@echo off
setlocal EnableExtensions EnableDelayedExpansion

title HalkTerminalManager - UPLOAD

cd /d "%~dp0"

echo.
echo ============================================================
echo          HalkTerminalManager - UPLOAD TO GITHUB
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
REM Проверка Git repository
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
REM Проверяем ветку
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
REM Проверяем изменения
REM ------------------------------------------------------------
echo ============================================================
echo                    LOCAL CHANGES
echo ============================================================
echo.

git status --short

for /f "delims=" %%A in ('git status --porcelain') do (
    set "HAS_CHANGES=1"
)

if not defined HAS_CHANGES (
    echo.
    echo [INFO] Изменений нет.
    echo.
    echo Локальная версия уже соответствует последнему commit.
    echo.
    pause
    exit /b 0
)

echo.
echo ============================================================
echo ВНИМАНИЕ: найдены изменения.
echo ============================================================
echo.

REM ------------------------------------------------------------
REM Показываем diff summary
REM ------------------------------------------------------------
echo Изменённые файлы:
echo.

git diff --stat

echo.
echo ------------------------------------------------------------
echo.

REM ------------------------------------------------------------
REM Получаем изменения с GitHub перед commit
REM ------------------------------------------------------------
echo Проверка GitHub перед загрузкой...
echo.

git fetch origin

if errorlevel 1 (
    echo.
    echo [ERROR] Не удалось получить информацию с GitHub.
    echo.
    echo Загрузка остановлена.
    echo.
    pause
    exit /b 3
)

echo [OK] GitHub доступен.
echo.

REM ------------------------------------------------------------
REM Проверяем, не появился ли новый commit на GitHub
REM ------------------------------------------------------------
for /f "delims=" %%A in ('git rev-list --count HEAD..origin/!BRANCH!') do set "BEHIND=%%A"

if "!BEHIND!" GTR "0" (
    echo.
    echo ============================================================
    echo [STOP] На GitHub уже есть новые изменения!
    echo ============================================================
    echo.
    echo Локальная версия отстаёт от GitHub на !BEHIND! commit^(s^).
    echo.
    echo Сначала запусти:
    echo     download.bat
    echo.
    echo Твои локальные изменения НЕ были удалены.
    echo.
    pause
    exit /b 4
)

echo [OK] GitHub не содержит новых commit.
echo.

REM ------------------------------------------------------------
REM Запрашиваем сообщение commit
REM ------------------------------------------------------------
echo Введи описание изменений.
echo Например:
echo   Update database
echo   Fix terminal card
echo   Import Excel data
echo.

set /p "MESSAGE=Commit message: "

if "!MESSAGE!"=="" (
    set "MESSAGE=Update project"
)

echo.
echo Commit message:
echo !MESSAGE!
echo.

REM ------------------------------------------------------------
REM Добавляем изменения
REM ------------------------------------------------------------
echo Добавление файлов в commit...
echo.

git add .

if errorlevel 1 (
    echo.
    echo [ERROR] git add завершился с ошибкой.
    echo.
    pause
    exit /b 5
)

echo [OK] Файлы добавлены.
echo.

REM ------------------------------------------------------------
REM Показываем staged changes
REM ------------------------------------------------------------
echo ============================================================
echo                 FILES TO BE UPLOADED
echo ============================================================
echo.

git status --short

echo.
echo ------------------------------------------------------------
echo.

set /p "CONFIRM=Продолжить commit и upload? (Y/N): "

if /I not "!CONFIRM!"=="Y" (
    echo.
    echo Загрузка отменена пользователем.
    echo.
    git reset >nul 2>&1
    pause
    exit /b 0
)

echo.

REM ------------------------------------------------------------
REM Commit
REM ------------------------------------------------------------
echo Создание commit...
echo.

git commit -m "!MESSAGE!"

if errorlevel 1 (
    echo.
    echo [ERROR] Commit не создан.
    echo.
    pause
    exit /b 6
)

echo.
echo [OK] Commit создан.
echo.

REM ------------------------------------------------------------
REM Push
REM ------------------------------------------------------------
echo ============================================================
echo                    PUSH TO GITHUB
echo ============================================================
echo.

git push origin !BRANCH!

if errorlevel 1 (
    echo.
    echo ============================================================
    echo [ERROR] PUSH НЕ ВЫПОЛНЕН
    echo ============================================================
    echo.
    echo Commit уже создан локально, поэтому твоя работа НЕ потеряна.
    echo.
    echo Проверь интернет и авторизацию GitHub.
    echo.
    echo Затем можно снова запустить upload.bat.
    echo.
    pause
    exit /b 7
)

echo.
echo ============================================================
echo                    UPLOAD COMPLETED
echo ============================================================
echo.
echo Изменения успешно загружены на GitHub.
echo.
echo Последний commit:
git log -1 --oneline

echo.
echo Статус:
git status

echo.
pause
exit /b 0