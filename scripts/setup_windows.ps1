# Setup DKRT no Windows (usa py launcher quando python nao esta no PATH)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..

if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
    Write-Host "Python nao encontrado. Instale Python 3.11+ de https://www.python.org/downloads/" -ForegroundColor Red
    Write-Host "Marque 'Add python.exe to PATH' no instalador." -ForegroundColor Yellow
    exit 1
}

Write-Host "Criando ambiente virtual..." -ForegroundColor Cyan
py -3.11 -m venv .venv

$python = Join-Path $PWD ".venv\Scripts\python.exe"
& $python -m pip install --upgrade pip
& $python -m pip install -e ".[dev]"

if (-not (Test-Path .env)) {
    Copy-Item .env.example .env
    Write-Host "Criado .env a partir de .env.example" -ForegroundColor Green
}

Write-Host "Gerando chunks RAG..." -ForegroundColor Cyan
& $python scripts/rag/chunk_hybrid.py knowledge/raw/ --out knowledge/chunks/ --category fiware

Write-Host ""
Write-Host "Setup concluido. Ative o ambiente:" -ForegroundColor Green
Write-Host "  .\.venv\Scripts\Activate.ps1" -ForegroundColor White
Write-Host ""
Write-Host "Comandos (com venv ativo):" -ForegroundColor Green
Write-Host "  dkrt                    # terminal interativo (principal)" -ForegroundColor White
Write-Host "  dkrt-tools query -t Sensor" -ForegroundColor White
Write-Host "  python -m pytest tests/ -v" -ForegroundColor White
Write-Host ""
Write-Host "Ou launcher direto:" -ForegroundColor Yellow
Write-Host "  .\scripts\dkrt-terminal.ps1" -ForegroundColor White
