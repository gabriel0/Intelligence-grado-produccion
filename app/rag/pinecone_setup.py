import os
import time

from pinecone import Pinecone, ServerlessSpec

from app.config import (
    ACTIVE_EMBED_MODEL,
    INDEX_NAME,
    PINECONE_API_KEY,
    PINECONE_CLOUD,
    PINECONE_NAMESPACE,
    PINECONE_REGION,
    require_env,
)


def pinecone_client() -> Pinecone:
    if PINECONE_API_KEY:
        return Pinecone(api_key=PINECONE_API_KEY)
    require_env("PINECONE_API_KEY")
    return Pinecone(api_key=os.environ["PINECONE_API_KEY"])


def _dimension(description) -> int | None:
    dimension = getattr(description, "dimension", None)
    if dimension is None and isinstance(description, dict):
        dimension = description.get("dimension")
    return dimension


def _create_index(pc: Pinecone, dimension: int) -> None:
    print(
        f"Creando índice '{INDEX_NAME}' "
        f"({dimension} dims, {PINECONE_CLOUD}/{PINECONE_REGION})...",
        flush=True,
    )
    pc.create_index(
        name=INDEX_NAME,
        dimension=dimension,
        metric="cosine",
        spec=ServerlessSpec(cloud=PINECONE_CLOUD, region=PINECONE_REGION),
    )


def ensure_index(dimension: int) -> str:
    """Crea el índice serverless si no existe y alinea la dimensión del encoder."""
    pc = pinecone_client()
    names = pc.list_indexes().names()

    if INDEX_NAME in names:
        current = _dimension(pc.describe_index(INDEX_NAME))
        if current != dimension:
            print(
                f"El índice '{INDEX_NAME}' tiene {current} dims y "
                f"{ACTIVE_EMBED_MODEL} genera {dimension}. Se recrea.",
                flush=True,
            )
            pc.delete_index(INDEX_NAME)
            while INDEX_NAME in pc.list_indexes().names():
                time.sleep(1)
            names = []
        else:
            print(f"El índice '{INDEX_NAME}' ya existe.", flush=True)

    if INDEX_NAME not in names:
        _create_index(pc, dimension)
        while INDEX_NAME not in pc.list_indexes().names():
            time.sleep(1)

    description = pc.describe_index(INDEX_NAME)
    created = _dimension(description)
    if created != dimension:
        raise RuntimeError(
            f"El índice '{INDEX_NAME}' quedó en {created} dims, "
            f"pero {ACTIVE_EMBED_MODEL} genera {dimension}."
        )

    print(f"Índice listo. Namespace de trabajo: '{PINECONE_NAMESPACE}'.", flush=True)
    return INDEX_NAME


def index_handle():
    return pinecone_client().Index(INDEX_NAME)
