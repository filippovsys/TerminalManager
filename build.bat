@echo off
chcp 65001 >nul
setlocal EnableExtensions EnableDelayedExpansion

title Terminal Manager - BUILD

cd /d "%~dp0"

echo.
echo ============================================================
echo          Terminal Manager - СБОРКА EXE
echo ============================================================
echo.
echo Project:
echo %CD%
echo.

REM ------------------------------------------------------------
REM Проверка Python
REM ------------------------------------------------------------
where python >nul 2>&1

if errorlevel 1 (
    echo [ERROR] Python не найден в PATH.
    echo.
    echo Установи Python или проверь его установку.
    echo.
    pause
    exit /b 1
)

echo [OK] Python найден:
python --version
echo.

REM ------------------------------------------------------------
REM Проверка PyInstaller
REM ------------------------------------------------------------
python -c "import PyInstaller" >nul 2>&1

if errorlevel 1 (
    echo [INFO] PyInstaller не установлен. Устанавливаю...
    python -m pip install --upgrade pyinstaller
    if errorlevel 1 (
        echo [ERROR] Не удалось установить PyInstaller.
        echo.
        pause
        exit /b 1
    )
)

echo [OK] PyInstaller готов.
echo.

REM ------------------------------------------------------------
REM Проверка openpyxl
REM ------------------------------------------------------------
python -c "import openpyxl" >nul 2>&1

if errorlevel 1 (
    echo [INFO] openpyxl не установлен. Устанавливаю...
    python -m pip install --upgrade openpyxl
    if errorlevel 1 (
        echo [ERROR] Не удалось установить openpyxl.
        echo.
        pause
        exit /b 1
    )
)

echo [OK] openpyxl готов.
echo.

REM ------------------------------------------------------------
REM Проверка spec-файла
REM ------------------------------------------------------------
if not exist "TerminalManager.spec" (
    echo [ERROR] Не найден TerminalManager.spec
    echo.
    echo Файл должен лежать в корне проекта рядом с main.py
    echo.
    pause
    exit /b 1
)

echo [OK] TerminalManager.spec найден.
echo.

REM ------------------------------------------------------------
REM Очистка старых сборок
REM ------------------------------------------------------------
if exist "build" (
    echo Удаление старой папки build...
    rmdir /s /q "build"
)
if exist "dist" (
    echo Удаление старой папки dist...
    rmdir /s /q "dist"
)
echo.

REM ------------------------------------------------------------
REM Сборка
REM ------------------------------------------------------------
echo ============================================================
echo                    СБОРКА...
echo ============================================================
echo.
echo Это может занять 30-60 секунд. Не закрывай окно.
echo.

python -m PyInstaller --clean --noconfirm TerminalManager.spec

REM PyInstaller иногда возвращает код != 0 даже при успешной сборке
REM (из-за предупреждений о необязательных модулях).
REM Поэтому проверяем результат -- наличие самого exe.
if not exist "dist\TerminalManager\TerminalManager.exe" (
    echo.
    echo ============================================================
    echo [ERROR] СБОРКА НЕ УДАЛАСЬ
    echo ============================================================
    echo.
    echo Exe не найден по пути:
    echo   dist\TerminalManager\TerminalManager.exe
    echo.
    echo Проверь сообщения выше.
    echo.
    echo Частые причины:
    echo   - антивирус блокирует запись в dist\build
    echo   - не установлены зависимости (pip install -r requirements.txt)
    echo   - ошибка в коде (попробуй запустить: python main.py)
    echo.
    pause
    exit /b 1
)

REM ------------------------------------------------------------
REM Успех
REM ------------------------------------------------------------
echo.
echo ============================================================
echo                 СБОРКА ЗАВЕРШЕНА
echo ============================================================
echo.
echo Результат:
echo   %CD%\dist\TerminalManager\TerminalManager.exe
echo.
echo Для развёртывания скопируй ВСЮ папку:
echo   dist\TerminalManager\
echo на сетевой диск.
echo.
echo Содержимое dist\TerminalManager:
dir "dist\TerminalManager" /b

echo.
pause
exit /b 0