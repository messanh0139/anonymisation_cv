@echo off
:: lancer.bat - Pipeline anonymisation CVs (Windows)
::
:: Prerequis :
::   - Python 3.11+ avec venv dans .venv\
::   - MiKTeX ou TeX Live (pdflatex dans le PATH)
::   - curl disponible (natif Windows 10/11 >= 1803)
::   - Fichiers credentials\ presents et config.yaml configure
::
:: Usage : lancer.bat [commande]
::
:: Commandes :
::   start    -> Demarrer le serveur FastAPI
::   stop     -> Arreter le serveur
::   status   -> Verifier l'etat du serveur
::   process  -> Extraire + anonymiser les CVs Drive
::   generate -> Generer les PDFs LaTeX
::   all      -> process + generate
::   run      -> start + process + generate  (defaut)

setlocal enabledelayedexpansion
cd /d "%~dp0"

set API=http://localhost:8000
set UVICORN=.venv\Scripts\uvicorn.exe
set LOG=%TEMP%\uvicorn_anonymi.log
set CMD=%~1
if "%CMD%"=="" set CMD=run

echo.
echo ============================================
echo    Pipeline anonymi_cv
echo ============================================
echo.

if /i "%CMD%"=="start"    goto do_start
if /i "%CMD%"=="stop"     goto do_stop
if /i "%CMD%"=="status"   goto do_status
if /i "%CMD%"=="process"  goto do_process
if /i "%CMD%"=="generate" goto do_generate
if /i "%CMD%"=="all"      goto do_all
if /i "%CMD%"=="reset"    goto do_reset
if /i "%CMD%"=="run"      goto do_run

echo [ERREUR] Commande inconnue : %CMD%
echo Commandes : start stop status process generate all run
exit /b 1

:do_start
call :fn_start
goto :end

:do_stop
echo [>>] Arret du serveur port 8000...
for /f "tokens=5" %%a in ('netstat -aon 2^>nul ^| findstr ":8000 "') do (
    taskkill /F /PID %%a >nul 2>&1
)
echo [OK] Serveur arrete
goto :end

:do_status
call :fn_check_server
if "%SERVER_UP%"=="1" (
    echo [OK] Serveur actif sur %API%
) else (
    echo [--] Serveur non disponible
)
goto :end

:do_process
call :fn_require_server
echo [>>] Extraction + anonymisation...
curl -s -X POST %API%/process | .venv\Scripts\python.exe -m json.tool
echo.
echo [OK] Traitement termine
goto :end

:do_generate
call :fn_require_server
call :fn_delete_pdfs
echo [>>] Generation des PDFs LaTeX...
curl -s -X POST %API%/generate-pdfs | .venv\Scripts\python.exe -m json.tool
echo.
echo [OK] PDFs generes
goto :end

:do_all
call :fn_require_server
echo [>>] Etape 1/2 - Extraction + anonymisation...
curl -s -X POST %API%/process | .venv\Scripts\python.exe -m json.tool
echo.
call :fn_delete_pdfs
echo [>>] Etape 2/2 - Generation des PDFs...
curl -s -X POST %API%/generate-pdfs | .venv\Scripts\python.exe -m json.tool
echo.
echo [OK] Pipeline complet termine
goto :end

:do_reset
call :fn_require_server
call :fn_delete_pdfs
echo [>>] Regeneration des PDFs...
curl -s -X POST %API%/generate-pdfs | .venv\Scripts\python.exe -m json.tool
echo.
echo [OK] Reset termine
goto :end

:do_run
call :fn_start
echo.
echo [>>] Etape 1/2 - Extraction + anonymisation...
curl -s -X POST %API%/process | .venv\Scripts\python.exe -m json.tool
echo.
call :fn_delete_pdfs
echo [>>] Etape 2/2 - Generation des PDFs...
curl -s -X POST %API%/generate-pdfs | .venv\Scripts\python.exe -m json.tool
echo.
echo ============================================
echo [OK] Termine - PDFs disponibles sur Drive
echo ============================================
goto :end

:: --- Fonctions ---

:fn_delete_pdfs
echo [>>] Suppression des PDFs existants sur Drive...
.venv\Scripts\python.exe -c "import sys; sys.path.insert(0,'.'); from app.drive_client import get_drive_service, list_files_in_folder; from app.config_loader import CFG; FOLDER=CFG.get('drive',{}).get('output_folder_id',''); svc=get_drive_service(); pdfs=[f for f in list_files_in_folder(svc,FOLDER) if f['name'].endswith('.pdf')]; [svc.files().delete(fileId=f['id']).execute() or print('  [del]',f['name']) for f in pdfs]; print('Supprimes :',len(pdfs),'fichier(s)')"
exit /b 0

:fn_check_server
set SERVER_UP=0
curl -s --max-time 2 %API%/ >nul 2>&1
if not errorlevel 1 set SERVER_UP=1
exit /b 0

:fn_start
call :fn_check_server
if "%SERVER_UP%"=="1" (
    echo [OK] Serveur deja actif sur %API%
    exit /b 0
)
echo [>>] Demarrage du serveur FastAPI...
if not exist "%UVICORN%" (
    echo [ERREUR] uvicorn introuvable : %UVICORN%
    echo Creez le venv : python -m venv .venv
    echo Puis : .venv\Scripts\pip install -r requirements.txt
    exit /b 1
)
start /b "" "%UVICORN%" app.main_cloud:app --host 0.0.0.0 --port 8000 >> "%LOG%" 2>&1
echo [>>] Attente demarrage (5 secondes)...
timeout /t 5 /nobreak >nul
call :fn_check_server
if "%SERVER_UP%"=="1" (
    echo [OK] Serveur demarre sur %API%
) else (
    echo [ERREUR] Serveur non demarre. Logs : %LOG%
    exit /b 1
)
exit /b 0

:fn_require_server
call :fn_check_server
if "%SERVER_UP%"=="0" (
    echo [ERREUR] Serveur non disponible. Lancez : lancer.bat start
    exit /b 1
)
exit /b 0

:end
echo.
endlocal
