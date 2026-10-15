#!/usr/bin/env bash
# The Intelligence System — control del stack local (Linux/macOS).
#   ./run.sh start   (default)
#   ./run.sh stop
set -euo pipefail
cd "$(dirname "$0")"

ACTION="${1:-start}"

docker_ok() {
  if ! command -v docker >/dev/null 2>&1; then
    echo "No encuentro 'docker' en el PATH. Instalá Docker y volvé a ejecutar."
    exit 1
  fi
  if ! docker info >/dev/null 2>&1; then
    echo "Docker no está corriendo (o el engine no responde)."
    exit 1
  fi
}

do_stop() {
  echo "==> Deteniendo Redis + Phoenix + API (Docker Compose)..."
  docker_ok
  docker compose down
  echo ""
  echo "Stack detenido (contenedores Redis/Phoenix/API)."
  echo "Ollama en el host, si estaba corriendo, no se toca."
}

do_start() {
  if [[ ! -f .env ]]; then
    cp .env.example .env
    echo "Se creó .env desde .env.example."
    echo "Completá PINECONE_API_KEY (obligatorio) y GOOGLE_API_KEY si usás Gemini."
    echo "Luego volvé a ejecutar ./run.sh start"
    exit 1
  fi

  pinecone_key="$(grep -E '^PINECONE_API_KEY=' .env | head -n1 | cut -d= -f2- | tr -d '\"' | tr -d "'" | xargs || true)"
  if [[ -z "${pinecone_key}" ]]; then
    echo "Falta PINECONE_API_KEY en .env. Completala y volvé a ejecutar."
    exit 1
  fi

  llm_provider="$(grep -E '^LLM_PROVIDER=' .env | head -n1 | cut -d= -f2- | tr -d '\"' | tr -d "'" | tr '[:upper:]' '[:lower:]' | xargs || true)"
  llm_provider="${llm_provider:-ollama}"
  embed_provider="$(grep -E '^EMBEDDING_PROVIDER=' .env | head -n1 | cut -d= -f2- | tr -d '\"' | tr -d "'" | tr '[:upper:]' '[:lower:]' | xargs || true)"
  if [[ -z "${embed_provider}" ]]; then
    if [[ "${llm_provider}" == "gemini" ]]; then embed_provider="google"; else embed_provider="ollama"; fi
  fi
  needs_ollama=0
  if [[ "${llm_provider}" == "ollama" || "${embed_provider}" == "ollama" ]]; then needs_ollama=1; fi

  if [[ "${llm_provider}" == "gemini" ]]; then
    google_key="$(grep -E '^GOOGLE_API_KEY=' .env | head -n1 | cut -d= -f2- | tr -d '\"' | tr -d "'" | xargs || true)"
    if [[ -z "${google_key}" ]]; then
      echo "LLM_PROVIDER=gemini requiere GOOGLE_API_KEY en .env."
      exit 1
    fi
  fi

  if [[ ! -x .venv/bin/python ]]; then
    echo "Creando venv..."
    python3.12 -m venv .venv
    .venv/bin/python -m pip install -q -r requirements.txt
  else
    echo "Actualizando dependencias del venv..."
    .venv/bin/python -m pip install -q -r requirements.txt
  fi

  echo "==> Comprobando Docker..."
  docker_ok
  mkdir -p data artifacts trazas

  if [[ "${needs_ollama}" -eq 1 ]]; then
    echo "==> Ollama (host) + modelos..."
    .venv/bin/python levantar.py --solo-ollama
  else
    echo "==> Sin Ollama (LLM=${llm_provider}, embeddings=${embed_provider})"
  fi

  echo "==> Redis + Phoenix + API (Docker Compose)..."
  docker compose up --build -d

  echo ""
  echo "Listo."
  echo "  API Swagger : http://127.0.0.1:8000/docs"
  echo "  Phoenix     : http://127.0.0.1:6006"
  echo "  Health      : http://127.0.0.1:8000/health"
  echo ""
  echo "Pruebas:  .venv/bin/python correr_carga.py"
  echo "Logs:     docker compose logs -f api"
  echo "Parar:    ./run.sh stop"
}

case "${ACTION}" in
  stop) do_stop ;;
  start) do_start ;;
  *)
    echo "Uso: ./run.sh [start|stop]"
    exit 1
    ;;
esac
