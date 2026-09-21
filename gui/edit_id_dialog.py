# -*- coding: utf-8 -*-
"""Диалог "Редактировать ID": правка полей terminal_ids."""

import re
import tkinter as tk
from tkinter import ttk, messagebox

import database
from gui import utils


def parse_date(s):
    if not s:
        return None
    s = s.strip()
    m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})$", s)
    if m:
        y, mo, d = m.groups()
        return f"{y}-{int(mo):02d}-{int(d):02d}"
    m = re.match(r"^(\d{1,2})\.(\d{1,2})\.(\d{4})$", s)
    if m:
        d, mo, y = m.groups()
        return f"{y}-{int(mo):02d}-{int(d):02d}"
    return s


class EditIdDialog(tk.Toplevel):
    def __init__(self, master, user, terminal_id_ref):
        super().__init__(master)
        self.user = user
        self.terminal_id_ref = terminal_id_ref
        self.result = False

        self.title("Редактировать ID")
        self.resizable(False, False)

        self._build()
        utils.apply_to_all_entries(self)
        self._load()

        self.transient(master)
        self.grab_set()
        self.wait_window(self)

    def _build(self):
        outer = ttk.Frame(self, padding=12)
        outer.pack(fill="both", expand=True)

        # --- Идентификация (только чтение) ---
        idf = ttk.LabelFrame(outer, text="Платёжный ID", padding=8)
        idf.pack(fill="x", pady=(0, 8))

        self.pid_var = tk.StringVar()
        self.m_id_var = tk.StringVar()
        self.m_type_var = tk.StringVar()
        self.transit_var = tk.StringVar()
        self.settle_var = tk.StringVar()

        ttk.Label(idf, text="ID:").grid(row=0, column=0, sticky="w")
        ttk.Label(idf, textvariable=self.pid_var,
                  font=("TkDefaultFont", 10, "bold")).grid(row=0, column=1, sticky="w", padx=(4, 0))

        ttk.Label(idf, text="M/id:").grid(row=1, column=0, sticky="w", pady=(4, 0))
        ttk.Label(idf, textvariable=self.m_id_var).grid(
            row=1, column=1, sticky="w", padx=(4, 0), pady=(4, 0))

        ttk.Label(idf, text="Тип клиента:").grid(row=2, column=0, sticky="w", pady=(4, 0))
        ttk.Label(idf, textvariable=self.m_type_var).grid(
            row=2, column=1, sticky="w", padx=(4, 0), pady=(4, 0))

        ttk.Label(idf, text="Транз/счёт:").grid(row=3, column=0, sticky="w", pady=(4, 0))
        ttk.Entry(idf, textvariable=self.transit_var, width=40).grid(
            row=3, column=1, sticky="w", padx=(4, 0), pady=(4, 0))

        ttk.Label(idf, text="Расч/счёт:").grid(row=4, column=0, sticky="w", pady=(4, 0))
        ttk.Entry(idf, textvariable=self.settle_var, width=40).grid(
            row=4, column=1, sticky="w", padx=(4, 0), pady=(4, 0))

        # --- Информация о точке ---
        info = ttk.LabelFrame(outer, text="Информация о точке", padding=8)
        info.pack(fill="x", pady=(0, 8))

        self.owner_var = tk.StringVar()
        self.point_var = tk.StringVar()
        self.addr_var = tk.StringVar()
        self.phone_var = tk.StringVar()

        ttk.Label(info, text="Ф.И. владельца:").grid(row=0, column=0, sticky="w")
        ttk.Entry(info, textvariable=self.owner_var, width=50).grid(
            row=0, column=1, sticky="we", padx=(4, 0))

        ttk.Label(info, text="Наименование:").grid(row=1, column=0, sticky="w", pady=(4, 0))
        ttk.Entry(info, textvariable=self.point_var, width=50).grid(
            row=1, column=1, sticky="we", padx=(4, 0), pady=(4, 0))

        ttk.Label(info, text="Адрес:").grid(row=2, column=0, sticky="w", pady=(4, 0))
        ttk.Entry(info, textvariable=self.addr_var, width=50).grid(
            row=2, column=1, sticky="we", padx=(4, 0), pady=(4, 0))

        ttk.Label(info, text="Телефон:").grid(row=3, column=0, sticky="w", pady=(4, 0))
        ttk.Entry(info, textvariable=self.phone_var, width=50).grid(
            row=3, column=1, sticky="we", padx=(4, 0), pady=(4, 0))

        # --- Даты и заметка ---
        dp = ttk.Frame(outer)
        dp.pack(fill="x", pady=(0, 8))

        dates = ttk.LabelFrame(dp, text="Даты", padding=8)
        dates.pack(side="left", fill="x", expand=True)

        self.install_var = tk.StringVar()
        self.issue_var = tk.StringVar()

        ttk.Label(dates, text="Установка:").grid(row=0, column=0, sticky="w")
        ttk.Entry(dates, textvariable=self.install_var, width=14).grid(
            row=0, column=1, sticky="w", padx=(4, 0))

        ttk.Label(dates, text="Выдача:").grid(row=1, column=0, sticky="w", pady=(4, 0))
        ttk.Entry(dates, textvariable=self.issue_var, width=14).grid(
            row=1, column=1, sticky="w", padx=(4, 0), pady=(4, 0))

        note_frame = ttk.LabelFrame(dp, text="Заметка", padding=8)
        note_frame.pack(side="left", fill="x", expand=True, padx=(8, 0))

        self.note_var = tk.StringVar()
        ttk.Entry(note_frame, textvariable=self.note_var, width=24).pack(fill="x")

        # --- Кнопки ---
        btns = ttk.Frame(outer)
        btns.pack(fill="x")
        ttk.Button(btns, text="Сохранить", command=self._save).pack(side="right", padx=2)
        ttk.Button(btns, text="Отмена", command=self.destroy).pack(side="right", padx=2)

    def _load(self):
        with database.get_connection() as conn:
            row = conn.execute("""
                SELECT ti.*, m.m_id AS merchant_m_id, m.merchant_type
                FROM terminal_ids ti
                LEFT JOIN merchants m ON m.id = ti.merchant_id
                WHERE ti.id = ?
            """, (self.terminal_id_ref,)).fetchone()
        if row is None:
            messagebox.showerror("Ошибка", "ID не найден", parent=self)
            self.destroy()
            return
        self.pid_var.set(row["payment_id"])
        self.m_id_var.set(row["merchant_m_id"] or "?")
        self.m_type_var.set(row["merchant_type"] or "?")
        self.transit_var.set(row["transit_account"] or "")
        self.settle_var.set(row["settlement_account"] or "")
        self.owner_var.set(row["owner_label"] or "")
        self.point_var.set(row["point_label"] or "")
        self.addr_var.set(row["address"] or "")
        self.phone_var.set(row["phone"] or "")
        self.install_var.set(row["install_date"] or "")
        self.issue_var.set(row["issue_date"] or "")
        self.note_var.set(row["note"] or "")

    def _save(self):
        try:
            with database.get_connection() as conn:
                database.update_terminal_id_fields(
                    conn, self.terminal_id_ref, self.user["id"],
                    transit_account=self.transit_var.get().strip() or None,
                    settlement_account=self.settle_var.get().strip() or None,
                    owner_label=self.owner_var.get().strip() or None,
                    point_label=self.point_var.get().strip() or None,
                    address=self.addr_var.get().strip() or None,
                    phone=self.phone_var.get().strip() or None,
                    install_date=parse_date(self.install_var.get()),
                    issue_date=parse_date(self.issue_var.get()),
                    note=self.note_var.get().strip() or None,
                )
        except Exception as exc:
            messagebox.showerror("Ошибка", str(exc), parent=self)
            return
        self.result = True
        messagebox.showinfo("Готово", "Изменения сохранены", parent=self)
        self.destroy()