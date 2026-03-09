from langchain_chroma import Chroma
from langchain_openai import OpenAIEmbeddings
from config.config import settings
from pydantic import SecretStr

embedding = OpenAIEmbeddings(
    api_key=SecretStr(settings.OPENAI_API_KEY),
    model=settings.embedding_model,
)

vectorstore = Chroma(
    collection_name=settings.COLLECTION_NAME,
    embedding_function=embedding,
    persist_directory=settings.CHROMA_DIR,
)

print("Searching for 99214:")
results = vectorstore.similarity_search("99214 office visit", k=5)
for res in results:
    if res.metadata.get("enmCode") == "99214" or "99214" in res.page_content:
        print(res.page_content)
        print("Metadata:", res.metadata)

print("\nSearching for 10040:")
res2 = vectorstore.similarity_search("10040 acne surgery", k=5)
for res in res2:
    if res.metadata.get("proCode") == "10040" or "10040" in res.page_content:
        print(res.page_content)
        print("Metadata:", res.metadata)

# Let's also dump the first few ENM codes to see what they look like
print("\nDumping some ENM codes:")
res3 = vectorstore.similarity_search("office visit", k=10, filter={"type": "enm"})
for res in res3:
    print(res.metadata.get("enmCode"), res.metadata.get("enmType"))
