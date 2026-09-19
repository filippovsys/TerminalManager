# -*- coding: utf-8 -*-
"""Справочник физических терминалов: список, поиск, создание, редактирование."""

import tkinter as tk
from tkinter import ttk, messagebox

import database
from gui import utils
from gui.terminal_card import TerminalCard


PLACE_LABELS = {"merchant": "У клиента", "warehouse": "Склад", "repair_shop": "Мастерская"}
CONDITION_LABELS = {
    "normal": "Норма", "in_repair": "В ремонте",
    "awaiting_firmware": "Ждёт прошивку", "written_off": "Списан",
}
OWNERSHIP_SHORT = {"bank": "Банк", "client": "Клиент"}


class NewTerminalDialog(tk.Toplevel):
    def __init__(self, master):
        super().__init__(master)
        self.title("Новый терминал")
        self.resizable(False, False)
        self.result = None

        frame = ttk.Frame(self, padding=20)
        frame.pack()

        self.sn_var = tk.StringVar()
        self.model_var = tk.StringVar()
        self.ownership_var = tk.StringVar(value="bank")
        self.conn_var = tk.StringVar(value="ethernet")
        self.is_epos_var = tk.IntVar(value=0)
        self.note_var = tk.StringVar()

        with database.get_connection() as conn:
            models = database.get_distinct_models(conn)

        ttk.Label(frame, text="S/N (можно пусто для E-POS):").grid(row=0, column=0, sticky="w", pady=4)
        e1 = ttk.Entry(frame, textvariable=self.sn_var, width=30)
        e1.grid(row=0, column=1, pady=4)

        ttk.Label(frame, text="Модель:").grid(row=1, column=0, sticky="w", pady=4)
        ttk.Combobox(frame, textvariable=self.model_var, values=models, width=27).grid(row=1, column=1, pady=4)

        ttk.Label(frame, text="Владение:").grid(row=2, column=0, sticky="w", pady=4)
        ttk.Combobox(frame, textvariable=self.ownership_var, values=["bank", "client"],
                     state="readonly", width=27).grid(row=2, column=1, pady=4)

        ttk.Label(frame, text="Тип подключения:").grid(row=3, column=0, sticky="w", pady=4)
        ttk.Combobox(frame, textvariable=self.conn_var, values=["sim", "ethernet"],
                     state="readonly", width=27).grid(row=3, column=1, pady=4)

        ttk.Label(frame, text="E-POS:").grid(row=4, column=0, sticky="w", pady=4)
        ttk.Checkbutton(frame, variable=self.is_epos_var).grid(row=4, column=1, sticky="w", pady=4)

        ttk.Label(frame, text="Заметка:").grid(row=5, column=0, sticky="w", pady=4)
        ttk.Entry(frame, textvariable=self.note_var, width=30).grid(row=5, column=1, pady=4)

        btns = ttk.Frame(frame)
        btns.grid(row=6, column=0, columnspan=2, pady=(10, 0))
        ttk.Button(btns, text="Создать", command=self._create).pack(side="left", padx=4)
        ttk.Button(btns, text="Отмена", command=self.destroy).pack(side="left", padx=4)

        utils.fix_paste_bindings(e1)
        e1.focus_set()
        self.transient(master)
        self.grab_set()
        self.wait_window(self)

    def _create(self):
        self.result = {
            "serial_number": self.sn_var.get().strip() or None,
            "model": self.model_var.get().strip() or None,
            "ownership": self.ownership_var.get(),
            "connection_type": self.conn_var.get(),
            "is_epos": self.is_epos_var.get(),
            "note": self.note_var.get().strip() or None,
        }
        self.destroy()


class TerminalsListWindow(tk.Toplevel):
    def __init__(self, master, user):
        super().__init__(master)
        self.user = user
        self.title("Справочник: Терминалы")
        self.geometry("920x580")

        self.query_var = tk.StringVar()
        self.epos_filter_var = tk.StringVar(value="all")

        top = ttk.Frame(self, padding=10)
        top.pack(fill="x")
        ttk.Label(top, text="Поиск:").pack(side="left")
        search_entry = ttk.Entry(top, textvariable=self.query_var, width=32)
        search_entry.pack(side="left", padx=6)
        search_entry.bind("<Return>", lambda e: self._load())
        ttk.Button(top, text="Найти", command=self._load).pack(side="left")
        ttk.Button(top, text="Сброс", command=self._reset).pack(side="left", padx=4)

        ttk.Label(top, text="  Показать:").pack(side="left", padx=(12, 2))
        for text, val in (("Все", "all"), ("Только E-POS", "epos"), ("Без E-POS", "no_epos")):
            ttk.Radiobutton(top, text=text, variable=self.epos_filter_var, value=val,
                            command=self._load).pack(side="left", padx=2)

        cols = ("sn", "model", "own", "epos", "place", "condition", "active_ids", "note")
        headings = {
            "sn": "S/N", "model": "Модель", "own": "Собств.", "epos": "E-POS",
            "place": "Место", "condition": "Состояние",
            "active_ids": "Актив. ID", "note": "Заметка",
        }
        widths = {"sn": 130, "model": 120, "own": 70, "epos": 55, "place": 100,
                  "condition": 110, "active_ids": 80, "note": 200}
        self.tree = ttk.Treeview(self, columns=cols, show="headings", height=18)
        for c in cols:
            self.tree.heading(c, text=headings[c])
            self.tree.column(c, width=widths[c], anchor="w")
        self.tree.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.tree.bind("<Double-1>", lambda e: self._open_card())
        self._terminals_by_iid = {}

        btns = ttk.Frame(self, padding=(10, 0, 10, 10))
        btns.pack(fill="x")
        ttk.Button(btns, text="Создать...", command=self._create).pack(side="left", padx=2)
        ttk.Button(btns, text="Открыть карточку", command=self._open_card).pack(side="left", padx=2)
        ttk.Button(btns, text="Обновить", command=self._load).pack(side="right", padx=2)

        utils.apply_to_all_entries(self)
        self._load()

    def _reset(self):
        self.query_var.set("")
        self.epos_filter_var.set("all")
        self._load()

    def _load(self):
        query = self.query_var.get().strip() or None
        mode = self.epos_filter_var.get()
        is_epos = None
        if mode == "epos":
            is_epos = True
        elif mode == "no_epos":
            is_epos = False
        with database.get_connection() as conn:
            rows = database.list_all_terminals(conn, query=query, is_epos=is_epos)
        self.tree.delete(*self.tree.get_children())
        self._terminals_by_iid.clear()
        for r in rows:
            iid = self.tree.insert("", "end", values=(
                r["serial_number"] or "(без S/N)",
                r["model"] or "",
                OWNERSHIP_SHORT.get(r["ownership"], r["ownership"]),
                "Да" if r["is_epos"] else "",
                PLACE_LABELS.get(r["current_place"], r["current_place"] or "—"),
                CONDITION_LABELS.get(r["condition"], r["condition"] or "—"),
                r["active_ids"], r["note"] or "",
            ))
            self._terminals_by_iid[iid] = r["id"]

    def _selected_id(self):
        sel = self.tree.selection()
        if not sel:
            return None
        return self._terminals_by_iid.get(sel[0])

    def _create(self):
        dlg = NewTerminalDialog(self)
        if dlg.result is None:
            return
        try:
            with database.get_connection() as conn:
                database.create_terminal(
                    conn, dlg.result["serial_number"], dlg.result["model"],
                    dlg.result["ownership"], dlg.result["connection_type"],
                    self.user["id"], note=dlg.result["note"],
                    is_epos=dlg.result["is_epos"],
                )
        except Exception as exc:
            messagebox.showerror("Ошибка", str(exc), parent=self)
            return
        self._load()

    def _open_card(self):
        tid = self._selected_id()
        if tid is None:
            return
        TerminalCard(self, self.user, tid, on_close=self._load)