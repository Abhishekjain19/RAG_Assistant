import os 
from langchain_chroma import Chroma 
try:
    from langchain_huggingface import HuggingFaceEmbeddings
except ImportError:
    from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document

CHROMA_DIR = "vector_db"
COLLECTION_NAME = "meeting_transcript"
EMBEDDING_MODEL  = "all-MiniLM-L6-v2"

_embeddings = None

def get_embeddings():
    global _embeddings
    if _embeddings is None:
        _embeddings = HuggingFaceEmbeddings(
            model_name=EMBEDDING_MODEL,
            model_kwargs={"device": "cpu"}
        )
    return _embeddings

def build_vector_store(transcript: str, persist_directory: str = CHROMA_DIR) -> Chroma:
    print("Building vector Store...")

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=150,
        separators=["\n\n", "\n", ". ", " ", ""],
    )
    chunks = splitter.split_text(transcript)
    if not chunks:
        chunks = [(transcript or "").strip() or "No transcript available."]

    docs = [
        Document(page_content=chunk, metadata={'chunk_index': i})
        for i, chunk in enumerate(chunks)
    ]

    embeddings = get_embeddings()

    # Reset existing collection if present to avoid cross-meeting document pollution
    try:
        existing = Chroma(
            collection_name=COLLECTION_NAME,
            embedding_function=embeddings,
            persist_directory=persist_directory,
        )
        existing.delete_collection()
        if hasattr(existing, "_client") and hasattr(existing._client, "close"):
            try:
                existing._client.close()
            except Exception:
                pass
    except Exception:
        pass

    vector_store = Chroma.from_documents(
        documents=docs,
        embedding=embeddings,
        collection_name=COLLECTION_NAME,
        persist_directory=persist_directory,
    )

    return vector_store


def load_vector_store(persist_directory: str = CHROMA_DIR) -> Chroma:
    embeddings = get_embeddings()
    vector_store = Chroma(
        collection_name=COLLECTION_NAME,
        embedding_function=embeddings,
        persist_directory=persist_directory,
    )

    return vector_store


def get_retriever(vector_store: Chroma, k: int = 8, search_type: str = "mmr"):
    n = 0
    try:
        n = int(vector_store._collection.count())
    except Exception:
        n = 0
    k = max(1, min(k, n)) if n else max(1, k)
    if search_type == "mmr":
        fetch_k = min(max(k, 20), n) if n else max(k, 20)
        return vector_store.as_retriever(
            search_type="mmr",
            search_kwargs={"k": k, "fetch_k": fetch_k, "lambda_mult": 0.7},
        )
    return vector_store.as_retriever(
        search_type="similarity",
        search_kwargs={"k": k},
    )


def clear_vector_store(persist_directory: str = CHROMA_DIR) -> None:
    """Clear and delete the vector database collection and persisted files."""
    import gc
    import shutil
    try:
        embeddings = get_embeddings()
        store = Chroma(
            collection_name=COLLECTION_NAME,
            embedding_function=embeddings,
            persist_directory=persist_directory,
        )
        store.delete_collection()
        if hasattr(store, "_client") and hasattr(store._client, "close"):
            try:
                store._client.close()
            except Exception:
                pass
        del store
        gc.collect()
    except Exception as e:
        print(f"Notice: collection delete skipped/failed: {e}")

    # Remove all lingering SQLite and index files in persist_directory
    if os.path.exists(persist_directory):
        for entry in os.scandir(persist_directory):
            try:
                if entry.is_file() or entry.is_symlink():
                    os.remove(entry.path)
                elif entry.is_dir():
                    shutil.rmtree(entry.path, ignore_errors=True)
            except Exception as e:
                # On Windows, SQLite might be locked briefly; collection is already cleared
                pass



