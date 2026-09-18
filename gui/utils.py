# -*- coding: utf-8 -*-
"""
gui/utils.py -- общие мелкие помощники для GUI.

Главное здесь -- fix_paste_bindings(): на Windows с русской (не английской)
раскладкой клавиатуры Tkinter не всегда получает правильный keysym для
Ctrl+V/C/X/A (это старая известная проблема Tk), из-за чего "Вставить"
по Ctrl+V в поле ввода просто не срабатывает, хотя через контекстное меню
или английскую раскладку всё работает. Решение -- ловить комбинацию по
физическому коду клавиши (event.keycode), а не по символу, и вручную
вызывать соответствующее виртуальное событие (<<Paste>>/<<Copy>>/<<Cut>>).

Применять к ЛЮБОМУ полю ввода (Entry), куда пользователь может что-то
вставлять -- поиск, поля карточек, логин и т.д.
"""

# Коды клавиш V/C/X/A одинаковы на большинстве раскладок Windows,
# т.к. это физическое положение клавиши, а не то, что на ней "напечатано"
# в текущей раскладке.
_KEYCODE_PASTE = (86,)   # V
_KEYCODE_COPY = (67,)    # C
_KEYCODE_CUT = (88,)     # X
_KEYCODE_SELECT_ALL = (65,)  # A


def fix_paste_bindings(widget):
    """Навешивает на widget (обычно ttk.Entry/tk.Entry) обработку
    Ctrl+V/C/X/A по коду клавиши -- работает независимо от текущей
    раскладки клавиатуры. Безопасно вызывать многократно на одном виджете."""

    def handler(event):
        # event.state содержит битовую маску модификаторов; бит 0x0004 --
        # зажат Control (стандартно для X11/Windows в Tk).
        if not (event.state & 0x0004):
            return None
        if event.keycode in _KEYCODE_PASTE:
            widget.event_generate("<<Paste>>")
            return "break"
        if event.keycode in _KEYCODE_COPY:
            widget.event_generate("<<Copy>>")
            return "break"
        if event.keycode in _KEYCODE_CUT:
            widget.event_generate("<<Cut>>")
            return "break"
        if event.keycode in _KEYCODE_SELECT_ALL:
            _select_all(widget)
            return "break"
        return None

    widget.bind("<KeyPress>", handler, add="+")


def _select_all(widget):
    try:
        widget.select_range(0, "end")
        widget.icursor("end")
    except Exception:
        # виджет без select_range (не Entry) -- просто игнорируем
        pass


def apply_to_all_entries(container):
    """Рекурсивно обходит все дочерние виджеты container и применяет
    fix_paste_bindings() к каждому Entry/Combobox. Удобно вызывать один
    раз в конце _build() окна/карточки вместо ручной расстановки."""
    import tkinter as tk
    from tkinter import ttk

    stack = [container]
    while stack:
        widget = stack.pop()
        if isinstance(widget, (tk.Entry, ttk.Entry, ttk.Combobox)):
            fix_paste_bindings(widget)
        stack.extend(widget.winfo_children())
