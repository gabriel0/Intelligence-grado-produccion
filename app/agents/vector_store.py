"""Búsqueda densa en Pinecone. Embeddings vía Ollama."""

import asyncio
import json
import time

from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

from app.config import (
    ACTIVE_EMBED_MODEL,
    EMBEDDING_PROVIDER,
    INDEX_NAME,
    PINECONE_NAMESPACE,
    TOP_K,
    VERSION_PROMPT,
)
from app.rag.embeddings import get_embeddings
from app.rag.pinecone_setup import index_handle
from app.schemas import Fragmento

_tracer = trace.get_tracer("intelligence_system.vector_store")


async def cerrar_http() -> None:
    """Compatibilidad con el lifespan; los embeddings usan httpx efímero."""
    return None


async def buscar(consulta: str, k: int = TOP_K) -> list[Fragmento]:
    with _tracer.start_as_current_span("vector_db.buscar") as span:
        span.set_attribute("openinference.span.kind", "RETRIEVER")
        span.set_attribute("input.value", consulta)
        span.set_attribute("input.mime_type", "text/plain")
        span.set_attribute("prompt_template_version", VERSION_PROMPT)
        span.set_attribute("retrieval.index", INDEX_NAME)
        span.set_attribute("retrieval.namespace", PINECONE_NAMESPACE)
        try:
            red = time.perf_counter()
            with _tracer.start_as_current_span(f"{EMBEDDING_PROVIDER}.embed") as embed_span:
                embed_span.set_attribute("openinference.span.kind", "EMBEDDING")
                embed_span.set_attribute("embedding.model_name", ACTIVE_EMBED_MODEL)
                embed_span.set_attribute("input.value", consulta)
                encoder = get_embeddings()
                vector = await asyncio.to_thread(encoder.embed_query, consulta)
                embed_span.set_attribute("embedding.vector_dim", len(vector))
            red_ms = (time.perf_counter() - red) * 1000

            proceso = time.perf_counter()

            def _query() -> list[Fragmento]:
                resultado = index_handle().query(
                    vector=vector,
                    top_k=k,
                    namespace=PINECONE_NAMESPACE,
                    include_metadata=True,
                )
                matches = getattr(resultado, "matches", None) or []
                if isinstance(resultado, dict):
                    matches = resultado.get("matches") or []
                out: list[Fragmento] = []
                for match in matches:
                    metadata = getattr(match, "metadata", None) or {}
                    if isinstance(match, dict):
                        metadata = match.get("metadata") or {}
                        match_id = str(match.get("id") or "")
                        score = float(match.get("score") or 0.0)
                    else:
                        match_id = str(getattr(match, "id", "") or "")
                        score = float(getattr(match, "score", 0.0) or 0.0)
                    texto = str(metadata.get("text") or "")
                    fuente = str(
                        metadata.get("source") or metadata.get("doc_id") or "pinecone"
                    )
                    chunk_id = str(metadata.get("chunk_id") or match_id)
                    out.append(
                        Fragmento(
                            id=chunk_id,
                            fuente=fuente,
                            texto=texto,
                            score=max(-1.0, min(1.0, round(score, 4))),
                        )
                    )
                return out

            fragmentos = await asyncio.to_thread(_query)
            proc_ms = (time.perf_counter() - proceso) * 1000
            span.set_attribute("latency.network_ms", round(red_ms, 2))
            span.set_attribute("latency.processing_ms", round(proc_ms, 2))
            span.set_attribute(
                "output.value",
                json.dumps([item.model_dump() for item in fragmentos], ensure_ascii=False),
            )
            for posicion, doc in enumerate(fragmentos):
                span.set_attribute(f"retrieval.documents.{posicion}.document.id", doc.id)
                span.set_attribute(
                    f"retrieval.documents.{posicion}.document.content", doc.texto
                )
                span.set_attribute(
                    f"retrieval.documents.{posicion}.document.score", doc.score
                )
            span.set_status(Status(StatusCode.OK))
            return fragmentos
        except Exception as exc:
            span.record_exception(exc)
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            raise
