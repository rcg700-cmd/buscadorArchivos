@echo off
rem Instalador para Windows: ejecutar con "instalar.cmd" desde la carpeta del proyecto.
rem Deja el comando "buscador" disponible en CMD y PowerShell.
setlocal
cd /d "%~dp0"

echo [1/2] Instalando dependencias...
python -m pip install -r requirements.txt
if errorlevel 1 goto :error

echo [2/2] Creando el comando "buscador"...
rem Copia un lanzador a WindowsApps, que esta en el PATH del usuario
set "ALIAS=%LOCALAPPDATA%\Microsoft\WindowsApps\buscador.bat"
> "%ALIAS%" (
  echo @echo off
  echo set "PYTHONPATH=%%PYTHONPATH%%;%~dp0"
  echo python -m buscador %%*
)
if errorlevel 1 goto :error

if exist "%ALIAS%" (
  echo.
  echo Listo. Abre un CMD o PowerShell y ejecuta:  buscador
  echo (con carpeta concreta:  buscador "D:\Docs"^)
  exit /b 0
)

:error
echo.
echo La instalacion no se completó. Alternativa manual: abre la carpeta y ejecuta
echo   python -m buscador
exit /b 1
