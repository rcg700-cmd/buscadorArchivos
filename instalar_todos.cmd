@echo off
rem Instalador para TODOS los usuarios (requiere ejecutarlo como administrador).
rem 1) Copia dist\buscador.exe a C:\Program Files\Buscador\
rem 2) Copia LEAME.txt junto al exe
rem 3) Crea C:\Windows\buscador.bat (C:\Windows esta en el PATH del sistema,
rem    asi cualquier usuario puede escribir "buscador" en CMD o PowerShell)
rem 4) Crea el acceso directo global en el menu Inicio (ProgramData)
setlocal
cd /d "%~dp0"

rem ---- comprobar permisos de administrador ----
net session >nul 2>&1
if errorlevel 1 (
  echo.
  echo Este instalador necesita permisos de administrador.
  echo Haz clic derecho sobre instalar_todos.cmd y elige "Ejecutar como administrador".
  exit /b 1
)

if not exist "dist\buscador.exe" (
  echo.
  echo No se encontro dist\buscador.exe. Compilalo primero con:
  echo   python -m PyInstaller --onefile --console --name buscador --clean --noconfirm --paths . buscador_exe.py --exclude-module PIL --exclude-module tkinter --exclude-module jedi --exclude-module IPython --exclude-module matplotlib --exclude-module numpy --exclude-module pandas --exclude-module pytest --exclude-module setuptools
  exit /b 1
)

set "DESTINO=C:\Program Files\Buscador"

echo [1/4] Copiando buscador.exe a "%DESTINO%"...
if not exist "%DESTINO%" mkdir "%DESTINO%"
copy /y "dist\buscador.exe" "%DESTINO%\buscador.exe" >nul
if errorlevel 1 goto :error

echo [2/4] Copiando LEAME.txt...
if exist "LEAME.txt" copy /y "LEAME.txt" "%DESTINO%\LEAME.txt" >nul

echo [3/4] Creando el comando global C:\Windows\buscador.bat ...
> "C:\Windows\buscador.bat" (
  echo @echo off
  echo "C:\Program Files\Buscador\buscador.exe" %%*
)
if errorlevel 1 goto :error

echo [4/4] Creando acceso directo en el menu Inicio (todos los usuarios)...
powershell -NoProfile -Command "$s=(New-Object -ComObject WScript.Shell).CreateShortcut('C:\ProgramData\Microsoft\Windows\Start Menu\Programs\Buscador de archivos.lnk');$s.TargetPath='C:\Program Files\Buscador\buscador.exe';$s.WorkingDirectory='C:\Program Files\Buscador';$s.Save()"

echo.
echo Listo. Con cualquier usuario de esta PC, abre CMD/PowerShell y escribe:  buscador
echo (con carpeta concreta:  buscador "D:\Docs"^)
echo Tambien queda "Buscador de archivos" en el menu Inicio.
exit /b 0

:error
echo.
echo La instalacion no se completo (¿carpeta protegida, antivirus?).
echo Alternativa manual: ejecutar dist\buscador.exe directamente.
exit /b 1
