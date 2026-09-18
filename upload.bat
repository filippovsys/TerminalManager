@echo off
cd /d "%~dp0"

echo.
echo ==========================================
echo   UPLOAD TO GITHUB
echo ==========================================
echo.

git add .

git status

echo.
set /p MESSAGE=Enter commit message: 

if "%MESSAGE%"=="" set MESSAGE=Update project

git commit -m "%MESSAGE%"

if errorlevel 1 (
    echo.
    echo Commit failed or there are no changes.
    echo.
    pause
    exit /b 1
)

git push

echo.
echo ==========================================
echo   DONE
echo ==========================================
echo.
pause