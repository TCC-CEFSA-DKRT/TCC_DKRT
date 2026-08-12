# Launcher do terminal DKRT (Windows)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    Write-Host "Crie o venv: py -3.11 -m venv .venv && pip install -e ." -ForegroundColor Yellow
    exit 1
}
& $Python -m context_broker_agent.terminal @args
