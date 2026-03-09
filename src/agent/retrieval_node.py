import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))
from config.schema import BillingState
from config.config import settings
from src.agent.state_helpers import _append_narrative
from loguru import logger

DATA_DIR = settings.DATA_DIR
CHROMA_DIR = settings.CHROMA_DIR
COLLECTION_NAME = settings.COLLECTION_NAME

# Lazy-initialised so the module can be imported without env vars being set.
_vectorstore = None


def _tokenize(value: object) -> list[str]:
    text = str(value or "").lower()
    parts = [part.strip(" ,.;:/()[]{}") for part in text.split()]
    return [part for part in parts if len(part) > 2]


def _build_focus_terms(facts: dict) -> set[str]:
    terms: set[str] = set()
    for key in ("documented_procedures", "sites", "laterality"):
        value = facts.get(key)
        if isinstance(value, list):
            for item in value:
                terms.update(_tokenize(item))
    return terms


def _doc_relevance_score(doc: dict, focus_terms: set[str]) -> int:
    content = str(doc.get("content") or "").lower()
    metadata = doc.get("metadata", {}) or {}
    desc = str(
        metadata.get("codeDesc")
        or metadata.get("enmCodeDesc")
        or metadata.get("modifierDesc")
        or ""
    ).lower()
    hay = f"{content} {desc}"
    score = 0
    for term in focus_terms:
        if term in hay:
            score += 1
    return score


def _trim_by_type(items: list[dict], facts: dict) -> list[dict]:
    focus_terms = _build_focus_terms(facts)
    caps = {"procedure": 10, "enm": 5, "modifier": 10}
    buckets: dict[str, list[dict]] = {"procedure": [], "enm": [], "modifier": []}
    passthrough: list[dict] = []

    for item in items:
        item_type = str((item.get("metadata", {}) or {}).get("type") or "")
        if item_type in buckets:
            buckets[item_type].append(item)
        else:
            passthrough.append(item)

    trimmed: list[dict] = []
    for item_type, docs in buckets.items():
        ranked = sorted(
            docs,
            key=lambda doc: (
                -_doc_relevance_score(doc, focus_terms),
                str((doc.get("metadata", {}) or {}).get("proCode")
                    or (doc.get("metadata", {}) or {}).get("enmCode")
                    or (doc.get("metadata", {}) or {}).get("modifier")
                    or ""),
            ),
        )
        trimmed.extend(ranked[: caps[item_type]])

    trimmed.extend(passthrough)
    return trimmed


def _get_vectorstore():
    """Return the shared Chroma vectorstore, initialising it on first call."""
    global _vectorstore
    if _vectorstore is None:
        from langchain_chroma import Chroma
        from pydantic import SecretStr
        from langchain_openai import OpenAIEmbeddings

        embedding = OpenAIEmbeddings(
            api_key=SecretStr(settings.OPENAI_API_KEY),
            model=settings.embedding_model,
        )
        _vectorstore = Chroma(
            collection_name=COLLECTION_NAME,
            embedding_function=embedding,
            persist_directory=CHROMA_DIR,
        )
    return _vectorstore


async def retrieval_node(state: BillingState) -> BillingState:
    try:
        vectorstore = _get_vectorstore()
    except Exception as exc:
        logger.error(f"retrieval_node: failed to initialise vectorstore: {exc}")
        state["retrieval"] = []
        _append_narrative(state, f"retrieval_node: vectorstore init failed — {exc}")
        return state

    facts = state.get("encounter_facts", {})
    if not isinstance(facts, dict):
        facts = {}

    documented_procedures = facts.get("documented_procedures", [])
    dx_codes = facts.get("documented_dx_codes", [])
    patient_type = facts.get("patient_type", "unknown")
    visit_type = facts.get("visit_type", "unknown")
    place_of_service = str(facts.get("place_of_service", "")).lower()

    docs_main = []

    # 1. Targeted Procedure Search
    for proc in documented_procedures:
        if not proc or not str(proc).strip():
            continue
        try:
            proc_query = str(proc).strip()
            docs = vectorstore.similarity_search(
                query=proc_query, k=2, filter={"type": "procedure"}
            )
            docs_main.extend(docs)

            for site in facts.get("sites", []) if isinstance(facts.get("sites"), list) else []:
                if not str(site).strip():
                    continue
                docs_site = vectorstore.similarity_search(
                    query=f"{proc_query} {site}",
                    k=1,
                    filter={"type": "procedure"},
                )
                docs_main.extend(docs_site)
        except Exception as exc:
            logger.error(f"retrieval_node: procedure search failed for '{proc}': {exc}")
            # fallback loose search if filter fails
            try:
                docs = vectorstore.similarity_search(query=str(proc), k=2)
                docs_main.extend(docs)
            except Exception:
                pass

    # 2. Targeted Diagnoses Search
    for dx in dx_codes:
        if not dx:
            continue
        try:
            docs = vectorstore.similarity_search(query=f"diagnosis {dx}", k=1)
            docs_main.extend(docs)
        except Exception as exc:
            logger.warning(f"retrieval_node: dx search failed for '{dx}': {exc}")

    # 3. Targeted Modifier Search based on procedures
    docs_mod = []
    mod_queries: list[str] = []
    if documented_procedures:
        mod_queries.extend(f"{str(proc)} modifier" for proc in documented_procedures if str(proc).strip())
    if isinstance(facts.get("laterality"), list) and facts.get("laterality"):
        mod_queries.append("laterality modifier")
    if visit_type != "procedure_only":
        mod_queries.append("evaluation management modifier")
    if not mod_queries:
        mod_queries = ["modifier"]

    for query in mod_queries[:6]:
        try:
            docs = vectorstore.similarity_search(
                query=query,
                k=3,
                filter={"type": "modifier"},
            )
            docs_mod.extend(docs)
        except Exception as exc:
            logger.warning(f"retrieval_node: modifier search failed for '{query}': {exc}")

    # 4. Targeted EM Search
    docs_enm = []
    if visit_type != "procedure_only":
        em_query_parts = ["office visit"]
        enm_type_hint = None
        facility_code = None

        if "office" in place_of_service:
            facility_code = "11"

        if patient_type == "established" or visit_type == "followup":
            enm_type_hint = "estPat"
            em_query_parts.append("established patient follow up")
        elif patient_type == "new":
            enm_type_hint = "newPat"
            em_query_parts.append("new patient")
        elif visit_type == "consult":
            enm_type_hint = "consult"
            em_query_parts.append("consultation")

        em_query = " ".join(em_query_parts)

        try:
            docs_enm_typed = []
            if enm_type_hint:
                docs_enm_typed.extend(
                    vectorstore.similarity_search(
                        query=f"{em_query} EM codes",
                        k=4,
                        filter={"enmType": enm_type_hint},
                    )
                )

            # Also get general office visit ones
            docs_enm_general = vectorstore.similarity_search(
                query=f"{em_query} EM level",
                k=3,
                filter={"type": "enm"},
            )

            docs_enm = [*docs_enm_typed, *docs_enm_general]
        except Exception as exc:
            logger.warning(f"retrieval_node: ENM search failed: {exc}")

    # Combine and deduplicate
    seen: set[str] = set()
    combined = []
    for doc in [*docs_main, *docs_mod, *docs_enm]:
        meta = getattr(doc, "metadata", {}) or {}
        doc_type = str(meta.get("type") or "")

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

    combined = _trim_by_type(combined, facts)
    state["retrieval"] = combined

    procedure_count = sum(
        1
        for item in combined
        if str(item.get("metadata", {}).get("type")) == "procedure"
    )
    enm_count = sum(
        1 for item in combined if str(item.get("metadata", {}).get("type")) == "enm"
    )
    modifier_count = sum(
        1
        for item in combined
        if str(item.get("metadata", {}).get("type")) == "modifier"
    )

    _append_narrative(
        state,
        f"retrieval_node: pulled procedure={procedure_count}, enm={enm_count}, modifier={modifier_count} references using targeted search",
    )

    return state
