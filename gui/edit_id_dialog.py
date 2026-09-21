# -*- coding: utf-8 -*-
"""Диалог "Редактировать ID": правка полей terminal_ids, смена мерчанта
и смена привязанного терминала."""

import re
import tkinter as tk
from tkinter import ttk, messagebox

import database
from gui import utils
from gui.terminal_picker_dialog import TerminalPickerDialog


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


class EditIdDialog(tk.Toplevel):
    def __init__(self, master, user, terminal_id_ref):
        super().__init__(master)
        self.user = user
        self.terminal_id_ref = terminal_id_ref
        self.result = False

        self.title("Редактировать ID")
        self.geometry("720x640")
        self.resizable(False, False)

        # Кэш мерчантов для combobox
        self._merchants = []
        self._merchant_display = []  # строки для combobox
        self._current_merchant_id = None

        self._build()
        utils.apply_to_all_entries(self)
        self._load_merchants()
        self._load()

        self.transient(master)
        self.grab_set()
        self.wait_window(self)

    # ------------------------------------------------------------------
    def _build(self):
        outer = ttk.Frame(self, padding=12)
        outer.pack(fill="both", expand=True)

        # --- Идентификация (только чтение) ---
        idf = ttk.LabelFrame(outer, text="Платёжный ID", padding=8)
        idf.pack(fill="x", pady=(0, 8))

        self.pid_var = tk.StringVar()
        ttk.Label(idf, text="ID:").grid(row=0, column=0, sticky="w")
        ttk.Label(idf, textvariable=self.pid_var,
                  font=("TkDefaultFont", 10, "bold")).grid(row=0, column=1, sticky="w", padx=(4, 0))

        self.transit_var = tk.StringVar()
        ttk.Label(idf, text="Транз/счёт:").grid(row=1, column=0, sticky="w", pady=(4, 0))
        ttk.Entry(idf, textvariable=self.transit_var, width=40).grid(
            row=1, column=1, sticky="w", padx=(4, 0), pady=(4, 0))

        self.settle_var = tk.StringVar()
        ttk.Label(idf, text="Расч/счёт:").grid(row=2, column=0, sticky="w", pady=(4, 0))
        ttk.Entry(idf, textvariable=self.settle_var, width=40).grid(
            row=2, column=1, sticky="w", padx=(4, 0), pady=(4, 0))

        # --- Клиент ---
        cli = ttk.LabelFrame(outer, text="Клиент (мерчант)", padding=8)
        cli.pack(fill="x", pady=(0, 8))

        ttk.Label(cli, text="M/id и владелец:").grid(row=0, column=0, sticky="w")
        self.merchant_var = tk.StringVar()
        self.merchant_cb = ttk.Combobox(cli, textvariable=self.merchant_var,
                                          width=60, state="readonly")
        self.merchant_cb.grid(row=0, column=1, sticky="w", padx=(4, 0), pady=(2, 0))

        # --- Терминал ---
        term = ttk.LabelFrame(outer, text="Привязка к физическому терминалу", padding=8)
        term.pack(fill="x", pady=(0, 8))

        self.terminal_var = tk.StringVar(value="— не привязан —")
        ttk.Label(term, text="Текущий S/N:").grid(row=0, column=0, sticky="w")
        ttk.Label(term, textvariable=self.terminal_var,
                  font=("TkDefaultFont", 10, "bold")).grid(row=0, column=1, sticky="w", padx=(4, 0))

        self.binding_since_var = tk.StringVar()
        ttk.Label(term, text="Привязан с:").grid(row=1, column=0, sticky="w", pady=(4, 0))
        ttk.Label(term, textvariable=self.binding_since_var, foreground="gray").grid(
            row=1, column=1, sticky="w", padx=(4, 0), pady=(4, 0))

        tbtns = ttk.Frame(term)
        tbtns.grid(row=2, column=0, columnspan=2, sticky="w", pady=(6, 0))
        self.btn_rebind = ttk.Button(tbtns, text="Перепривязать к другому...",
                                      command=self._rebind_terminal)
        self.btn_rebind.pack(side="left", padx=2)
        self.btn_unbind = ttk.Button(tbtns, text="Отвязать от терминала",
                                      command=self._unbind_terminal)
        self.btn_unbind.pack(side="left", padx=2)

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
        ttk.Entry(dates, textvariable=self.install_var, width=14).grid(row=0, column=1, sticky="w", padx=(4, 0))
        ttk.Label(dates, text="Выдача:").grid(row=1, column=0, sticky="w", pady=(4, 0))
        ttk.Entry(dates, textvariable=self.issue_var, width=14).grid(row=1, column=1, sticky="w", padx=(4, 0), pady=(4, 0))

        note_frame = ttk.LabelFrame(dp, text="Заметка", padding=8)
        note_frame.pack(side="left", fill="x", expand=True, padx=(8, 0))
        self.note_var = tk.StringVar()
        ttk.Entry(note_frame, textvariable=self.note_var, width=24).pack(fill="x")

        # --- Кнопки ---
        btns = ttk.Frame(outer)
        btns.pack(fill="x")
        ttk.Button(btns, text="Сохранить", command=self._save).pack(side="right", padx=2)
        ttk.Button(btns, text="Отмена", command=self.destroy).pack(side="right", padx=2)

    # ------------------------------------------------------------------
    def _load_merchants(self):
        with database.get_connection() as conn:
            self._merchants = database.list_merchants_for_combo(conn)
        self._merchant_display = []
        for m in self._merchants:
            mtype = TYPE_LABELS.get(m["merchant_type"], m["merchant_type"])
            owner = (m["owner_label"] or "")[:50]
            label = f"{m['m_id']}  •  {mtype}"
            if owner:
                label += f"  •  {owner}"
            self._merchant_display.append(label)
        self.merchant_cb["values"] = self._merchant_display

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
        self.transit_var.set(row["transit_account"] or "")
        self.settle_var.set(row["settlement_account"] or "")
        self.owner_var.set(row["owner_label"] or "")
        self.point_var.set(row["point_label"] or "")
        self.addr_var.set(row["address"] or "")
        self.phone_var.set(row["phone"] or "")
        self.install_var.set(row["install_date"] or "")
        self.issue_var.set(row["issue_date"] or "")
        self.note_var.set(row["note"] or "")

        # Мерчант
        self._current_merchant_id = row["merchant_id"]
        for i, m in enumerate(self._merchants):
            if m["id"] == self._current_merchant_id:
                self.merchant_var.set(self._merchant_display[i])
                break

        # Текущая привязка терминала
        self._load_binding()

    def _load_binding(self):
        with database.get_connection() as conn:
            b = conn.execute("""
                SELECT b.id AS binding_id, b.bound_from,
                       t.id AS terminal_id, t.serial_number, t.model
                FROM terminal_id_bindings b
                JOIN terminals t ON t.id = b.terminal_id
                WHERE b.terminal_id_ref = ? AND b.bound_to IS NULL
                ORDER BY b.id DESC LIMIT 1
            """, (self.terminal_id_ref,)).fetchone()
        self._current_binding = dict(b) if b else None
        if b:
            self.terminal_var.set(f"{b['serial_number'] or '(без S/N)'} ({b['model'] or '—'})")
            self.binding_since_var.set(b["bound_from"])
            self.btn_unbind.state(["!disabled"])
            self.btn_rebind.configure(text="Перепривязать к другому...")
        else:
            self.terminal_var.set("— не привязан —")
            self.binding_since_var.set("")
            self.btn_unbind.state(["disabled"])
            self.btn_rebind.configure(text="Привязать к терминалу...")

    # ------------------------------------------------------------------
    def _save(self):
        # Мерчант
        selected_idx = self.merchant_cb.current()
        new_merchant_id = self._current_merchant_id
        if selected_idx is not None and 0 <= selected_idx < len(self._merchants):
            new_merchant_id = self._merchants[selected_idx]["id"]
        merchant_changed = (new_merchant_id != self._current_merchant_id)

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
                if merchant_changed:
                    old_m = conn.execute(
                        "SELECT m_id FROM merchants WHERE id = ?", (self._current_merchant_id,)
                    ).fetchone()
                    new_m = conn.execute(
                        "SELECT m_id FROM merchants WHERE id = ?", (new_merchant_id,)
                    ).fetchone()
                    conn.execute(
                        "UPDATE terminal_ids SET merchant_id = ? WHERE id = ?",
                        (new_merchant_id, self.terminal_id_ref),
                    )
                    database.log_change(
                        conn, self.user["id"], "terminal_id", self.terminal_id_ref,
                        "merchant_id",
                        old_m["m_id"] if old_m else None,
                        new_m["m_id"] if new_m else None,
                    )
        except Exception as exc:
            messagebox.showerror("Ошибка", str(exc), parent=self)
            return
        self.result = True
        messagebox.showinfo("Готово", "Изменения сохранены", parent=self)
        self.destroy()

    def _unbind_terminal(self):
        if not self._current_binding:
            return
        if not messagebox.askyesno(
            "Подтверждение",
            f"Отвязать ID от терминала {self._current_binding['serial_number']}?\n"
            "ID останется в базе, но без физического терминала.",
            parent=self,
        ):
            return
        try:
            with database.get_connection() as conn:
                database.unbind_terminal_id(conn, self._current_binding["binding_id"], self.user["id"])
        except Exception as exc:
            messagebox.showerror("Ошибка", str(exc), parent=self)
            return
        self._load_binding()
        self.result = True

    def _rebind_terminal(self):
        dlg = TerminalPickerDialog(self, self.user)
        if not dlg.result:
            return
        new_tid = dlg.result["terminal_id"]

        # Если уже привязан -- закрываем старую привязку
        try:
            with database.get_connection() as conn:
                if self._current_binding:
                    database.unbind_terminal_id(
                        conn, self._current_binding["binding_id"], self.user["id"]
                    )
                database.bind_terminal_id(conn, new_tid, self.terminal_id_ref, self.user["id"])
                # Если терминал был на складе -- выдаём клиенту (по текущему мерчанту ID)
                row = conn.execute(
                    "SELECT merchant_id FROM terminal_ids WHERE id = ?",
                    (self.terminal_id_ref,),
                ).fetchone()
                if row and row["merchant_id"]:
                    conn.execute(
                        "INSERT INTO terminal_placements (terminal_id, place_type, merchant_id, comment, changed_by) "
                        "VALUES (?, 'merchant', ?, ?, ?)",
                        (new_tid, row["merchant_id"],
                         f"перепривязан к ID {self.pid_var.get()}", self.user["id"]),
                    )
        except Exception as exc:
            messagebox.showerror("Ошибка", str(exc), parent=self)
            return
        self._load_binding()
        self.result = True