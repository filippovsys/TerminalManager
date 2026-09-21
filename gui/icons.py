# -*- coding: utf-8 -*-
"""Загрузка иконки приложения.

Работает и в исходниках, и в собранном .exe (PyInstaller).
Ищет icon.ico в нескольких местах, чтобы точно найти его
в любой конфигурации запуска.
"""

import os
import sys


def get_icon_path():
    """Возвращает путь к icon.ico или None, если не найден."""
    candidates = []

    if getattr(sys, "frozen", False):
        # Собранный .exe -- icon.ico лежит рядом с exe
        exe_dir = os.path.dirname(os.path.abspath(sys.executable))
        candidates.append(os.path.join(exe_dir, "icon.ico"))
        # Иногда PyInstaller кладёт datas во _internal
        candidates.append(os.path.join(exe_dir, "_internal", "icon.ico"))
        # И в _MEIPASS на всякий случай
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            candidates.append(os.path.join(meipass, "icon.ico"))
    else:
        # Запуск из исходников -- icon.ico в корне проекта
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        candidates.append(os.path.join(base, "icon.ico"))

    for p in candidates:
        if os.path.exists(p):
            return p
    return None


def set_window_icon(window):
    """Ставит иконку окну. Безопасно вызывать всегда -- если файла нет, ничего не делает."""
    path = get_icon_path()
    if not path:
        return
    try:
        window.iconbitmap(path)
    except Exception:
        try:
            window.wm_iconbitmap(path)
        except Exception:
            pass

def get_logo_path():
    """Возвращает путь к logo.png или None, если файла нет."""
    candidates = []
    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(os.path.abspath(sys.executable))
        candidates.append(os.path.join(exe_dir, "logo.png"))
        candidates.append(os.path.join(exe_dir, "_internal", "logo.png"))
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            candidates.append(os.path.join(meipass, "logo.png"))
    else:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        candidates.append(os.path.join(base, "logo.png"))
    for p in candidates:
        if os.path.exists(p):
            return p
    return None