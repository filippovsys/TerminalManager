# -*- coding: utf-8 -*-
"""Диалог "Выдать новый ID": создаёт terminal_ids, привязывает к терминалу
и мерчанту (создавая их при необходимости) и опционально выдаёт клиенту.

Если M/id или S/N уже существуют -- подтягивает последние сохранённые
данные (адрес, телефон, SIM, IP), чтобы не вводить заново."""

import re
import tkinter as tk
from datetime import date
from tkinter import ttk, messagebox

import database
from gui import utils


TYPE_LABELS = {"bank": "BANK", "edara": "EDARA", "telekeci": "TELEKEÇI"}


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


class NewIdDialog(tk.Toplevel):
    def __init__(self, master, user, prefill_m_id=None, prefill_sn=None):
        super().__init__(master)
        self.user = user
        self.result = False
        self.prefill_m_id = prefill_m_id
        self.prefill_sn = prefill_sn

        self.title("Выдать новый ID")
        self.resizable(False, False)

        self._build()
        utils.apply_to_all_entries(self)
        self._check_merchant()
        self._check_terminal()

        self.transient(master)
        self.grab_set()
        self.wait_window(self)

    def _build(self):
        outer = ttk.Frame(self, padding=12)
        outer.pack(fill="both", expand=True)

        # --- Клиент ---
        cli = ttk.LabelFrame(outer, text="Клиент (мерчант)", padding=8)
        cli.pack(fill="x", pady=(0, 8))

        self.m_id_var = tk.StringVar(value=self.prefill_m_id or "")
        self.m_id_status = tk.StringVar(value="")
        self.m_type_var = tk.StringVar(value="telekeci")

        ttk.Label(cli, text="M/id:").grid(row=0, column=0, sticky="w")
        e = ttk.Entry(cli, textvariable=self.m_id_var, width=30)
        e.grid(row=0, column=1, sticky="w", padx=(4, 0))
        e.bind("<FocusOut>", lambda ev: self._check_merchant())
        e.bind("<KeyRelease>", lambda ev: self._check_merchant())

        ttk.Label(cli, textvariable=self.m_id_status, foreground="gray").grid(
            row=0, column=2, sticky="w", padx=(8, 0))

        ttk.Label(cli, text="Тип (для нового):").grid(row=1, column=0, sticky="w", pady=(4, 0))
        self.m_type_cb = ttk.Combobox(
            cli, textvariable=self.m_type_var,
            values=["bank", "edara", "telekeci"], state="readonly", width=27,
        )
        self.m_type_cb.grid(row=1, column=1, sticky="w", padx=(4, 0), pady=(4, 0))

        # --- Терминал ---
        term = ttk.LabelFrame(outer, text="Физический терминал", padding=8)
        term.pack(fill="x", pady=(0, 8))

        self.sn_var = tk.StringVar(value=self.prefill_sn or "")
        self.sn_status = tk.StringVar(value="")
        self.model_var = tk.StringVar()
        self.ownership_var = tk.StringVar(value="bank")

        ttk.Label(term, text="S/N:").grid(row=0, column=0, sticky="w")
        e2 = ttk.Entry(term, textvariable=self.sn_var, width=30)
        e2.grid(row=0, column=1, sticky="w", padx=(4, 0))
        e2.bind("<FocusOut>", lambda ev: self._check_terminal())
        e2.bind("<KeyRelease>", lambda ev: self._check_terminal())

        ttk.Label(term, textvariable=self.sn_status, foreground="gray").grid(
            row=0, column=2, sticky="w", padx=(8, 0))

        ttk.Label(term, text="Модель (для нового):").grid(row=1, column=0, sticky="w", pady=(4, 0))
        self.model_cb = ttk.Combobox(term, textvariable=self.model_var, width=27)
        with database.get_connection() as conn:
            models = database.get_distinct_models(conn)
        self.model_cb["values"] = models
        self.model_cb.grid(row=1, column=1, sticky="w", padx=(4, 0), pady=(4, 0))

        ttk.Label(term, text="Владение (для нового):").grid(row=2, column=0, sticky="w", pady=(4, 0))
        self.own_cb = ttk.Combobox(
            term, textvariable=self.ownership_var,
            values=["bank", "client"], state="readonly", width=27,
        )
        self.own_cb.grid(row=2, column=1, sticky="w", padx=(4, 0), pady=(4, 0))

        # --- ID ---
        idf = ttk.LabelFrame(outer, text="Платёжный ID", padding=8)
        idf.pack(fill="x", pady=(0, 8))

        self.pid_var = tk.StringVar()
        self.transit_var = tk.StringVar()
        self.settle_var = tk.StringVar()

        ttk.Label(idf, text="ID:").grid(row=0, column=0, sticky="w")
        ttk.Entry(idf, textvariable=self.pid_var, width=30).grid(row=0, column=1, sticky="w", padx=(4, 0))

        ttk.Label(idf, text="Транз/счёт:").grid(row=1, column=0, sticky="w", pady=(4, 0))
        ttk.Entry(idf, textvariable=self.transit_var, width=30).grid(
            row=1, column=1, sticky="w", padx=(4, 0), pady=(4, 0))

        ttk.Label(idf, text="Расч/счёт:").grid(row=2, column=0, sticky="w", pady=(4, 0))
        ttk.Entry(idf, textvariable=self.settle_var, width=30).grid(
            row=2, column=1, sticky="w", padx=(4, 0), pady=(4, 0))

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

        # --- Даты и подключение ---
        dp = ttk.Frame(outer)
        dp.pack(fill="x", pady=(0, 8))

        dates = ttk.LabelFrame(dp, text="Даты", padding=8)
        dates.pack(side="left", fill="x", expand=True)

        self.install_var = tk.StringVar()
        self.issue_var = tk.StringVar(value=date.today().isoformat())

        ttk.Label(dates, text="Установка:").grid(row=0, column=0, sticky="w")
        ttk.Entry(dates, textvariable=self.install_var, width=14).grid(
            row=0, column=1, sticky="w", padx=(4, 0))

        ttk.Label(dates, text="Выдача:").grid(row=1, column=0, sticky="w", pady=(4, 0))
        ttk.Entry(dates, textvariable=self.issue_var, width=14).grid(
            row=1, column=1, sticky="w", padx=(4, 0), pady=(4, 0))

        conn = ttk.LabelFrame(dp, text="Подключение", padding=8)
        conn.pack(side="left", fill="x", expand=True, padx=(8, 0))

        self.sim_var = tk.StringVar()
        self.ip_var = tk.StringVar()

        ttk.Label(conn, text="SIM:").grid(row=0, column=0, sticky="w")
        ttk.Entry(conn, textvariable=self.sim_var, width=18).grid(
            row=0, column=1, sticky="w", padx=(4, 0))

        ttk.Label(conn, text="IP:").grid(row=1, column=0, sticky="w", pady=(4, 0))
        ttk.Entry(conn, textvariable=self.ip_var, width=18).grid(
            row=1, column=1, sticky="w", padx=(4, 0), pady=(4, 0))

        # --- Чекбокс ---
        self.issue_to_client_var = tk.IntVar(value=1)
        ttk.Checkbutton(
            outer, text="Выдать клиенту (терминал переедет к этому мерчанту)",
            variable=self.issue_to_client_var,
        ).pack(anchor="w", pady=(0, 8))

        # --- Кнопки ---
        btns = ttk.Frame(outer)
        btns.pack(fill="x")
        ttk.Button(btns, text="Создать и выдать", command=self._do_create).pack(side="right", padx=2)
        ttk.Button(btns, text="Отмена", command=self.destroy).pack(side="right", padx=2)

    # ------------------------------------------------------------------
    def _check_merchant(self):
        m_id = self.m_id_var.get().strip()
        if not m_id:
            self.m_id_status.set("")
            return
        with database.get_connection() as conn:
            row = conn.execute(
                "SELECT id, merchant_type FROM merchants WHERE m_id = ?", (m_id,)
            ).fetchone()
            if row:
                self.m_id_status.set(
                    f"✓ найден, тип: {TYPE_LABELS.get(row['merchant_type'], row['merchant_type'])}"
                )
                self.m_type_var.set(row["merchant_type"])
                self.m_type_cb.state(["disabled"])

                # --- автозаполнение из последнего ID этого мерчанта ---
                last = conn.execute("""
                    SELECT owner_label, point_label, address, phone
                    FROM terminal_ids
                    WHERE merchant_id = ?
                    ORDER BY id DESC LIMIT 1
                """, (row["id"],)).fetchone()
                if last:
                    if not self.owner_var.get() and last["owner_label"]:
                        self.owner_var.set(last["owner_label"])
                    if not self.point_var.get() and last["point_label"]:
                        self.point_var.set(last["point_label"])
                    if not self.addr_var.get() and last["address"]:
                        self.addr_var.set(last["address"])
                    if not self.phone_var.get() and last["phone"]:
                        self.phone_var.set(last["phone"])
            else:
                self.m_id_status.set("• будет создан новый")
                self.m_type_cb.state(["!disabled", "readonly"])

    def _check_terminal(self):
        sn = self.sn_var.get().strip()
        if not sn:
            self.sn_status.set("")
            return
        with database.get_connection() as conn:
            row = conn.execute(
                "SELECT id, model, ownership FROM terminals WHERE serial_number = ?", (sn,)
            ).fetchone()
            if row:
                self.sn_status.set(f"✓ найден: {row['model'] or '—'}")
                self.model_var.set(row["model"] or "")
                self.ownership_var.set(row["ownership"])
                self.model_cb.state(["disabled"])
                self.own_cb.state(["disabled"])

                # --- автозаполнение SIM/IP из последнего подключения ---
                conn_row = conn.execute("""
                    SELECT sim_number, ip_address
                    FROM connection_history
                    WHERE terminal_id = ? AND valid_to IS NULL
                    ORDER BY id DESC LIMIT 1
                """, (row["id"],)).fetchone()
                if conn_row:
                    if not self.sim_var.get() and conn_row["sim_number"]:
                        self.sim_var.set(conn_row["sim_number"])
                    if not self.ip_var.get() and conn_row["ip_address"]:
                        self.ip_var.set(conn_row["ip_address"])
            else:
                self.sn_status.set("• будет создан новый")
                self.model_cb.state(["!disabled"])
                self.own_cb.state(["!disabled", "readonly"])

    def _do_create(self):
        pid = self.pid_var.get().strip()
        if not pid:
            messagebox.showerror("Ошибка", "Укажите ID (payment_id)", parent=self)
            return
        m_id = self.m_id_var.get().strip()
        if not m_id:
            messagebox.showerror("Ошибка", "Укажите M/id клиента", parent=self)
            return
        sn = self.sn_var.get().strip() or None

        try:
            with database.get_connection() as conn:
                existing = conn.execute(
                    "SELECT id FROM terminal_ids WHERE payment_id = ?", (pid,)
                ).fetchone()
                if existing:
                    raise ValueError(f"ID {pid} уже есть в базе. Используйте другой ID.")

                row = conn.execute(
                    "SELECT id, merchant_type FROM merchants WHERE m_id = ?", (m_id,)
                ).fetchone()
                if row:
                    merchant_id = row["id"]
                else:
                    mtype = self.m_type_var.get() or "telekeci"
                    merchant_id = database.create_merchant(
                        conn, m_id, mtype, self.user["id"],
                        note="создан при выдаче нового ID",
                    )

                terminal_id = None
                if sn:
                    row = conn.execute(
                        "SELECT id FROM terminals WHERE serial_number = ?", (sn,)
                    ).fetchone()
                    if row:
                        terminal_id = row["id"]
                    else:
                        terminal_id = database.create_terminal(
                            conn, sn,
                            self.model_var.get().strip() or None,
                            self.ownership_var.get() or "bank",
                            None,
                            self.user["id"],
                            note="создан при выдаче нового ID",
                        )

                cur = conn.execute(
                    "INSERT INTO terminal_ids (payment_id, transit_account, settlement_account, "
                    "merchant_id, owner_label, point_label, address, phone, "
                    "install_date, issue_date) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        pid,
                        self.transit_var.get().strip() or None,
                        self.settle_var.get().strip() or None,
                        merchant_id,
                        self.owner_var.get().strip() or None,
                        self.point_var.get().strip() or None,
                        self.addr_var.get().strip() or None,
                        self.phone_var.get().strip() or None,
                        parse_date(self.install_var.get()),
                        parse_date(self.issue_var.get()),
                    ),
                )
                terminal_id_ref = cur.lastrowid

                if terminal_id:
                    database.bind_terminal_id(conn, terminal_id, terminal_id_ref, self.user["id"])

                    sim = self.sim_var.get().strip() or None
                    ip = self.ip_var.get().strip() or None
                    if sim or ip:
                        database.change_connection(conn, terminal_id, sim, ip, self.user["id"])

                    if self.issue_to_client_var.get():
                        database.move_terminal(
                            conn, terminal_id, "merchant", self.user["id"],
                            merchant_id=merchant_id,
                            comment=f"выдан клиенту (ID {pid})",
                        )

                database.log_change(
                    conn, self.user["id"], "terminal_id", terminal_id_ref,
                    "created", None, pid,
                )

        except Exception as exc:
            messagebox.showerror("Ошибка", str(exc), parent=self)
            return

        self.result = True
        messagebox.showinfo("Готово", f"ID {pid} создан и привязан.", parent=self)
        self.destroy()