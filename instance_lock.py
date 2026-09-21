# -*- coding: utf-8 -*-
"""
Блокировка "один пользователь одновременно" для сетевой версии.

Файл instance.lock создаётся рядом с базой данных (в той же сетевой
папке, где terminals.db). Хранит имя пользователя, имя компьютера,
PID и время последнего "сердцебиения".

- При запуске: если файл занят кем-то живым (heartbeat свежий) --
  показываем сообщение и выходим.
- Если лок протух (программа аварийно завершилась, питание выключили) --
  забираем его.
- Раз в HEARTBEAT_INTERVAL секунд обновляем heartbeat в фоновом потоке.
- При штатном закрытии удаляем файл.

Это не 100% защита (в теории двое могут нажать "запустить" в одну и ту
же миллисекунду на медленной сети), но для офиса из 3-5 человек --
надёжно и достаточно. Главное -- не даёт испортить БД одновременной
записью.
"""

import getpass
import json
import os
import socket
import threading
from datetime import datetime

import config


LOCK_FILE = os.path.join(os.path.dirname(config.DB_PATH), "instance.lock")

HEARTBEAT_INTERVAL = 5       # как часто обновляем "сердцебиение", секунд
STALE_AFTER_SECONDS = 30     # если обновлений не было дольше -- сеанс "умер"

_heartbeat_stop = threading.Event()
_lock_info = None
_lock_acquired = False


def _get_current_user():
    return os.environ.get("USERNAME") or getpass.getuser() or "неизвестный пользователь"


def _get_current_computer():
    return os.environ.get("COMPUTERNAME") or socket.gethostname() or "неизвестный компьютер"


def _read_lock_file():
    try:
        with open(LOCK_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _write_lock_file(data):
    try:
        d = os.path.dirname(LOCK_FILE)
        if d and not os.path.exists(d):
            os.makedirs(d)
        with open(LOCK_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f)
        return True
    except Exception:
        return False


def try_acquire_lock():
    """
    Пытается занять блокировку для текущего пользователя.

    Возвращает:
      (True, None)           -- удалось занять.
      (False, owner_info)    -- программа занята, owner_info содержит
                                user / computer того, кто её занял.
      (False, {"error": ...}) -- не удалось создать файл блокировки
                                (например, нет доступа к сетевой папке).
    """
    global _lock_info, _lock_acquired

    existing = _read_lock_file()
    if existing:
        try:
            hb = datetime.fromisoformat(existing.get("heartbeat", ""))
            age = (datetime.now() - hb).total_seconds()
        except Exception:
            age = None

        if age is not None and age <= STALE_AFTER_SECONDS:
            return False, existing

    _lock_info = {
        "user": _get_current_user(),
        "computer": _get_current_computer(),
        "pid": os.getpid(),
        "started": datetime.now().isoformat(),
        "heartbeat": datetime.now().isoformat(),
    }
    if not _write_lock_file(_lock_info):
        return False, {"error": f"Не удалось создать файл блокировки:\n{LOCK_FILE}"}

    _lock_acquired = True
    return True, None


def describe_lock_owner(owner_info):
    """Человекочитаемое описание того, кто занял программу."""
    if not owner_info:
        return "другой пользователь"
    user = owner_info.get("user", "неизвестный пользователь")
    computer = owner_info.get("computer", "неизвестный компьютер")
    return f'Пользователь: "{user}"\nКомпьютер: "{computer}"'


def start_heartbeat():
    """Запускает фоновый поток, обновляющий heartbeat."""
    def loop():
        while not _heartbeat_stop.is_set():
            if _lock_info is not None:
                _lock_info["heartbeat"] = datetime.now().isoformat()
                _write_lock_file(_lock_info)
            _heartbeat_stop.wait(HEARTBEAT_INTERVAL)

    thread = threading.Thread(target=loop, daemon=True)
    thread.start()


def release_lock():
    """Освобождает блокировку при штатном закрытии."""
    global _lock_acquired
    _heartbeat_stop.set()
    try:
        if _lock_acquired and os.path.exists(LOCK_FILE):
            data = _read_lock_file()
            # Удаляем только если это наш собственный лок
            if data and data.get("pid") == os.getpid():
                os.remove(LOCK_FILE)
    except Exception:
        pass
    _lock_acquired = False