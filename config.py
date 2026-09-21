# -*- coding: utf-8 -*-
"""
Конфигурация Terminal Manager.

DB_PATH указывает на общий файл БД на сетевой папке -- именно он должен
быть доступен всем пользователям.

Приоритет определения пути к БД:
  1. Переменная окружения HTM_DB_PATH (если задана).
  2. Папка data/ рядом с .exe (в собранной программе) или рядом с
     config.py (при запуске из исходников).

Ресурсы (db_schema.sql, CHANGELOG.md) в собранном .exe лежат внутри
упаковки -- их путь определяет функция _resource_path().
"""

import os
import sys

# Версия приложения. Обновляется при каждом наборе значимых изменений --
# см. CHANGELOG.md рядом с исходниками. Отображается в заголовке главного
# окна и в "О программе", чтобы всегда было видно, какая версия запущена
# на конкретном компьютере.
APP_VERSION = "1.4 RELEASE"

# Версия схемы БД -- увеличивается при каждой структурной правке БД.
SCHEMA_VERSION = 4


def _is_frozen():
    """True, если программа запущена как собранный .exe (PyInstaller)."""
    return getattr(sys, "frozen", False)


def _app_dir():
    """Папка, где лежит .exe (или папка проекта при запуске из исходников).

    Для .exe -- папка, в которой сам файл. Для исходников -- папка,
    где лежит config.py.
    """
    if _is_frozen():
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def _resource_path(name):
    """Путь к встроенному ресурсу (db_schema.sql, CHANGELOG.md).

    В собранном .exe ресурсы распакованы в sys._MEIPASS.
    При запуске из исходников -- это просто файл рядом с config.py.
    """
    if _is_frozen():
        base = getattr(sys, "_MEIPASS", _app_dir())
        return os.path.join(base, name)
    return os.path.join(_app_dir(), name)


# --- Путь к БД ---
_env_db = os.environ.get("HTM_DB_PATH")
if _env_db:
    DB_PATH = _env_db
else:
    DB_PATH = os.path.join(_app_dir(), "data", "terminals.db")

# --- Пути к ресурсам ---
SCHEMA_SQL_PATH = _resource_path("db_schema.sql")
CHANGELOG_PATH = _resource_path("CHANGELOG.md")

# Через сколько минут неактивная блокировка карточки считается "зависшей"
# и может быть снята другим пользователем (на случай, если приложение
# закрылось аварийно и не сняло блокировку само).
EDIT_LOCK_TIMEOUT_MINUTES = 30

# Параметры хеширования пароля
PBKDF2_ITERATIONS = 200_000