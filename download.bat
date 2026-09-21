@echo off
chcp 65001 >nul
setlocal EnableExtensions EnableDelayedExpansion

title Terminal Manager - DOWNLOAD

cd /d "%~dp0"

echo.
echo ============================================================
echo        Terminal Manager - DOWNLOAD FROM GITHUB
echo ============================================================
echo.
echo Project:
echo %CD%
echo.

REM ------------------------------------------------------------
REM Проверка Git
REM ------------------------------------------------------------
where git >nul 2>&1

if errorlevel 1 (
    echo [ERROR] Git не найден в PATH.
    echo.
    echo Установи Git или проверь его установку.
    echo.
    pause
    exit /b 1
)

echo [OK] Git найден.
echo.

REM ------------------------------------------------------------
REM Проверка, что это Git-репозиторий
REM ------------------------------------------------------------
git rev-parse --is-inside-work-tree >nul 2>&1

if errorlevel 1 (
    echo [ERROR] Эта папка не является Git-репозиторием.
    echo.
    echo Папка:
    echo %CD%
    echo.
    pause
    exit /b 1
)

echo [OK] Git repository найден.
echo.

REM ------------------------------------------------------------
REM Проверка remote
REM ------------------------------------------------------------
git remote get-url origin >nul 2>&1

if errorlevel 1 (
    echo [ERROR] Remote "origin" не настроен.
    echo.
    echo Проверь настройку GitHub для проекта.
    echo.
    pause
    exit /b 1
)

for /f "delims=" %%R in ('git remote get-url origin') do set "REMOTE=%%R"

echo [OK] GitHub:
echo !REMOTE!
echo.

REM ------------------------------------------------------------
REM Проверяем текущую ветку
REM ------------------------------------------------------------
for /f "delims=" %%B in ('git branch --show-current') do set "BRANCH=%%B"

if "!BRANCH!"=="" (
    echo [ERROR] Не удалось определить текущую ветку.
    echo.
    pause
    exit /b 1
)

echo [OK] Current branch: !BRANCH!
echo.

REM ------------------------------------------------------------
REM Проверяем локальные изменения
REM ------------------------------------------------------------
echo Проверка локальных изменений...
echo.

git status --porcelain

if not errorlevel 1 (
    for /f "delims=" %%A in ('git status --porcelain') do (
        set "DIRTY=1"
    )
)

if defined DIRTY (
    echo.
    echo ============================================================
    echo [STOP] Есть локальные изменения!
    echo ============================================================
    echo.
    echo GitHub НЕ будет скачан, чтобы не затереть твою работу.
    echo.
    echo Сначала сделай upload.bat, если эти изменения нужно
    echo отправить на GitHub.
    echo.
    pause
    exit /b 2
)

echo [OK] Локальных изменений нет.
echo.

REM ------------------------------------------------------------
REM Получаем информацию с GitHub
REM ------------------------------------------------------------
echo Получение информации с GitHub...
echo.

git fetch origin

if errorlevel 1 (
    echo.
    echo [ERROR] Не удалось получить данные с GitHub.
    echo.
    echo Возможные причины:
    echo   - нет интернета
    echo   - проблема авторизации GitHub
    echo   - недоступен репозиторий
    echo.
    pause
    exit /b 3
)

echo.
echo [OK] GitHub доступен.
echo.

REM ------------------------------------------------------------
REM Синхронизация
REM ------------------------------------------------------------
echo Синхронизация локальной версии с GitHub...
echo.

git pull --ff-only origin !BRANCH!

if errorlevel 1 (
    echo.
    echo ============================================================
    echo [ERROR] Синхронизация не выполнена.
    echo ============================================================
    echo.
    echo Git отказался выполнять fast-forward.
    echo.
    echo Это обычно означает, что история локального репозитория
    echo и GitHub разошлась.
    echo.
    echo Ничего автоматически не изменялось.
    echo.
    pause
    exit /b 4
)

echo.
echo ============================================================
echo                 DOWNLOAD COMPLETED
echo ============================================================
echo.
echo Локальная папка обновлена из GitHub.
echo.

git status

echo.
pause
exit /b 0