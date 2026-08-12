@echo off
title DKRT Terminal
setlocal
set "DKRT_ROOT=%~dp0.."
cd /d "%DKRT_ROOT%"

if not exist ".venv\Scripts\python.exe" goto :no_venv

".venv\Scripts\python.exe" -c "import context_broker_agent" >nul 2>&1
if errorlevel 1 goto :no_package

REM Le SLM_PROVIDER do .env para decidir o caminho de inicializacao.
set "DKRT_PROVIDER="
for /f "tokens=2 delims==" %%V in ('findstr /b "SLM_PROVIDER=" .env 2^>nul') do set "DKRT_PROVIDER=%%V"
for /f "tokens=* delims= " %%T in ("%DKRT_PROVIDER%") do set "DKRT_PROVIDER=%%T"

if /i "%DKRT_PROVIDER%"=="llama_cpp" goto :llama_cpp_path

REM ============================================================
REM Caminho OLLAMA
REM ============================================================
set "DKRT_STARTED_OLLAMA="

REM Já está respondendo?
powershell -NoProfile -Command "try { (Invoke-WebRequest -Uri 'http://127.0.0.1:11434/api/tags' -UseBasicParsing -TimeoutSec 2).StatusCode | Out-Null; exit 0 } catch { exit 1 }" >nul 2>&1
if not errorlevel 1 (
    echo [DKRT] Ollama ja estava rodando ^(reutilizando^).
    goto :run
)

where ollama >nul 2>&1
if errorlevel 1 (
    echo [DKRT] Ollama nao encontrado no PATH. Instale em https://ollama.com
    echo [DKRT] Ou use SLM_PROVIDER=llama_cpp no .env
    echo [DKRT] Seguindo sem SLM ^(modo heuristico^).
    goto :run
)

echo [DKRT] Iniciando Ollama em segundo plano...

REM Inicia sem redirecionar stdin/stdout de forma que o Ollama aborte.
REM Logs vão para arquivos separados via PowerShell.
powershell -NoProfile -Command ^
  "Start-Process -FilePath 'ollama' -ArgumentList 'serve' -WindowStyle Hidden -RedirectStandardOutput ('$env:TEMP\dkrt-ollama.log') -RedirectStandardError ('$env:TEMP\dkrt-ollama.err')" >nul 2>&1

set "DKRT_STARTED_OLLAMA=1"

echo [DKRT] Aguardando Ollama (ate ~45s)...
powershell -NoProfile -Command ^
  "$ok=$false; for($i=0;$i -lt 90;$i++){ try{ $r=Invoke-WebRequest -Uri 'http://127.0.0.1:11434/api/tags' -UseBasicParsing -TimeoutSec 1; if($r.StatusCode -eq 200){$ok=$true; break} } catch{}; Start-Sleep -Milliseconds 500 }; if($ok){exit 0}else{exit 1}" >nul 2>&1

if errorlevel 1 (
    echo [DKRT] Ollama nao respondeu a tempo.
    echo [DKRT] Veja: %TEMP%\dkrt-ollama.err  e  %TEMP%\dkrt-ollama.log
    echo [DKRT] Continuando em modo heuristico.
) else (
    echo [DKRT] Ollama pronto.
)
goto :run

:ollama_missing
echo [DKRT] Ollama nao encontrado no PATH. Instale em https://ollama.com
echo [DKRT] Ou troque para llama.cpp no .env: SLM_PROVIDER=llama_cpp
echo [DKRT] Seguindo sem SLM ^(modo heuristico simplificado^).
goto :run

:ollama_ok
echo [DKRT] Ollama ja estava rodando ^(reutilizando^).
goto :run

REM ============================================================
REM Caminho LLAMA.CPP: sem daemon. So checa o GGUF e segue.
REM ============================================================
:llama_cpp_path
echo [DKRT] Backend SLM: llama.cpp ^(in-process, sem daemon^).

REM Verifica se o pacote llama-cpp-python esta instalado.
".venv\Scripts\python.exe" -c "import llama_cpp" >nul 2>&1
if errorlevel 1 (
    echo [DKRT] llama-cpp-python ausente. Instale com:
    echo        .\.venv\Scripts\pip install -e ".[slm-cpp]"
    echo [DKRT] Continuando em modo heuristico.
    goto :run
)

REM Verifica se o GGUF default esta presente (ou usuario configurou outro path).
set "DKRT_DEFAULT_GGUF=models\qwen2.5-3b-instruct-q4_k_m.gguf"
if not exist "%DKRT_DEFAULT_GGUF%" (
    echo [DKRT] Modelo GGUF nao encontrado em %DKRT_DEFAULT_GGUF%
    echo [DKRT] Baixe com: .\.venv\Scripts\python scripts\download_qwen_gguf.py
    echo [DKRT] Continuando em modo heuristico ate o modelo ser instalado.
) else (
    echo [DKRT] Modelo GGUF pronto: %DKRT_DEFAULT_GGUF%
)
goto :run

REM ============================================================
:run
echo.
".venv\Scripts\python.exe" -m context_broker_agent.terminal
set "DKRT_EXIT=%errorlevel%"

if defined DKRT_STARTED_OLLAMA (
    echo.
    echo [DKRT] Encerrando Ollama iniciado por esta sessao...
    taskkill /F /T /IM ollama.exe >nul 2>&1
)

endlocal & exit /b %DKRT_EXIT%

:no_venv
echo [DKRT] Ambiente virtual nao encontrado em %CD%.
echo.
echo Execute no PowerShell:
echo   py -3.11 -m venv .venv
echo   .venv\Scripts\pip install -e .
echo.
pause
exit /b 1

:no_package
echo [DKRT] Pacote context_broker_agent nao instalado no venv.
echo.
echo Execute no PowerShell ^(na pasta do projeto^):
echo   .venv\Scripts\pip install -e .
echo.
echo Se o erro persistir, remova pastas corrompidas em:
echo   .venv\Lib\site-packages\~ontext*
echo   e reinstale com o comando acima.
echo.
pause
exit /b 1
