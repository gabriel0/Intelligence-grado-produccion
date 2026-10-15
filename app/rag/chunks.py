import hashlib
import json
import re
from pathlib import Path

import tiktoken
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.config import (
    CHUNK_OVERLAP_TOKENS,
    CHUNK_SIZE_TOKENS,
    CHUNKS_PATH,
    DATA,
)

ALLOWED_SUFFIXES = {".md", ".txt"}


def read_text(path: Path) -> str:
    raw_bytes = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-8", "cp1252"):
        try:
            return raw_bytes.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw_bytes.decode("utf-8", errors="replace")


def clean_text(text: str) -> str:
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    text = re.sub(r"[\u200b-\u200d\ufeff\u00ad]", "", text)
    text = re.sub(r"\r\n?", "\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def chunk_id(doc_id: str, page: int, text: str) -> str:
    payload = f"{doc_id}\n{page}\n{text}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def list_source_files(data_dir: Path = DATA) -> list[Path]:
    if not data_dir.is_dir():
        return []
    return sorted(
        path
        for path in data_dir.iterdir()
        if path.is_file() and path.suffix.lower() in ALLOWED_SUFFIXES
    )


def build_documents_from_paths(paths: list[Path]) -> list[Document]:
    tokenizer = tiktoken.get_encoding("cl100k_base")
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE_TOKENS,
        chunk_overlap=CHUNK_OVERLAP_TOKENS,
        length_function=lambda text: len(tokenizer.encode(text)),
        separators=["\n\n", "\n", ". ", " ", ""],
    )
    documents: list[Document] = []
    for path in paths:
        if path.suffix.lower() not in ALLOWED_SUFFIXES:
            continue
        doc_id = path.stem
        raw = clean_text(read_text(path))
        if not raw:
            print(f"{path.name}: vacío, se omite", flush=True)
            continue
        chunks = splitter.split_text(raw)
        print(
            f"{path.name}: {len(tokenizer.encode(raw))} tokens -> {len(chunks)} chunks",
            flush=True,
        )
        for index, text in enumerate(chunks, start=1):
            identifier = chunk_id(doc_id, index, text)
            documents.append(
                Document(
                    page_content=text,
                    metadata={
                        "chunk_id": identifier,
                        "doc_id": doc_id,
                        "source": path.name,
                        "page": index,
                        "category": doc_id,
                        "text": text,
                    },
                )
            )
    return documents


def build_documents(data_dir: Path = DATA) -> list[Document]:
    files = list_source_files(data_dir)
    if not files:
        raise FileNotFoundError(f"No hay archivos .md o .txt en {data_dir}")
    return build_documents_from_paths(files)


def save_chunks(documents: list[Document], path: Path = CHUNKS_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = [
        {"page_content": doc.page_content, "metadata": doc.metadata}
        for doc in documents
    ]
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
