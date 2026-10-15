"""API asíncrona del orquestador. La instrumentación corre antes de LangChain."""

from dotenv import load_dotenv

load_dotenv()

from app.observability import iniciar

iniciar()

import asyncio
import logging
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, File, HTTPException, UploadFile
from redis import asyncio as aioredis

from app.agents.runtime import texto
from app.agents.vector_store import cerrar_http
from app.config import API_HOST, API_PORT, DATA, QUEUE_NAME, REDIS_URL
from app.graph import build_graph, memoria_redis
from app.observability import registrar_tarifa
from app.rag.chunks import list_source_files
from app.rag.ingest import (
    namespace_count,
    reindex_all,
    save_markdown,
    seed_if_empty,
    upsert_files,
)
from app.schemas import (
    AprobacionAceptada,
    AprobacionEntrada,
    ArchivoIndexado,
    CargaResponse,
    Conversacion,
    DocumentoInfo,
    DocumentosLista,
    EstadoJob,
    MensajeConversacion,
    ReindexResponse,
    Salud,
    TareaAceptada,
    TareaEntrada,
)
from app.worker import consumir, guardar, leer

log = logging.getLogger("intelligence_system")
_reindex_lock = asyncio.Lock()


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.redis = aioredis.from_url(REDIS_URL, decode_responses=True)
    app.state.redis_worker = aioredis.from_url(
        REDIS_URL,
        decode_responses=True,
        socket_timeout=None,
        socket_connect_timeout=5,
    )
    await app.state.redis.ping()
    await registrar_tarifa()

    async def _seed_en_fondo() -> None:
        try:
            chunks = await asyncio.to_thread(seed_if_empty)
            log.info("Pinecone seed/estado: %s chunks", chunks)
        except Exception:
            log.exception("No se pudo preparar Pinecone al arrancar")

    async with memoria_redis(REDIS_URL) as checkpointer:
        app.state.graph = build_graph(checkpointer)
        tarea = asyncio.create_task(consumir(app))
        # Seed después de aceptar tráfico: crear índice + embeds no debe tumbar /health.
        seed_task = asyncio.create_task(_seed_en_fondo())
        yield
        seed_task.cancel()
        try:
            await seed_task
        except asyncio.CancelledError:
            pass
        tarea.cancel()
        try:
            await tarea
        except asyncio.CancelledError:
            pass
    await app.state.redis_worker.aclose()
    await app.state.redis.aclose()
    await cerrar_http()


app = FastAPI(
    title="The Intelligence System",
    version="1.0.0",
    description=(
        "Sistema de IA unificado (módulos 6 y 7): RAG sobre Pinecone, orquestador "
        "multi-agente con supervisor, cola Redis, checkpoints LangGraph, trazas en "
        "Arize Phoenix, carga de documentos por API y aprobación humana (HITL) "
        "antes de publicar un precio en el catálogo."
    ),
    lifespan=lifespan,
)


@app.get("/health", response_model=Salud, tags=["sistema"])
async def health() -> Salud:
    try:
        await app.state.redis.ping()
        redis_ok = "ok"
    except Exception:
        redis_ok = "error"
    pinecone_estado: Literal["ok", "error", "empty"]
    try:
        chunks = await asyncio.to_thread(namespace_count)
        pinecone_estado = "ok" if chunks > 0 else "empty"
    except Exception:
        chunks = 0
        pinecone_estado = "error"
    return Salud(
        api="ok",
        redis=redis_ok,
        pinecone=pinecone_estado,
        chunks=chunks,
        reindexando=_reindex_lock.locked(),
    )


@app.get("/documentos", response_model=DocumentosLista, tags=["conocimiento"])
async def listar_documentos() -> DocumentosLista:
    archivos = [
        DocumentoInfo(nombre=path.name, bytes=path.stat().st_size)
        for path in list_source_files(DATA)
    ]
    try:
        chunks = await asyncio.to_thread(namespace_count)
    except Exception:
        chunks = 0
    return DocumentosLista(archivos=archivos, chunks=chunks, data_dir=str(DATA))


@app.post("/reindex", response_model=ReindexResponse, tags=["conocimiento"])
async def reindexar() -> ReindexResponse:
    if _reindex_lock.locked():
        raise HTTPException(status_code=409, detail="Ya hay una reindexación en curso.")
    async with _reindex_lock:
        try:
            chunks = await asyncio.to_thread(reindex_all, DATA)
        except FileNotFoundError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except Exception as error:
            raise HTTPException(
                status_code=500,
                detail=f"Falló la reindexación: {error}",
            ) from error
        return ReindexResponse(chunks=chunks, data_dir=str(DATA))


@app.post("/documentos", response_model=CargaResponse, tags=["conocimiento"])
async def cargar_documentos(
    archivos: list[UploadFile] = File(
        ...,
        description=(
            "Uno o más .md o .txt. Cada archivo se guarda en data/ y se reindexa "
            "solo en Pinecone (upsert por nombre; no hace falta POST /reindex)."
        ),
    ),
) -> CargaResponse:
    if not archivos:
        raise HTTPException(status_code=400, detail="No se enviaron archivos.")
    if _reindex_lock.locked():
        raise HTTPException(
            status_code=409,
            detail="Hay una reindexación en curso. Reintentá en unos segundos.",
        )
    async with _reindex_lock:
        guardados: list[str] = []
        detalle: list[ArchivoIndexado] = []
        chunks_nuevos = 0
        try:
            for archivo in archivos:
                contenido = await archivo.read()
                path = await asyncio.to_thread(
                    save_markdown,
                    archivo.filename or "documento.md",
                    contenido,
                )
                # Reindex automático por archivo: borra chunks previos del source y upsert.
                chunks_archivo = await asyncio.to_thread(upsert_files, [path])
                guardados.append(path.name)
                detalle.append(ArchivoIndexado(nombre=path.name, chunks=chunks_archivo))
                chunks_nuevos += chunks_archivo
            chunks_totales = await asyncio.to_thread(namespace_count)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        except Exception as error:
            raise HTTPException(
                status_code=500,
                detail=f"No se pudieron indexar los archivos: {error}",
            ) from error
        return CargaResponse(
            archivos=guardados,
            detalle=detalle,
            chunks_nuevos=chunks_nuevos,
            chunks_totales=chunks_totales,
            data_dir=str(DATA),
            reindexado=True,
        )


@app.post("/tasks", response_model=TareaAceptada, status_code=202, tags=["tareas"])
async def crear_tarea(entrada: TareaEntrada) -> TareaAceptada:
    job_id = str(uuid.uuid4())
    thread_id = entrada.thread_id or str(uuid.uuid4())
    estado = {
        "job_id": job_id,
        "thread_id": thread_id,
        "status": "PENDING",
        "fase": "nueva",
        "consulta": entrada.consulta,
        "respuesta": None,
        "pasos": None,
        "error": None,
        "es_critica": False,
        "propuesta": None,
        "aprobado": None,
        "comentario": "",
    }
    await guardar(app.state.redis, job_id, estado)
    await app.state.redis.rpush(QUEUE_NAME, job_id)
    return TareaAceptada(job_id=job_id, thread_id=thread_id, status="PENDING")


@app.get("/tasks/{job_id}", response_model=EstadoJob, tags=["tareas"])
async def estado_tarea(job_id: str) -> EstadoJob:
    estado = await leer(app.state.redis, job_id)
    if estado is None:
        raise HTTPException(status_code=404, detail="Tarea no encontrada")
    return EstadoJob.model_validate(estado)


@app.post(
    "/tasks/{job_id}/approve",
    response_model=AprobacionAceptada,
    status_code=202,
    tags=["tareas"],
)
async def aprobar_tarea(job_id: str, entrada: AprobacionEntrada) -> AprobacionAceptada:
    estado = await leer(app.state.redis, job_id)
    if estado is None:
        raise HTTPException(status_code=404, detail="Tarea no encontrada")
    if estado["status"] != "AWAITING_APPROVAL":
        raise HTTPException(status_code=409, detail="La tarea no está esperando aprobación")
    estado["aprobado"] = entrada.aprobado
    estado["comentario"] = entrada.comentario
    estado["fase"] = "reanudar"
    estado["status"] = "RUNNING"
    await guardar(app.state.redis, job_id, estado)
    await app.state.redis.rpush(QUEUE_NAME, job_id)
    return AprobacionAceptada(job_id=job_id, status="RUNNING")


@app.get("/conversations/{thread_id}", response_model=Conversacion, tags=["conversaciones"])
async def leer_conversacion(thread_id: str) -> Conversacion:
    snapshot = await app.state.graph.aget_state({"configurable": {"thread_id": thread_id}})
    valores = snapshot.values if snapshot else None
    mensajes = list((valores or {}).get("messages") or [])
    if not mensajes:
        raise HTTPException(status_code=404, detail="Conversación no encontrada")
    return Conversacion(
        thread_id=thread_id,
        mensajes=[
            MensajeConversacion(
                rol=mensaje.type,
                contenido=texto(mensaje),
                nombre=getattr(mensaje, "name", None),
            )
            for mensaje in mensajes
        ],
        investigacion=(valores or {}).get("investigacion") or "",
        analisis=(valores or {}).get("analisis") or "",
        respuesta_final=(valores or {}).get("respuesta_final") or "",
        ajuste=(valores or {}).get("ajuste") or "",
    )


def main() -> None:
    import uvicorn

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    uvicorn.run("app.main:app", host=API_HOST, port=API_PORT, reload=False)


if __name__ == "__main__":
    main()
