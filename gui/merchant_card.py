# -*- coding: utf-8 -*-
"""Карточка мерчанта (клиента): просмотр + редактирование (с блокировкой)."""

import tkinter as tk
from tkinter import ttk, messagebox, simpledialog

import database
from gui import utils
from gui.new_id_dialog import NewIdDialog


class MerchantCard(tk.Toplevel):
    def __init__(self, master, user, merchant_id, on_close=None):
        super().__init__(master)
        from gui.icons import set_window_icon
        set_window_icon(self)
        self.user = user
        self.merchant_id = merchant_id
        self.on_close_callback = on_close
        self.read_only = False

        self.title("Мерчант")
        self.geometry("680x520")

        with database.get_connection() as conn:
            ok, lock_info = database.acquire_lock(conn, "merchant", merchant_id, user["id"])
        if not ok:
            self.read_only = True
            messagebox.showwarning(
                "Карточка занята",
                f"Редактирует: {lock_info['locked_by_name']} с {lock_info['locked_at']}.\n"
                f"Карточка открыта только для просмотра.",
                parent=self,
            )

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._build()
        utils.apply_to_all_entries(self)
        self._load()

    # ------------------------------------------------------------------
    def _build(self):
        top = ttk.Frame(self, padding=10)
        top.pack(fill="x")

        self.m_id_var = tk.StringVar()
        self.type_var = tk.StringVar()
        self.note_var = tk.StringVar()
        self.address_var = tk.StringVar()
        self.phone_var = tk.StringVar()

        ttk.Label(top, text="M/id:").grid(row=0, column=0, sticky="w")
        ttk.Label(top, textvariable=self.m_id_var, font=("TkDefaultFont", 10, "bold")).grid(
            row=0, column=1, sticky="w"
        )

        ttk.Label(top, text="Тип:").grid(row=1, column=0, sticky="w")
        ttk.Combobox(top, textvariable=self.type_var, values=["telekeci", "edara", "bank"],
                     width=27, state="readonly").grid(row=1, column=1, sticky="w")

        ttk.Label(top, text="Заметка:").grid(row=2, column=0, sticky="w")
        ttk.Entry(top, textvariable=self.note_var, width=40).grid(row=2, column=1, sticky="w")

        ttk.Label(top, text="Адрес:").grid(row=3, column=0, sticky="w")
        ttk.Entry(top, textvariable=self.address_var, width=40).grid(row=3, column=1, sticky="w")

        ttk.Label(top, text="Телефон:").grid(row=4, column=0, sticky="w")
        ttk.Entry(top, textvariable=self.phone_var, width=40).grid(row=4, column=1, sticky="w")

        self.status_label = ttk.Label(top, text="", foreground="blue")
        self.status_label.grid(row=5, column=0, columnspan=2, sticky="w", pady=(6, 0))

        btns = ttk.Frame(top)
        btns.grid(row=6, column=0, columnspan=2, sticky="w", pady=(8, 0))
        ttk.Button(btns, text="Сохранить", command=self._save).pack(side="left", padx=2)
        ttk.Button(btns, text="Сохранить адрес/телефон", command=self._save_contact).pack(side="left", padx=2)
        ttk.Button(btns, text="Добавить ID...", command=self._add_id).pack(side="left", padx=2)
        ttk.Button(btns, text="Отчёт по клиенту...", command=self._open_report).pack(side="left", padx=2)
        ttk.Button(btns, text="Закрыть обслуживание", command=lambda: self._set_status("closed")).pack(
            side="left", padx=2
        )
        ttk.Button(btns, text="Открыть заново", command=lambda: self._set_status("opened")).pack(
            side="left", padx=2
        )

        self.ids_tree = ttk.Treeview(
            self, columns=("payment_id", "terminal_sn", "owner_label", "point_label"),
            show="headings", height=14,
        )
        for c, title in (("payment_id", "ID"), ("terminal_sn", "S/N терминала"),
                         ("owner_label", "ФИО/плательщик"), ("point_label", "Точка/назначение")):
            self.ids_tree.heading(c, text=title)
            self.ids_tree.column(c, width=140, anchor="w")
        self.ids_tree.pack(fill="both", expand=True, padx=10, pady=10)

        if self.read_only:
            for child in top.winfo_children():
                if isinstance(child, (ttk.Entry, ttk.Combobox)):
                    child.state(["disabled"])
            for b in btns.winfo_children():
                b.state(["disabled"])

    # ------------------------------------------------------------------
    def _load(self):
        with database.get_connection() as conn:
            data = database.get_merchant(conn, self.merchant_id)
            terminal_sn_by_id = {}
            for row in data["terminal_ids"]:
                sn_row = conn.execute(
                    """
                    SELECT t.serial_number FROM terminal_id_bindings b
                    JOIN terminals t ON t.id = b.terminal_id
                    WHERE b.terminal_id_ref = ?
                    ORDER BY (b.bound_to IS NULL) DESC LIMIT 1
                    """,
                    (row["id"],),
                ).fetchone()
                terminal_sn_by_id[row["id"]] = sn_row["serial_number"] if sn_row else ""
        if data is None:
            messagebox.showerror("Ошибка", "Мерчант не найден")
            self.destroy()
            return
        self.data = data
        m = data["merchant"]
        self.m_id_var.set(m["m_id"])
        self.type_var.set(m["merchant_type"] or "")
        self.note_var.set(m["note"] or "")
        contact = data["current_contact"] or {}
        self.address_var.set(contact.get("address") or "")
        self.phone_var.set(contact.get("phone") or "")

        st = data["current_status"]
        status_text = "закрыт" if st == "closed" else "активен"
        self.status_label.config(text=f"Текущий статус: {status_text}")

        self.ids_tree.delete(*self.ids_tree.get_children())
        for r in data["terminal_ids"]:
            self.ids_tree.insert("", "end", values=(
                r["payment_id"], terminal_sn_by_id.get(r["id"], ""),
                r["owner_label"] or "", r["point_label"] or "",
            ))

    def _save(self):
        if self.read_only:
            return
        with database.get_connection() as conn:
            database.update_merchant(
                conn, self.merchant_id, self.user["id"],
                merchant_type=self.type_var.get() or None,
                note=self.note_var.get() or None,
            )
        self._load()
        messagebox.showinfo("Готово", "Изменения сохранены", parent=self)

    def _save_contact(self):
        if self.read_only:
            return
        with database.get_connection() as conn:
            database.set_merchant_contact(
                conn, self.merchant_id, self.address_var.get() or None,
                self.phone_var.get() or None, self.user["id"],
            )
        self._load()
        messagebox.showinfo("Готово", "Адрес/телефон сохранены", parent=self)

    def _add_id(self):
        if self.read_only:
            return
        m_id = self.data["merchant"]["m_id"] if self.data else None
        dlg = NewIdDialog(self, self.user, prefill_m_id=m_id)
        if dlg.result:
            self._load()

    def _open_report(self):
        from gui.merchant_report import MerchantReportWindow
        MerchantReportWindow(self, self.user, self.merchant_id)

    def _set_status(self, status):
        if self.read_only:
            return
        comment = simpledialog.askstring("Комментарий", "Комментарий (необязательно):", parent=self) or None
        with database.get_connection() as conn:
            database.set_merchant_status(conn, self.merchant_id, status, self.user["id"], comment=comment)
        self._load()

    # ------------------------------------------------------------------
    def _on_close(self):
        if not self.read_only:
            with database.get_connection() as conn:
                database.release_lock(conn, "merchant", self.merchant_id, self.user["id"])
        if self.on_close_callback:
            self.on_close_callback()
        self.destroy()