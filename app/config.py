import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
TRAZAS = ROOT / "trazas"
ARTIFACTS = ROOT / "artifacts"
CHUNKS_PATH = ARTIFACTS / "chunks.json"

AJUSTES_PATH = DATA / "ajustes.jsonl"

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "ollama").strip().lower()

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:14b")
EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "all-minilm")
OLLAMA_KEEP_ALIVE = os.getenv("OLLAMA_KEEP_ALIVE", "2m")

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash").strip()
GOOGLE_EMBED_MODEL = os.getenv("GOOGLE_EMBED_MODEL", "gemini-embedding-001").strip()
GOOGLE_EMBED_DIMS = int(os.getenv("GOOGLE_EMBED_DIMS", "1536"))

# Con Gemini, por defecto embeddings también van a Google (sin Ollama).
# Podés forzar ollama con EMBEDDING_PROVIDER=ollama (híbrido).
_default_embed = "google" if LLM_PROVIDER == "gemini" else "ollama"
EMBEDDING_PROVIDER = os.getenv("EMBEDDING_PROVIDER", _default_embed).strip().lower()

PINECONE_API_KEY = os.getenv("PINECONE_API_KEY", "").strip()
_default_index = (
    "intelligence-system-gemini"
    if EMBEDDING_PROVIDER == "google"
    else "intelligence-system"
)
INDEX_NAME = os.getenv("INDEX_NAME", _default_index).strip()
PINECONE_NAMESPACE = os.getenv("PINECONE_NAMESPACE", "intelligence-system").strip()
PINECONE_CLOUD = os.getenv("PINECONE_CLOUD", "aws").strip()
PINECONE_REGION = os.getenv("PINECONE_REGION", "us-east-1").strip()

CHUNK_SIZE_TOKENS = int(os.getenv("CHUNK_SIZE_TOKENS", "600"))
CHUNK_OVERLAP_TOKENS = int(os.getenv("CHUNK_OVERLAP_TOKENS", "80"))
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", str(2 * 1024 * 1024)))

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
PHOENIX_URL = os.getenv("PHOENIX_URL", "http://127.0.0.1:6006").rstrip("/")
PHOENIX_ENDPOINT = os.getenv("PHOENIX_ENDPOINT", "http://127.0.0.1:6006/v1/traces")
PHOENIX_PROJECT = os.getenv("PHOENIX_PROJECT", "intelligence-system")

API_HOST = os.getenv("API_HOST", "127.0.0.1")
API_PORT = int(os.getenv("API_PORT", "8000"))

MAX_PASOS = int(os.getenv("MAX_PASOS", "4"))
MAX_VISITAS = int(os.getenv("MAX_VISITAS", "2"))
TOP_K = int(os.getenv("TOP_K", "4"))
VERSION_PROMPT = os.getenv("PROMPT_VERSION", "intelligence-system-v1")
JOB_TIMEOUT = int(os.getenv("JOB_TIMEOUT", "600"))

_default_in = "0.10" if LLM_PROVIDER == "gemini" else "2"
_default_out = "0.40" if LLM_PROVIDER == "gemini" else "8"
COSTO_ENTRADA_POR_MILLON = float(os.getenv("COSTO_ENTRADA_POR_MILLON", _default_in))
COSTO_SALIDA_POR_MILLON = float(os.getenv("COSTO_SALIDA_POR_MILLON", _default_out))

if LLM_PROVIDER not in {"ollama", "gemini"}:
    raise RuntimeError(f"LLM_PROVIDER inválido: {LLM_PROVIDER!r}. Usá ollama o gemini.")

if EMBEDDING_PROVIDER not in {"ollama", "google"}:
    raise RuntimeError(
        f"EMBEDDING_PROVIDER inválido: {EMBEDDING_PROVIDER!r}. Usá ollama o google."
    )

if EMBEDDING_PROVIDER == "google":
    ACTIVE_EMBED_MODEL = GOOGLE_EMBED_MODEL
    EMBED_DIMENSIONS = GOOGLE_EMBED_DIMS
else:
    ACTIVE_EMBED_MODEL = EMBED_MODEL
    EMBED_DIMENSIONS = 384


def necesita_ollama() -> bool:
    """True si el chat o los embeddings dependen de Ollama en el host."""
    return LLM_PROVIDER == "ollama" or EMBEDDING_PROVIDER == "ollama"


QUEUE_NAME = "intel:tareas"
JOB_PREFIX = "intel:job:"

PRECIO_FICHA = 89990.0
COSTO_FICHA = 40000.0


def require_env(*names: str) -> None:
    missing = [name for name in names if not os.getenv(name, "").strip()]
    if missing:
        joined = ", ".join(missing)
        raise RuntimeError(
            f"Faltan variables en .env: {joined}. "
            "Copiá .env.example a .env y completá las claves."
        )
