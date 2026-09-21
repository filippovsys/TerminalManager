# -*- coding: utf-8 -*-
"""Диалог выбора/создания терминала по S/N."""

import tkinter as tk
from tkinter import ttk, messagebox

import database
from gui import utils


PLACE_LABELS = {"merchant": "У клиента", "warehouse": "Склад", "repair_shop": "Мастерская"}


class TerminalPickerDialog(tk.Toplevel):
    """Возвращает dict {"terminal_id": id, "serial_number": ...} или None."""

    def __init__(self, master, user, prefill_sn=None):
        super().__init__(master)
        self.user = user
        self.result = None

        self.title("Выбор терминала")
        self.geometry("760x480")

        self.query_var = tk.StringVar(value=prefill_sn or "")
        self.sn_var = tk.StringVar(value=prefill_sn or "")
        self.model_var = tk.StringVar()
        self.ownership_var = tk.StringVar(value="bank")
        self.create_new_var = tk.IntVar(value=0)

        self._build()
        utils.apply_to_all_entries(self)
        self._search()

        self.transient(master)
        self.grab_set()
        self.wait_window(self)

    def _build(self):
        top = ttk.Frame(self, padding=10)
        top.pack(fill="x")
        ttk.Label(top, text="Поиск по S/N или модели:").pack(side="left")
        e = ttk.Entry(top, textvariable=self.query_var, width=30)
        e.pack(side="left", padx=6)
        e.bind("<Return>", lambda ev: self._search())
        ttk.Button(top, text="Найти", command=self._search).pack(side="left")

        cols = ("sn", "model", "own", "place", "condition")
        headings = {"sn": "S/N", "model": "Модель", "own": "Собств.",
                    "place": "Место", "condition": "Состояние"}
        widths = {"sn": 130, "model": 130, "own": 70, "place": 110, "condition": 110}
        self.tree = ttk.Treeview(self, columns=cols, show="headings", height=12)
        for c in cols:
            self.tree.heading(c, text=headings[c])
            self.tree.column(c, width=widths[c], anchor="w")
        self.tree.pack(fill="both", expand=True, padx=10, pady=(0, 6))
        self.tree.bind("<Double-1>", lambda ev: self._pick_existing())
        self._terminals_by_iid = {}

        # --- блок создания нового ---
        new_frame = ttk.LabelFrame(self, text="Если S/N нет в списке", padding=8)
        new_frame.pack(fill="x", padx=10, pady=(0, 6))

        ttk.Checkbutton(new_frame, text="Создать новый терминал",
                        variable=self.create_new_var,
                        command=self._on_check_toggle).grid(row=0, column=0, columnspan=2, sticky="w")

        ttk.Label(new_frame, text="S/N:").grid(row=1, column=0, sticky="w", pady=(4, 0))
        self.sn_entry = ttk.Entry(new_frame, textvariable=self.sn_var, width=30, state="disabled")
        self.sn_entry.grid(row=1, column=1, sticky="w", padx=(4, 0), pady=(4, 0))

        ttk.Label(new_frame, text="Модель:").grid(row=2, column=0, sticky="w", pady=(4, 0))
        with database.get_connection() as conn:
            models = database.get_distinct_models(conn)
        self.model_cb = ttk.Combobox(new_frame, textvariable=self.model_var, values=models, width=27, state="disabled")
        self.model_cb.grid(row=2, column=1, sticky="w", padx=(4, 0), pady=(4, 0))

        ttk.Label(new_frame, text="Владение:").grid(row=3, column=0, sticky="w", pady=(4, 0))
        self.own_cb = ttk.Combobox(new_frame, textvariable=self.ownership_var,
                                    values=["bank", "client"], state="disabled", width=27)
        self.own_cb.grid(row=3, column=1, sticky="w", padx=(4, 0), pady=(4, 0))

        # --- кнопки ---
        btns = ttk.Frame(self, padding=(10, 0, 10, 10))
        btns.pack(fill="x")
        ttk.Button(btns, text="Выбрать", command=self._do_pick).pack(side="right", padx=2)
        ttk.Button(btns, text="Отмена", command=self.destroy).pack(side="right", padx=2)

    def _on_check_toggle(self):
        if self.create_new_var.get():
            self.sn_entry.configure(state="normal")
            self.model_cb.configure(state="normal")
            self.own_cb.configure(state="readonly")
        else:
            self.sn_entry.configure(state="disabled")
            self.model_cb.configure(state="disabled")
            self.own_cb.configure(state="disabled")

    def _search(self):
        q = self.query_var.get().strip() or None
        with database.get_connection() as conn:
            rows = database.list_all_terminals(conn, query=q, is_epos=None, limit=500)
        self.tree.delete(*self.tree.get_children())
        self._terminals_by_iid.clear()
        for r in rows:
            iid = self.tree.insert("", "end", values=(
                r["serial_number"] or "(без S/N)",
                r["model"] or "",
                "Банк" if r["ownership"] == "bank" else "Клиент",
                PLACE_LABELS.get(r["current_place"], r["current_place"] or "—"),
                r["condition"] or "",
            ))
            self._terminals_by_iid[iid] = r

    def _pick_existing(self):
        sel = self.tree.selection()
        if not sel:
            return
        r = self._terminals_by_iid.get(sel[0])
        if r:
            self.result = {"terminal_id": r["id"], "serial_number": r["serial_number"]}
            self.destroy()

    def _do_pick(self):
        # приоритет -- выбор из списка
        sel = self.tree.selection()
        if sel and not self.create_new_var.get():
            self._pick_existing()
            return
        # иначе -- создание нового
        if self.create_new_var.get():
            sn = self.sn_var.get().strip()
            if not sn:
                messagebox.showerror("Ошибка", "Укажите S/N нового терминала", parent=self)
                return
            try:
                with database.get_connection() as conn:
                    new_id = database.create_terminal(
                        conn, sn,
                        self.model_var.get().strip() or None,
                        self.ownership_var.get() or "bank",
                        None, self.user["id"],
                        note="создан при привязке ID",
                    )
            except Exception as exc:
                messagebox.showerror("Ошибка", str(exc), parent=self)
                return
            self.result = {"terminal_id": new_id, "serial_number": sn}
            self.destroy()
            return
        messagebox.showinfo("Выбор", "Выберите терминал из списка или поставьте галочку «Создать новый».", parent=self)