import hashlib
import re
import chromadb
from ollama import Client, ResponseError
from tqdm import tqdm

from llama_index.core import Document
from llama_index.core.node_parser import MarkdownNodeParser

from llm import answer
from config import settings


EMBED_MODEL = settings["embedding_model"]
KNOWLEDGE_PATH = settings["knowledge_path"]
CHROMA_PATH = settings["chroma_path"]
COLLECTION_NAME = "knowledge"
INDEX_VERSION = 3
MAX_CHUNK_CHARS = settings["max_chunk_chars"]
TOP_K = settings["top_k"]

db = chromadb.PersistentClient(path=str(CHROMA_PATH))
collection = db.get_or_create_collection(COLLECTION_NAME)
ollama = Client(host=settings["ollama_host"])

parser = MarkdownNodeParser()


def chunks():
    with KNOWLEDGE_PATH.open(encoding="utf-8") as f:
        text = f.read()

    document = Document(text=text)

    nodes = parser.get_nodes_from_documents([document])
    result = []

    for node in nodes:
        content = node.get_content().strip()
        if not content:
            continue

        lines = content.splitlines()
        title = next((line.strip() for line in lines if line.lstrip().startswith("#")), "")
        paragraphs = [
            part.strip()
            for part in re.split(r"\n\s*\n", content)
            if part.strip() and not part.lstrip().startswith("#")
        ]
        current = []
        current_length = 0

        for paragraph in paragraphs:
            candidate_length = current_length + len(paragraph) + 2
            if current and candidate_length > MAX_CHUNK_CHARS:
                result.append("\n\n".join(current))
                current = []
                current_length = 0

            if title and paragraph != title and not paragraph.startswith("#"):
                paragraph = f"{title}\n\n{paragraph}"

            current.append(paragraph)
            current_length += len(paragraph) + 2

        if current:
            result.append("\n\n".join(current))

    return result


def knowledge_hash():
    return hashlib.sha256(KNOWLEDGE_PATH.read_bytes()).hexdigest()


def index_signature():
    value = f"{knowledge_hash()}|{EMBED_MODEL}|{MAX_CHUNK_CHARS}"
    return hashlib.sha256(value.encode()).hexdigest()


def embed_text(text):
    try:
        return ollama.embed(model=EMBED_MODEL, input=text)["embeddings"][0]
    except (ConnectionError, ResponseError) as error:
        raise RuntimeError(
            f"Embedding model unavailable. Start Ollama and run: ollama pull {EMBED_MODEL}"
        ) from error


def _terms(text):
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def build():
    global collection

    signature = index_signature()
    metadata = collection.metadata or {}

    if (
        collection.count()
        and metadata.get("index_signature") == signature
        and metadata.get("index_version") == INDEX_VERSION
    ):
        print(f"Using existing index ({collection.count()} chunks)")
        return

    docs = chunks()

    if not docs:
        raise ValueError(f"No chunks found in {KNOWLEDGE_PATH}")

    if collection.count():
        print("Knowledge changed. Rebuilding index...")
        db.delete_collection(COLLECTION_NAME)
        collection = db.get_or_create_collection(
            COLLECTION_NAME,
            metadata={"index_signature": signature, "index_version": INDEX_VERSION},
        )
    else:
        collection.modify(metadata={"index_signature": signature, "index_version": INDEX_VERSION})

    print(f"Chunks: {len(docs)}")
    print("Embedding chunks...")

    vectors = [embed_text(doc) for doc in tqdm(docs, desc="Embedding")]

    collection.add(ids=[str(i) for i in range(len(docs))], documents=docs, embeddings=vectors)

    print("Index ready.")


def retrieve_scored(question, top_k=TOP_K):
    query = embed_text(question)
    candidate_count = min(max(top_k * 2, top_k), collection.count())

    result = collection.query(
        query_embeddings=[query],
        n_results=candidate_count,
    )

    query_terms = _terms(question)
    scored = []
    for document, distance in zip(result["documents"][0], result["distances"][0]):
        overlap = len(query_terms & _terms(document)) / max(len(query_terms), 1)
        semantic = 1 / (1 + distance)
        score = 0.75 * semantic + 0.25 * overlap
        scored.append((score, document, distance))

    scored.sort(key=lambda item: item[0], reverse=True)
    return scored[:top_k]


def retrieve(question, top_k=5):
    return [document for _, document, _ in retrieve_scored(question, top_k)]


def ask(question):
    print("Retrieving...")

    docs = retrieve(question)

    context = "\n\n".join(docs)

    print("Generating...")

    try:
        return answer(question, context)
    except (ConnectionError, ResponseError) as error:
        raise RuntimeError(
            "Generation model unavailable. Start Ollama and run: ollama pull qwen3:0.6b"
        ) from error
