# Abre o terminal DKRT em nova janela do Windows Terminal ou PowerShell
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$Python = Join-Path $Root ".venv\Scripts\python.exe"

if (-not (Test-Path $Python)) {
    Write-Host "Ambiente virtual ausente. Rode: py -3.11 -m venv .venv; pip install -e ." -ForegroundColor Yellow
    exit 1
}

$cmd = "Set-Location '$Root'; & '$Python' -m context_broker_multiagent.terminal"

# Nova janela PowerShell dedicada
Start-Process powershell.exe -ArgumentList "-NoExit", "-Command", $cmd -WorkingDirectory $Root
