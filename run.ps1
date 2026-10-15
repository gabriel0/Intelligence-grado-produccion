# The Intelligence System — control del stack local (Windows).
#
#   .\run.ps1 start   # prereqs + docker compose up (default)
#   .\run.ps1 stop    # docker compose down
#
# Requisitos start: Docker Desktop, Python 3.12, PINECONE_API_KEY en .env
# (Ollama solo si LLM/embeddings lo requieren)

param(
    [Parameter(Position = 0)]
    [ValidateSet("start", "stop")]
    [string]$Action = "start"
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

function Get-DotEnvValue([string]$Name) {
    if (-not (Test-Path ".env")) { return "" }
    foreach ($line in Get-Content ".env") {
        $trim = $line.Trim()
        if (-not $trim -or $trim.StartsWith("#")) { continue }
        $parts = $trim -split "=", 2
        if ($parts.Count -eq 2 -and $parts[0].Trim() -eq $Name) {
            return $parts[1].Trim().Trim('"').Trim("'")
        }
    }
    return ""
}

function Test-DockerEngine {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        Write-Host "No encuentro 'docker' en el PATH. Instala Docker Desktop."
        exit 1
    }
    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    docker info *> $null
    $ok = ($LASTEXITCODE -eq 0)
    $ErrorActionPreference = $prevEap
    if (-not $ok) {
        Write-Host "Docker Desktop no esta corriendo (o el engine no responde)."
        Write-Host "Abri Docker Desktop, espera a que diga 'Engine running' y reintenta."
        exit 1
    }
}

function Invoke-Stop {
    Write-Host "==> Deteniendo Redis + Phoenix + API (Docker Compose)..."
    Test-DockerEngine
    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    docker compose down
    $code = $LASTEXITCODE
    $ErrorActionPreference = $prevEap
    if ($code -ne 0) {
        Write-Host "Fallo docker compose down."
        exit 1
    }
    Write-Host ""
    Write-Host "Stack detenido (contenedores Redis/Phoenix/API)."
    Write-Host "Ollama en el host, si estaba corriendo, no se toca."
}

function Invoke-Start {
    if (-not (Test-Path ".env")) {
        Copy-Item ".env.example" ".env"
        Write-Host "Se creo .env desde .env.example."
        Write-Host "Completa PINECONE_API_KEY (obligatorio) y GOOGLE_API_KEY si usas Gemini."
        Write-Host "Luego volve a ejecutar .\run.ps1 start"
        exit 1
    }

    $pineconeKey = Get-DotEnvValue "PINECONE_API_KEY"
    if ([string]::IsNullOrWhiteSpace($pineconeKey)) {
        Write-Host "Falta PINECONE_API_KEY en .env. Completala y volve a ejecutar."
        exit 1
    }

    $llmProvider = (Get-DotEnvValue "LLM_PROVIDER").ToLower()
    if ([string]::IsNullOrWhiteSpace($llmProvider)) { $llmProvider = "ollama" }
    $embedProvider = (Get-DotEnvValue "EMBEDDING_PROVIDER").ToLower()
    if ([string]::IsNullOrWhiteSpace($embedProvider)) {
        if ($llmProvider -eq "gemini") { $embedProvider = "google" } else { $embedProvider = "ollama" }
    }
    $needsOllama = ($llmProvider -eq "ollama") -or ($embedProvider -eq "ollama")

    if ($llmProvider -eq "gemini") {
        $googleKey = Get-DotEnvValue "GOOGLE_API_KEY"
        if ([string]::IsNullOrWhiteSpace($googleKey)) {
            Write-Host "LLM_PROVIDER=gemini requiere GOOGLE_API_KEY en .env."
            exit 1
        }
    }

    Write-Host "==> Comprobando Docker Desktop..."
    Test-DockerEngine

    if (-not (Test-Path ".venv\Scripts\python.exe")) {
        Write-Host "Creando venv..."
        py -3.12 -m venv .venv
        .\.venv\Scripts\python.exe -m pip install -q -r requirements.txt
    } else {
        Write-Host "Actualizando dependencias del venv..."
        .\.venv\Scripts\python.exe -m pip install -q -r requirements.txt
    }

    New-Item -ItemType Directory -Force -Path "data", "artifacts", "trazas" | Out-Null

    if ($needsOllama) {
        Write-Host "==> Ollama (host) + modelos..."
        .\.venv\Scripts\python.exe levantar.py --solo-ollama
    } else {
        Write-Host "==> Sin Ollama (LLM=$llmProvider, embeddings=$embedProvider)"
    }

    Write-Host "==> Redis + Phoenix + API (Docker Compose)..."
    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    docker compose up --build -d
    $composeOk = ($LASTEXITCODE -eq 0)
    $ErrorActionPreference = $prevEap
    if (-not $composeOk) {
        Write-Host "Fallo docker compose. Revisa Docker Desktop y los logs de arriba."
        exit 1
    }

    Write-Host ""
    Write-Host "Listo."
    Write-Host "  API Swagger : http://127.0.0.1:8000/docs"
    Write-Host "  Phoenix     : http://127.0.0.1:6006"
    Write-Host "  Health      : http://127.0.0.1:8000/health"
    Write-Host "  Documentos  : POST/GET http://127.0.0.1:8000/documentos"
    Write-Host "  Reindex     : POST http://127.0.0.1:8000/reindex"
    Write-Host ""
    Write-Host "Pruebas:  .\.venv\Scripts\python.exe correr_carga.py"
    Write-Host "Logs:     docker compose logs -f api"
    Write-Host "Parar:    .\run.ps1 stop"
}

switch ($Action) {
    "stop" { Invoke-Stop }
    default { Invoke-Start }
}
