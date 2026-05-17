# Setup automatizado de la plataforma BPMN en Windows.
# Requisitos previos:
#   - Python 3.11+ instalado y en el PATH (https://www.python.org/downloads/windows/).
#   - PowerShell 5.1+ (incluido en Windows 10/11).
#
# Uso:
#   1. Abrir PowerShell en la raiz del repositorio.
#   2. (Una sola vez) habilitar scripts:
#        Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
#   3. .\scripts\setup_windows.ps1

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot

Write-Host "==> Creando entorno virtual (.venv)..." -ForegroundColor Cyan
if (-Not (Test-Path "$ProjectRoot\.venv")) {
    python -m venv "$ProjectRoot\.venv"
} else {
    Write-Host "    Entorno .venv ya existe, se reutiliza."
}

$activate = Join-Path $ProjectRoot ".venv\Scripts\Activate.ps1"
Write-Host "==> Activando entorno virtual..." -ForegroundColor Cyan
. $activate

Write-Host "==> Actualizando pip..." -ForegroundColor Cyan
python -m pip install --upgrade pip

Write-Host "==> Instalando dependencias del proyecto..." -ForegroundColor Cyan
pip install -e "$ProjectRoot[dev]"

Write-Host ""
Write-Host "Setup completo." -ForegroundColor Green
Write-Host "Para ejecutar la app:"            -ForegroundColor Yellow
Write-Host "    .\.venv\Scripts\Activate.ps1" -ForegroundColor Yellow
Write-Host "    bpmn-platform"                -ForegroundColor Yellow
Write-Host ""
Write-Host "Para generar solo la plantilla Excel:" -ForegroundColor Yellow
Write-Host "    bpmn-template -o plantilla_bpmn.xlsx" -ForegroundColor Yellow
