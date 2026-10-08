"""Index the Meridian policy corpus into a local Chroma collection."""

import os
from pathlib import Path

os.environ.setdefault("HF_HUB_VERBOSITY", "error")
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

import chromadb
from sentence_transformers import SentenceTransformer

ROOT = Path(__file__).resolve().parent
CORPUS_DIR = ROOT / "corpus"
CHROMA_DIR = ROOT / "chroma_db"
COLLECTION_NAME = "meridian_policies"
MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"


def is_heading(line: str) -> bool:
    stripped = line.strip()
    letters = [char for char in stripped if char.isalpha()]
    return len(letters) >= 3 and stripped == stripped.upper()


def document_title(text: str, filename: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped == "MERIDIAN TECHNOLOGIES" or stripped.startswith("---"):
            if stripped.startswith("---"):
                break
            continue
        return stripped
    return filename


def split_sections(text: str) -> list[tuple[str, str]]:
    body = text.split("---", 1)[1] if "---" in text else text
    heading = "INTRODUCTION"
    lines: list[str] = []
    sections: list[tuple[str, str]] = []

    def flush() -> None:
        content = "\n".join(lines).strip()
        if content:
            sections.append((heading, content))

    for line in body.splitlines():
        if is_heading(line):
            flush()
            heading = line.strip()
            lines = []
        else:
            lines.append(line)
    flush()
    return sections


def embedding_text(title: str, filename: str, section: str, content: str) -> str:
    return f"Document: {title}\nFile: {filename}\nSection: {section}\n\n{content}"


def chunk_id(filename: str, index: int, section: str) -> str:
    slug = "".join(char.lower() if char.isalnum() else "-" for char in section)
    slug = "-".join(part for part in slug.split("-") if part)
    return f"{filename}::{index}::{slug}"


def main() -> None:
    files = sorted(CORPUS_DIR.glob("*.txt"))
    ids: list[str] = []
    documents: list[str] = []
    metadatas: list[dict[str, str]] = []

    for path in files:
        text = path.read_text(encoding="utf-8")
        title = document_title(text, path.name)
        for index, (section, content) in enumerate(split_sections(text)):
            ids.append(chunk_id(path.name, index, section))
            documents.append(embedding_text(title, path.name, section, content))
            metadatas.append({"source": path.name, "section": section})

    model = SentenceTransformer(MODEL_NAME)
    embeddings = model.encode(documents, normalize_embeddings=True, show_progress_bar=False)

    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    collection = client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )
    collection.upsert(
        ids=ids,
        documents=documents,
        embeddings=embeddings.tolist(),
        metadatas=metadatas,
    )
    stale = [existing for existing in collection.get(include=[])["ids"] if existing not in set(ids)]
    if stale:
        collection.delete(ids=stale)
    print(f"Indexed {len(files)} documents, {len(ids)} chunks.")


if __name__ == "__main__":
    main()
