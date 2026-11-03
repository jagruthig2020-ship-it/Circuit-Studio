@echo off
setlocal
cd /d "%~dp0"
echo.
echo =============================================
echo             CIRCUIT STUDIO
ECHO  One workbench. One local backend. No npm.
echo =============================================
echo.
where py >nul 2>nul
if %errorlevel% equ 0 (
 set "PY=py -3"
) else (
 set "PY=python"
)
%PY% -c "import fastapi, uvicorn, PIL, multipart" >nul 2>nul
if errorlevel 1 (
 echo Installing Python requirements. An internet connection is needed on first run.
 %PY% -m pip install -r backend\requirements.txt
 if errorlevel 1 (
   echo Dependency installation failed. Install Python 3.11+ and try again.
   pause
   exit /b 1
 )
)
start "" http://127.0.0.1:8000/
%PY% -m uvicorn backend.app:app --host 127.0.0.1 --port 8000
if errorlevel 1 pause
