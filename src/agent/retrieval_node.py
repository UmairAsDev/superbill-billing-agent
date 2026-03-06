import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))
from langchain_chroma import Chroma
from langchain_openai import OpenAIEmbeddings
from config.schema import BillingState
from config.config import settings
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()



DATA_DIR = settings.DATA_DIR
CHROMA_DIR = settings.CHROMA_DIR
COLLECTION_NAME = settings.COLLECTION_NAME


OpenAI(api_key=settings.OPENAI_API_KEY)

embedding = OpenAIEmbeddings(model=settings.embedding_model)

vectorstore = Chroma(
    collection_name=COLLECTION_NAME,
    embedding_function=embedding,
    persist_directory=CHROMA_DIR
)

async def retrieval_node(state: BillingState) -> BillingState:
    query_parts = []
    em_query_parts = []

    notes = state.get("notes", {})
    procedures = notes.get("procedures_documented")
    diagnoses = notes.get("diagnoses")
    chief_complaint = notes.get("chief_complaint")
    history = notes.get("history")
    exam = notes.get("exam")
    assessment = notes.get("assessment")
    visit = notes.get("visit")
    patient_summary = notes.get("raw_patient_summary")

    if procedures:
        query_parts.append(str(procedures))
    if diagnoses:
        query_parts.append(str(diagnoses))

    if chief_complaint:
        em_query_parts.append(str(chief_complaint))
    if history:
        em_query_parts.append(str(history))
    if exam:
        em_query_parts.append(str(exam))
    if assessment:
        em_query_parts.append(str(assessment))
    if visit:
        em_query_parts.append(str(visit))
    if diagnoses:
        em_query_parts.append(str(diagnoses))


    biopsy = state.get("biopsy", {})
    mohs = state.get("mohs", {})
    if biopsy:
        query_parts.append(str(biopsy))
    if mohs:
        query_parts.append(str(mohs))

    query = " ".join(query_parts).strip()

    docs_main = vectorstore.similarity_search(query=query, k=8) if query else []

    # Modifiers are often not retrieved by a generic query (k is small and modifiers
    # text is short). Do a second pass constrained to modifier docs.
    docs_mod = []
    if query:
        try:
            docs_mod = vectorstore.similarity_search(
                query=f"{query} modifier",
                k=20,
                filter={"type": "modifier"},
            )
        except TypeError:
            # Some vectorstore adapters don't support filter; fall back to unfiltered
            # search and then keep only modifier docs.
            docs_mod = [
                d
                for d in vectorstore.similarity_search(query=f"{query} modifier", k=20)
                if getattr(d, "metadata", {}).get("type") == "modifier"
            ]

    em_query = " ".join(em_query_parts).strip()
    docs_enm = []
    if em_query:
        visit_text = " ".join(
            [
                str(chief_complaint or ""),
                str(patient_summary or ""),
                str(assessment or ""),
            ]
        ).lower()
        if "followup" in visit_text or "follow-up" in visit_text or "established" in visit_text:
            enm_type_hint = "estPat"
        elif "new patient" in visit_text or "new" in visit_text:
            enm_type_hint = "newPat"
        else:
            enm_type_hint = None

        facility_code = None
        if isinstance(visit, dict):
            place = str(visit.get("place_of_service") or "").strip().lower()
            if place == "office":
                facility_code = "11"

        try:
            docs_enm_general = vectorstore.similarity_search(
                query=f"{em_query} office visit em level",
                k=12,
                filter={"type": "enm"},
            )

            docs_enm_typed = []
            if enm_type_hint:
                docs_enm_typed.extend(
                    vectorstore.similarity_search(
                        query=f"{em_query} office follow up established patient em",
                        k=12,
                        filter={"enmType": enm_type_hint},
                    )
                )
            if facility_code:
                docs_enm_typed.extend(
                    vectorstore.similarity_search(
                        query=f"{em_query} office encounter place of service",
                        k=12,
                        filter={"facilityCode": facility_code},
                    )
                )

            docs_enm = [*docs_enm_typed, *docs_enm_general]
        except TypeError:
            docs_enm = [
                d
                for d in vectorstore.similarity_search(
                    query=f"{em_query} office visit em level", k=12
                )
                if getattr(d, "metadata", {}).get("type") == "enm"
            ]

    # Prefer office/non-preventive ENM families (estPat/newPat/consult) and only
    # keep "other" if we have no focused ENM results.
    docs_enm_preferred = [
        d
        for d in docs_enm
        if str(getattr(d, "metadata", {}).get("enmType") or "") in {"estPat", "newPat", "consult"}
    ]
    if docs_enm_preferred:
        docs_enm = docs_enm_preferred

    seen: set[str] = set()
    combined = []
    for doc in [*docs_main, *docs_mod, *docs_enm]:
        meta = getattr(doc, "metadata", {}) or {}
        doc_type = str(meta.get("type") or "")
        key = None
        if doc_type == "procedure" and meta.get("proCode") is not None:
            key = f"procedure:{meta.get('proCode')}"
        elif doc_type == "enm" and meta.get("enmCode") is not None:
            key = f"enm:{meta.get('enmCode')}"
        elif doc_type == "modifier" and meta.get("modifier") is not None:
            key = f"modifier:{meta.get('modifier')}"
        else:
            key = f"content:{getattr(doc, 'page_content', '')[:200]}"

        if key in seen:
            continue
        seen.add(key)

        if not meta.get("active", True):
            continue

        combined.append({"content": doc.page_content, "metadata": meta})

    state["retrieval"] = combined

    return state
