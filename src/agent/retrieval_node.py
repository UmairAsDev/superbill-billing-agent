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

    notes = state.get("notes", {})
    procedures = notes.get("procedures_documented")
    diagnoses = notes.get("diagnoses")

    if procedures:
        query_parts.append(str(procedures))
    if diagnoses:
        query_parts.append(str(diagnoses))


    biopsy = state.get("biopsy", {})
    mohs = state.get("mohs", {})
    if biopsy:
        query_parts.append(str(biopsy))
    if mohs:
        query_parts.append(str(mohs))

    query = " ".join(query_parts).strip()

    docs = vectorstore.similarity_search(query=query, k=8)

    state["retrieval"] = [
        {
            "content": doc.page_content,
            "metadata": doc.metadata
        }
        for doc in docs
        if doc.metadata.get("active", True)
    ]

    return state
