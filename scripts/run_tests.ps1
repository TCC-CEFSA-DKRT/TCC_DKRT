# Executa testes DKRT (sem integração Orion)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..
$py = Join-Path $PSScriptRoot "..\.venv\Scripts\python.exe"
if (-not (Test-Path $py)) { Write-Error "Execute scripts\setup_windows.ps1 primeiro."; exit 1 }
& $py -m pytest tests/ -v -m "not integration"
