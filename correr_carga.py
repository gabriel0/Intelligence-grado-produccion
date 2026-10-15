"""Validación: upload a Pinecone + cinco altas concurrentes + HITL."""

import asyncio
import json
import os
import time
from pathlib import Path

import httpx

import levantar

API = os.getenv("API_URL", "http://127.0.0.1:8000").rstrip("/")
ROOT = Path(__file__).resolve().parent
SALIDA = ROOT / "trazas" / "carga.json"
UPLOAD_PATH = ROOT / "data" / "prueba-upload.md"

MARCA_UPLOAD = "TOKEN-UPLOAD-ORION-ZX9"
UPLOAD_TEXTO = (
    "# Nota de prueba indexada por API\n\n"
    f"El producto Orion ZX9 tiene el código secreto {MARCA_UPLOAD}. "
    "Solo aparece en este documento subido por POST /documentos.\n"
)

CASOS = [
    (
        "novax-margen",
        "Con las reseñas del Nova X, decime el sentimiento neto y el margen porcentual de la ficha.",
    ),
    (
        "novax-precio",
        "¿Cuál es el precio de venta y el costo de reposición del Nova X?",
    ),
    (
        "novax-luis",
        "¿Qué sentimiento tiene la reseña de Luis sobre los Nova X? Incluí el sentimiento neto y el margen.",
    ),
    (
        "novax-umbral",
        "Con la ficha del Nova X, ¿el margen porcentual supera el 50%? Mostrá sentimiento neto y margen.",
    ),
    (
        "fuera-de-corpus",
        "¿Cuál es la garantía en dólares del televisor Bravia? Si no está en las reseñas, decilo.",
    ),
]

CRITICA = (
    "novax-descuento",
    "Publicá en el catálogo un descuento del Nova X. "
    "Antes calculá el sentimiento neto y el margen porcentual de la ficha.",
)

UPLOAD_CASO = (
    "upload-orion",
    f"Según los documentos indexados, ¿qué código secreto tiene el Orion ZX9? "
    f"Si aparece {MARCA_UPLOAD}, citálo.",
)


async def _esperar(cliente: httpx.AsyncClient, job_id: str, hasta: float) -> dict:
    limite = time.monotonic() + hasta
    while time.monotonic() < limite:
        response = await cliente.get(f"{API}/tasks/{job_id}")
        response.raise_for_status()
        estado = response.json()
        if estado["status"] in {"DONE", "FAILED", "AWAITING_APPROVAL"}:
            return estado
        await asyncio.sleep(3)
    raise TimeoutError(f"El job {job_id} no terminó a tiempo")


async def _alta(cliente: httpx.AsyncClient, nombre: str, consulta: str) -> dict:
    inicio = time.perf_counter()
    response = await cliente.post(
        f"{API}/tasks",
        json={"consulta": consulta, "thread_id": nombre},
    )
    response.raise_for_status()
    aceptada = response.json()
    aceptada["alta_ms"] = round((time.perf_counter() - inicio) * 1000, 1)
    aceptada["nombre"] = nombre
    print(f"{nombre} -> {aceptada['job_id']} en {aceptada['alta_ms']} ms", flush=True)
    return aceptada


async def _subir_documento(cliente: httpx.AsyncClient) -> dict:
    UPLOAD_PATH.write_text(UPLOAD_TEXTO, encoding="utf-8")
    with UPLOAD_PATH.open("rb") as handle:
        response = await cliente.post(
            f"{API}/documentos",
            files={"archivos": (UPLOAD_PATH.name, handle, "text/markdown")},
        )
    response.raise_for_status()
    cuerpo = response.json()
    print(
        f"upload -> {cuerpo['archivos']} chunks_nuevos={cuerpo['chunks_nuevos']} "
        f"totales={cuerpo['chunks_totales']}",
        flush=True,
    )
    return cuerpo


async def _esperar_api(cliente: httpx.AsyncClient, intentos: int = 60) -> dict:
    """Espera a que la API termine el lifespan (índice Pinecone / seed)."""
    ultimo: Exception | None = None
    for n in range(1, intentos + 1):
        try:
            salud = await cliente.get(f"{API}/health")
            salud.raise_for_status()
            cuerpo = salud.json()
            if cuerpo.get("redis") != "ok":
                raise RuntimeError("Redis no responde")
            if cuerpo.get("pinecone") == "error":
                raise RuntimeError("Pinecone no responde")
            # Si el seed aún corre, pinecone puede estar empty unos segundos.
            if cuerpo.get("pinecone") == "empty" and n < intentos:
                print(f"  API ok pero Pinecone vacío, espero seed... ({n}/{intentos})", flush=True)
                await asyncio.sleep(2)
                continue
            print(f"API lista (health ok, chunks={cuerpo.get('chunks', 0)})", flush=True)
            return cuerpo
        except Exception as exc:
            ultimo = exc
            print(f"  Esperando API... ({n}/{intentos}): {type(exc).__name__}", flush=True)
            await asyncio.sleep(2)
    raise SystemExit(f"La API no respondió a tiempo: {ultimo}")


async def main() -> None:
    from app.config import necesita_ollama

    if necesita_ollama():
        print("Aseguro Ollama (host)...", flush=True)
        levantar.main(solo_ollama=True)
    else:
        print("Sin Ollama (Gemini chat + embeddings Google).", flush=True)

    async with httpx.AsyncClient(timeout=60) as cliente:
        await _esperar_api(cliente)

        upload = await _subir_documento(cliente)
        docs = await cliente.get(f"{API}/documentos")
        docs.raise_for_status()
        nombres = {item["nombre"] for item in docs.json()["archivos"]}
        if UPLOAD_PATH.name not in nombres:
            raise SystemExit("El archivo subido no aparece en GET /documentos")

        altas = await asyncio.gather(
            *[_alta(cliente, nombre, consulta) for nombre, consulta in CASOS]
        )
        estados = []
        for alta in altas:
            estado = await _esperar(cliente, alta["job_id"], 2400)
            print(f"  {alta['nombre']} {estado['status']}", flush=True)
            estados.append({"caso": alta["nombre"], "alta_ms": alta["alta_ms"], **estado})

        upload_alta = await _alta(cliente, *UPLOAD_CASO)
        upload_estado = await _esperar(cliente, upload_alta["job_id"], 2400)
        print(f"  {upload_alta['nombre']} {upload_estado['status']}", flush=True)
        respuesta_upload = (upload_estado.get("respuesta") or "").upper()
        if upload_estado["status"] != "DONE" or MARCA_UPLOAD not in respuesta_upload:
            raise SystemExit(
                "La consulta sobre el documento subido no recuperó la marca: "
                f"{upload_estado.get('status')} {upload_estado.get('respuesta')}"
            )

        critica = await _alta(cliente, *CRITICA)
        pausa = await _esperar(cliente, critica["job_id"], 900)
        print(f"  pausa {pausa['status']}: {pausa.get('propuesta')}", flush=True)
        if pausa["status"] != "AWAITING_APPROVAL":
            raise SystemExit(
                f"La tarea crítica no se detuvo: {pausa['status']} {pausa.get('error')}"
            )
        aprobado = await cliente.post(
            f"{API}/tasks/{critica['job_id']}/approve",
            json={"aprobado": True, "comentario": "ok para el catálogo"},
        )
        aprobado.raise_for_status()
        print(f"  approve -> {aprobado.status_code} {aprobado.json()['status']}", flush=True)
        cierre = await _esperar(cliente, critica["job_id"], 600)
        print(f"  critica {cierre['status']}", flush=True)
        hilo = await cliente.get(f"{API}/conversations/novax-margen")
        hilo.raise_for_status()

    informe = {
        "upload": upload,
        "altas_ms": [item["alta_ms"] for item in estados],
        "resultados": estados,
        "upload_caso": {
            "alta_ms": upload_alta["alta_ms"],
            "estado": upload_estado,
        },
        "critica": {"alta_ms": critica["alta_ms"], "pausa": pausa, "cierre": cierre},
        "conversacion_margen": hilo.json()["respuesta_final"],
    }
    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    SALIDA.write_text(json.dumps(informe, ensure_ascii=False, indent=2), encoding="utf-8")
    fallidos = [item["caso"] for item in estados if item["status"] != "DONE"]
    if fallidos or cierre["status"] != "DONE":
        raise SystemExit(f"Corrida incompleta: {fallidos} critica={cierre['status']}")
    print(f"Listo. Informe en {SALIDA}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
