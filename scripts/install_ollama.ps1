# Instalacion guiada de Ollama (motor IA local, offline-first) en Windows.
#
# Este script NO instala Ollama de forma silenciosa: solo abre el instalador
# oficial y orienta al usuario. Es la forma segura recomendada por Ollama.
#
# Uso:
#   .\scripts\install_ollama.ps1            # descarga e instala
#   .\scripts\install_ollama.ps1 -OnlyModel # solo descarga el modelo

param(
    [switch]$OnlyModel,
    [string]$Model = "llama3.1:8b"
)

$ErrorActionPreference = "Stop"
$installerUrl = "https://ollama.com/download/OllamaSetup.exe"
$installerPath = Join-Path $env:TEMP "OllamaSetup.exe"

if (-Not $OnlyModel) {
    Write-Host "==> Descargando instalador oficial de Ollama..." -ForegroundColor Cyan
    Invoke-WebRequest -Uri $installerUrl -OutFile $installerPath

    Write-Host "==> Ejecutando instalador (acepte los prompts del sistema)..." -ForegroundColor Cyan
    Start-Process -FilePath $installerPath -Wait
    Write-Host "Instalacion finalizada." -ForegroundColor Green
}

Write-Host ""
Write-Host "==> Descargando modelo '$Model'..." -ForegroundColor Cyan
Write-Host "    (puede tardar varios minutos la primera vez)"
ollama pull $Model

Write-Host ""
Write-Host "Listo. Para verificar:" -ForegroundColor Green
Write-Host "    ollama list" -ForegroundColor Yellow
Write-Host "    ollama run $Model 'Hola'" -ForegroundColor Yellow
