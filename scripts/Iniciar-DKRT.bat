@echo off
REM Abre o terminal DKRT em janela NOVA (cmd separado do Cursor)
set "DKRT_ROOT=%~dp0.."
cd /d "%DKRT_ROOT%"

if not exist ".venv\Scripts\python.exe" (
    echo [DKRT] Ambiente virtual nao encontrado em:
    echo   %CD%
    echo.
    echo Execute no PowerShell:
    echo   py -3.11 -m venv .venv
    echo   .venv\Scripts\pip install -e .
    echo.
    pause
    exit /b 1
)

REM /D define a pasta de trabalho; evita erro de sintaxe com aspas no caminho
start "DKRT Terminal" /D "%CD%" cmd /k ".venv\Scripts\python.exe -m context_broker_multiagent.terminal"
