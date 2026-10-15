"""Ingesta de documentos hacia Pinecone (seed, reindex y upsert por archivo)."""

import logging
import re
from pathlib import Path

from langchain_pinecone import PineconeVectorStore

from app.config import DATA, INDEX_NAME, MAX_UPLOAD_BYTES, PINECONE_NAMESPACE
from app.rag.chunks import (
    ALLOWED_SUFFIXES,
    build_documents,
    build_documents_from_paths,
    list_source_files,
    save_chunks,
)
from app.rag.embeddings import get_embeddings
from app.rag.pinecone_setup import ensure_index, index_handle

log = logging.getLogger("intelligence_system")

_SAFE_STEM = re.compile(r"[^a-zA-Z0-9._-]+")


def safe_filename(original: str) -> str:
    name = Path(original).name
    if not name or name != Path(name).name or ".." in name:
        raise ValueError("Nombre de archivo inválido.")
    suffix = Path(name).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise ValueError("Solo se aceptan archivos .md o .txt.")
    stem = _SAFE_STEM.sub("_", Path(name).stem).strip("._")
    if not stem:
        raise ValueError("Nombre de archivo inválido.")
    return f"{stem}{suffix}"


def save_markdown(filename: str, content: bytes, dest_dir: Path = DATA) -> Path:
    if len(content) > MAX_UPLOAD_BYTES:
        raise ValueError(
            f"El archivo supera el máximo de {MAX_UPLOAD_BYTES // (1024 * 1024)} MB."
        )
    try:
        content.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError("El archivo tiene que ser texto UTF-8.") from error
    dest_dir.mkdir(parents=True, exist_ok=True)
    path = dest_dir / safe_filename(filename)
    path.write_bytes(content)
    return path


def _prepare_index() -> None:
    encoder = get_embeddings()
    ensure_index(len(encoder.embed_query("dimension")))


def clear_namespace() -> None:
    index = index_handle()
    try:
        index.delete(delete_all=True, namespace=PINECONE_NAMESPACE)
        log.info("Namespace '%s' vaciado.", PINECONE_NAMESPACE)
    except Exception as exc:
        message = str(exc).lower()
        if "namespace not found" in message or "404" in message:
            log.info("Namespace '%s' todavía no tenía vectores.", PINECONE_NAMESPACE)
            return
        raise


def delete_source(source: str) -> None:
    index = index_handle()
    try:
        index.delete(
            filter={"source": {"$eq": source}},
            namespace=PINECONE_NAMESPACE,
        )
    except Exception as exc:
        message = str(exc).lower()
        if "namespace not found" in message or "404" in message:
            return
        raise


def namespace_count() -> int:
    try:
        stats = index_handle().describe_index_stats()
    except Exception:
        return 0
    namespaces = getattr(stats, "namespaces", None) or {}
    if isinstance(stats, dict):
        namespaces = stats.get("namespaces") or {}
    info = namespaces.get(PINECONE_NAMESPACE) or {}
    if isinstance(info, dict):
        return int(info.get("vector_count") or 0)
    return int(getattr(info, "vector_count", 0) or 0)


def _upsert_documents(documents: list) -> int:
    if not documents:
        return 0
    ids = [doc.metadata["chunk_id"] for doc in documents]
    PineconeVectorStore.from_documents(
        documents=documents,
        embedding=get_embeddings(),
        index_name=INDEX_NAME,
        namespace=PINECONE_NAMESPACE,
        ids=ids,
    )
    return len(documents)


def upsert_files(paths: list[Path]) -> int:
    """Reemplaza en Pinecone los chunks de cada archivo y deja el resto intacto."""
    _prepare_index()
    added = 0
    for path in paths:
        delete_source(path.name)
        documents = build_documents_from_paths([path])
        added += _upsert_documents(documents)
    return added


def reindex_all(data_dir: Path = DATA) -> int:
    """Vacía el namespace e indexa todos los .md/.txt de data/."""
    _prepare_index()
    documents = build_documents(data_dir)
    clear_namespace()
    count = _upsert_documents(documents)
    save_chunks(documents)
    log.info(
        "Reindex listo: %s chunks en '%s' / namespace '%s'.",
        count,
        INDEX_NAME,
        PINECONE_NAMESPACE,
    )
    return count


def seed_if_empty(data_dir: Path = DATA) -> int:
    """Si el namespace está vacío y hay archivos en data/, indexa el seed."""
    _prepare_index()
    existing = namespace_count()
    if existing > 0:
        log.info("Pinecone ya tiene %s vectores en '%s'.", existing, PINECONE_NAMESPACE)
        return existing
    files = list_source_files(data_dir)
    if not files:
        log.warning("Namespace vacío y no hay documentos seed en %s.", data_dir)
        return 0
    log.info("Namespace vacío. Indexando seed desde %s (%s archivos).", data_dir, len(files))
    documents = build_documents_from_paths(files)
    count = _upsert_documents(documents)
    save_chunks(documents)
    return count
