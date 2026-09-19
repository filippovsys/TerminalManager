# -*- coding: utf-8 -*-
"""Настройки колонок главного окна: порядок, видимость, ширины.
Сохраняются в column_settings.json рядом с config.py."""

import json
import os
import tkinter as tk
from tkinter import ttk, messagebox

import config


COLUMN_SETTINGS_PATH = os.path.join(
    os.path.dirname(os.path.abspath(config.__file__)), "column_settings.json"
)


def load_settings():
    try:
        with open(COLUMN_SETTINGS_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_settings(data):
    try:
        with open(COLUMN_SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


class ColumnSettingsDialog(tk.Toplevel):
    """Диалог: список колонок, где можно перемещать (↑↓) и скрывать/показывать (двойной клик)."""

    def __init__(self, master, all_ids, headings, visible_ids, on_apply):
        super().__init__(master)
        self.title("Настройка колонок")
        self.resizable(False, False)
        self.on_apply = on_apply
        self.headings = headings

        hidden = [c for c in all_ids if c not in visible_ids]
        self.items = [(c, True) for c in visible_ids] + [(c, False) for c in hidden]

        main = ttk.Frame(self, padding=10)
        main.pack(fill="both", expand=True)

        ttk.Label(main, text="Порядок и видимость колонок (двойной клик — скрыть/показать):").grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 6)
        )

        self.lb = tk.Listbox(main, selectmode="single", activestyle="none",
                             width=42, height=12, font=("Consolas", 10))
        self.lb.grid(row=1, column=0, sticky="nsew")
        self.lb.bind("<Double-Button-1>", lambda e: self._toggle())

        btn_frame = ttk.Frame(main)
        btn_frame.grid(row=1, column=1, sticky="n", padx=(10, 0))
        ttk.Button(btn_frame, text="↑", width=4, command=self._up).pack(pady=2)
        ttk.Button(btn_frame, text="↓", width=4, command=self._down).pack(pady=2)
        ttk.Button(btn_frame, text="Показать/скрыть", command=self._toggle).pack(pady=(10, 2))

        actions = ttk.Frame(main)
        actions.grid(row=2, column=0, columnspan=2, sticky="e", pady=(10, 0))
        ttk.Button(actions, text="Применить", command=self._apply).pack(side="right", padx=2)
        ttk.Button(actions, text="Отмена", command=self.destroy).pack(side="right", padx=2)

        self._refresh()

        self.transient(master)
        self.grab_set()
        self.wait_window(self)

    def _refresh(self):
        self.lb.delete(0, "end")
        for cid, vis in self.items:
            mark = "✓" if vis else " "
            name = self.headings.get(cid, cid)
            self.lb.insert("end", f"  {mark}   {name}")

    def _selected_idx(self):
        sel = self.lb.curselection()
        return sel[0] if sel else None

    def _up(self):
        i = self._selected_idx()
        if i is None or i == 0:
            return
        self.items[i - 1], self.items[i] = self.items[i], self.items[i - 1]
        self._refresh()
        self.lb.selection_set(i - 1)

    def _down(self):
        i = self._selected_idx()
        if i is None or i == len(self.items) - 1:
            return
        self.items[i], self.items[i + 1] = self.items[i + 1], self.items[i]
        self._refresh()
        self.lb.selection_set(i + 1)

    def _toggle(self):
        i = self._selected_idx()
        if i is None:
            return
        cid, vis = self.items[i]
        self.items[i] = (cid, not vis)
        self._refresh()
        self.lb.selection_set(i)

    def _apply(self):
        visible = [cid for cid, vis in self.items if vis]
        if not visible:
            messagebox.showwarning("Ошибка", "Хотя бы одна колонка должна остаться видимой",
                                   parent=self)
            return
        self.on_apply(visible)
        self.destroy()