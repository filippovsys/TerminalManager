# -*- coding: utf-8 -*-
"""Справочник мерчантов (клиентов): список, поиск, создание, редактирование."""

import tkinter as tk
from tkinter import ttk, messagebox

import database
from gui import utils
from gui.merchant_card import MerchantCard


TYPE_LABELS = {"bank": "BANK", "edara": "EDARA", "telekeci": "TELEKEÇI"}


class NewMerchantDialog(tk.Toplevel):
    def __init__(self, master):
        super().__init__(master)
        self.title("Новый мерчант")
        self.resizable(False, False)
        self.result = None

        frame = ttk.Frame(self, padding=20)
        frame.pack()

        self.m_id_var = tk.StringVar()
        self.type_var = tk.StringVar(value="telekeci")
        self.note_var = tk.StringVar()

        ttk.Label(frame, text="M/id:").grid(row=0, column=0, sticky="w", pady=4)
        e1 = ttk.Entry(frame, textvariable=self.m_id_var, width=30)
        e1.grid(row=0, column=1, pady=4)

        ttk.Label(frame, text="Тип:").grid(row=1, column=0, sticky="w", pady=4)
        ttk.Combobox(frame, textvariable=self.type_var,
                     values=["telekeci", "edara", "bank"],
                     state="readonly", width=27).grid(row=1, column=1, pady=4)

        ttk.Label(frame, text="Заметка:").grid(row=2, column=0, sticky="w", pady=4)
        ttk.Entry(frame, textvariable=self.note_var, width=30).grid(row=2, column=1, pady=4)

        btns = ttk.Frame(frame)
        btns.grid(row=3, column=0, columnspan=2, pady=(10, 0))
        ttk.Button(btns, text="Создать", command=self._create).pack(side="left", padx=4)
        ttk.Button(btns, text="Отмена", command=self.destroy).pack(side="left", padx=4)

        utils.fix_paste_bindings(e1)
        e1.focus_set()
        self.transient(master)
        self.grab_set()
        self.wait_window(self)

    def _create(self):
        m_id = self.m_id_var.get().strip()
        if not m_id:
            messagebox.showerror("Ошибка", "Укажите M/id", parent=self)
            return
        self.result = {
            "m_id": m_id,
            "merchant_type": self.type_var.get(),
            "note": self.note_var.get().strip() or None,
        }
        self.destroy()


class MerchantsListWindow(tk.Toplevel):
    def __init__(self, master, user):
        super().__init__(master)
        self.user = user
        self.title("Справочник: Мерчанты")
        self.geometry("820x560")

        self.query_var = tk.StringVar()

        top = ttk.Frame(self, padding=10)
        top.pack(fill="x")
        ttk.Label(top, text="Поиск:").pack(side="left")
        search_entry = ttk.Entry(top, textvariable=self.query_var, width=40)
        search_entry.pack(side="left", padx=6)
        search_entry.bind("<Return>", lambda e: self._load())
        ttk.Button(top, text="Найти", command=self._load).pack(side="left")
        ttk.Button(top, text="Сброс", command=self._reset).pack(side="left", padx=4)

        cols = ("m_id", "type", "ids_count", "note", "created_at")
        headings = {"m_id": "M/id", "type": "Тип", "ids_count": "ID-ов",
                    "note": "Заметка", "created_at": "Создан"}
        widths = {"m_id": 130, "type": 100, "ids_count": 70, "note": 280, "created_at": 150}
        self.tree = ttk.Treeview(self, columns=cols, show="headings", height=18)
        for c in cols:
            self.tree.heading(c, text=headings[c])
            self.tree.column(c, width=widths[c], anchor="w")
        self.tree.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.tree.bind("<Double-1>", lambda e: self._open_card())
        self._merchants_by_iid = {}

        btns = ttk.Frame(self, padding=(10, 0, 10, 10))
        btns.pack(fill="x")
        ttk.Button(btns, text="Создать...", command=self._create).pack(side="left", padx=2)
        ttk.Button(btns, text="Открыть карточку", command=self._open_card).pack(side="left", padx=2)
        ttk.Button(btns, text="Обновить", command=self._load).pack(side="right", padx=2)

        utils.apply_to_all_entries(self)
        self._load()

    def _reset(self):
        self.query_var.set("")
        self._load()

    def _load(self):
        query = self.query_var.get().strip() or None
        with database.get_connection() as conn:
            rows = database.list_all_merchants(conn, query=query)
        self.tree.delete(*self.tree.get_children())
        self._merchants_by_iid.clear()
        for r in rows:
            iid = self.tree.insert("", "end", values=(
                r["m_id"], TYPE_LABELS.get(r["merchant_type"], r["merchant_type"]),
                r["ids_count"], r["note"] or "", r["created_at"],
            ))
            self._merchants_by_iid[iid] = r["id"]

    def _selected_id(self):
        sel = self.tree.selection()
        if not sel:
            return None
        return self._merchants_by_iid.get(sel[0])

    def _create(self):
        dlg = NewMerchantDialog(self)
        if dlg.result is None:
            return
        try:
            with database.get_connection() as conn:
                database.create_merchant(
                    conn, dlg.result["m_id"], dlg.result["merchant_type"],
                    self.user["id"], note=dlg.result["note"],
                )
        except Exception as exc:
            messagebox.showerror("Ошибка", str(exc), parent=self)
            return
        self._load()

    def _open_card(self):
        mid = self._selected_id()
        if mid is None:
            return
        MerchantCard(self, self.user, mid, on_close=self._load)