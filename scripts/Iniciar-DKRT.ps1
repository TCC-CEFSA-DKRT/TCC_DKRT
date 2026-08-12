# Inicia o terminal DKRT garantindo que o Ollama esteja online
# e encerra o Ollama automaticamente ao sair (somente se foi este script quem o subiu)

$ErrorActionPreference = 'Continue'
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $Root

$Python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    Write-Host "[DKRT] Ambiente virtual ausente em $Root" -ForegroundColor Yellow
    Write-Host "       Execute: py -3.11 -m venv .venv; .\.venv\Scripts\pip install -e ." -ForegroundColor Yellow
    Read-Host "Pressione ENTER para sair"
    exit 1
}

& $Python -c "import context_broker_agent" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "[DKRT] Pacote context_broker_agent nao instalado no venv." -ForegroundColor Yellow
    Write-Host "       Execute: .\.venv\Scripts\pip install -e ." -ForegroundColor Yellow
    Write-Host "       Se persistir, remova .venv\Lib\site-packages\~ontext* e reinstale." -ForegroundColor Yellow
    Read-Host "Pressione ENTER para sair"
    exit 1
}

function Test-Ollama {
    try {
        Invoke-WebRequest -Uri "http://localhost:11434/api/tags" -UseBasicParsing -TimeoutSec 2 | Out-Null
        return $true
    } catch {
        return $false
    }
}

$DkrtStartedOllama = $false

if (Test-Ollama) {
    Write-Host "[DKRT] Ollama ja esta rodando (reutilizando)." -ForegroundColor DarkGray
} else {
    $ollamaCmd = Get-Command ollama -ErrorAction SilentlyContinue
    if (-not $ollamaCmd) {
        Write-Host "[DKRT] Ollama nao encontrado no PATH. Instale: https://ollama.com" -ForegroundColor Yellow
        Write-Host "[DKRT] Seguindo sem SLM (modo heuristico simplificado)." -ForegroundColor Yellow
    } else {
        Write-Host "[DKRT] Iniciando Ollama em segundo plano..." -ForegroundColor Cyan
        $logOut = Join-Path $env:TEMP "dkrt-ollama.log"
        $logErr = Join-Path $env:TEMP "dkrt-ollama.err"
        Start-Process -FilePath "ollama" -ArgumentList "serve" -WindowStyle Hidden `
            -RedirectStandardOutput $logOut -RedirectStandardError $logErr `
            -ErrorAction SilentlyContinue | Out-Null
        $DkrtStartedOllama = $true

        $ready = $false
        for ($i = 0; $i -lt 60; $i++) {
            Start-Sleep -Milliseconds 500
            if (Test-Ollama) { $ready = $true; break }
        }
        if ($ready) {
            Write-Host "[DKRT] Ollama pronto." -ForegroundColor Green
        } else {
            Write-Host "[DKRT] Ollama nao respondeu em 30s, seguindo mesmo assim." -ForegroundColor Yellow
        }
    }
}

Write-Host ""

try {
    & $Python -m context_broker_agent.terminal
} finally {
    if ($DkrtStartedOllama) {
        Write-Host ""
        Write-Host "[DKRT] Encerrando Ollama iniciado por esta sessao..." -ForegroundColor DarkGray
        & taskkill.exe /F /T /IM ollama.exe 2>$null | Out-Null
    }
}
