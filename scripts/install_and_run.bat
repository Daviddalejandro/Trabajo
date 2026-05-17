@echo off
REM ============================================================
REM  BPMN Platform - Instalador y lanzador one-click para Windows
REM  Requisitos: Anaconda instalado (con conda en el PATH).
REM
REM  Uso: doble clic sobre este archivo desde Explorador.
REM       O, desde un Anaconda Prompt:  scripts\install_and_run.bat
REM ============================================================

setlocal EnableDelayedExpansion

echo.
echo ============================================================
echo  BPMN Platform - Setup automatico con Anaconda
echo ============================================================
echo.

REM --- 1) Verificar conda en el PATH -------------------------
where conda >nul 2>&1
if errorlevel 1 (
    echo [ERROR] 'conda' no esta en el PATH.
    echo.
    echo Soluciones:
    echo   - Cierra esta ventana y vuelve a abrirla desde
    echo     "Anaconda Prompt" en el menu Inicio.
    echo   - O agrega Anaconda al PATH:
    echo     Inicio ^> Editar variables de entorno del sistema ^>
    echo     PATH ^> agregar  C:\Users\TU_USER\Anaconda3\Scripts
    echo.
    pause
    exit /b 1
)
echo [OK] conda detectado.

REM --- 2) Carpeta de trabajo ---------------------------------
set "REPO_DIR=%~dp0.."
pushd "%REPO_DIR%"
echo [OK] Repositorio: %CD%
echo.

REM --- 3) Crear entorno conda 'bpmn' si no existe ------------
echo Buscando entorno conda 'bpmn'...
call conda env list | findstr /R /C:"^bpmn " >nul 2>&1
if errorlevel 1 (
    echo [INFO] Creando entorno 'bpmn' con Python 3.11 ^(toma 1-2 min^)...
    call conda create -n bpmn python=3.11 -y
    if errorlevel 1 (
        echo [ERROR] No se pudo crear el entorno conda.
        pause
        exit /b 1
    )
) else (
    echo [OK] Entorno 'bpmn' ya existe.
)
echo.

REM --- 4) Instalar la app en modo editable -------------------
echo [INFO] Instalando dependencias en el entorno 'bpmn'...
echo        (esto toma 2-3 min la primera vez)
echo.
call conda run -n bpmn --no-capture-output pip install -e .
if errorlevel 1 (
    echo [ERROR] Fallo la instalacion de dependencias.
    pause
    exit /b 1
)
echo.
echo [OK] Instalacion completa.
echo.

REM --- 5) Lanzar la app --------------------------------------
echo ============================================================
echo  Lanzando BPMN Platform...
echo  Si la ventana no aparece, revisa la consola por errores.
echo ============================================================
echo.
call conda run -n bpmn --no-capture-output python -m bpmn_platform
if errorlevel 1 (
    echo.
    echo [ERROR] La app cerro con error. Revisa el traceback de arriba.
    pause
    exit /b 1
)

popd
echo.
echo La app se cerro. Para volver a lanzarla, basta con doble clic
echo a este mismo archivo, o desde Anaconda Prompt:
echo     conda activate bpmn
echo     bpmn-platform
echo.
pause
endlocal
