# -*- coding: utf-8 -*-
"""Карточка физического терминала: просмотр + редактирование (с блокировкой)."""

import tkinter as tk
from tkinter import ttk, messagebox, simpledialog

import database
from gui import utils
from gui.new_id_dialog import NewIdDialog
from gui.edit_id_dialog import EditIdDialog
from gui.repair_dialog import RepairDialog


PLACE_LABELS = {"merchant": "У клиента", "warehouse": "Склад", "repair_shop": "Мастерская"}
CONDITION_LABELS = {
    "normal": "Норма",
    "in_repair": "В ремонте",
    "written_off": "Списан",
}


class MoveDialog(tk.Toplevel):
    """Диалог перемещения: только кнопки."""

    def __init__(self, master, current_place):
        super().__init__(master)
        self.title("Переместить терминал")
        self.resizable(False, False)
        self.result = None

        ttk.Label(
            self, text=f"Текущее место: {PLACE_LABELS.get(current_place, current_place)}",
            font=("TkDefaultFont", 10, "bold"),
        ).pack(padx=20, pady=(15, 10))

        btns = ttk.Frame(self, padding=10)
        btns.pack()
        ttk.Button(btns, text="К мерчанту", width=15,
                   command=lambda: self._pick("merchant")).pack(side="left", padx=4)
        ttk.Button(btns, text="На склад", width=15,
                   command=lambda: self._pick("warehouse")).pack(side="left", padx=4)
        ttk.Button(btns, text="В мастерскую", width=15,
                   command=lambda: self._pick("repair_shop")).pack(side="left", padx=4)

        ttk.Button(self, text="Отмена", command=self.destroy).pack(pady=(0, 12))

        self.transient(master)
        self.grab_set()
        self.wait_window(self)

    def _pick(self, place):
        self.result = place
        self.destroy()


class TerminalCard(tk.Toplevel):
    def __init__(self, master, user, terminal_id, on_close=None):
        super().__init__(master)
        self.user = user
        self.terminal_id = terminal_id
        self.on_close_callback = on_close
        self.read_only = False

        self.title("Терминал")
        self.geometry("800x640")

        with database.get_connection() as conn:
            ok, lock_info = database.acquire_lock(conn, "terminal", terminal_id, user["id"])
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

    def _build(self):
        top = ttk.Frame(self, padding=10)
        top.pack(fill="x")

        self.sn_var = tk.StringVar()
        self.model_var = tk.StringVar()
        self.ownership_var = tk.StringVar()
        self.note_var = tk.StringVar()

        ttk.Label(top, text="S/N:").grid(row=0, column=0, sticky="w")
        ttk.Label(top, textvariable=self.sn_var, font=("TkDefaultFont", 10, "bold")).grid(
            row=0, column=1, sticky="w"
        )

        ttk.Label(top, text="Модель:").grid(row=1, column=0, sticky="w")
        ttk.Entry(top, textvariable=self.model_var, width=30).grid(row=1, column=1, sticky="w")

        ttk.Label(top, text="Владение:").grid(row=2, column=0, sticky="w")
        ttk.Combobox(top, textvariable=self.ownership_var, values=["bank", "client"],
                     width=27, state="readonly").grid(row=2, column=1, sticky="w")

        ttk.Label(top, text="Заметка:").grid(row=3, column=0, sticky="w")
        ttk.Entry(top, textvariable=self.note_var, width=40).grid(row=3, column=1, sticky="w")

        self.state_label = ttk.Label(top, text="", foreground="blue")
        self.state_label.grid(row=4, column=0, columnspan=2, sticky="w", pady=(6, 0))

        btns = ttk.Frame(top)
        btns.grid(row=5, column=0, columnspan=2, sticky="w", pady=(8, 0))
        ttk.Button(btns, text="Сохранить", command=self._save).pack(side="left", padx=2)
        ttk.Button(btns, text="Сменить SIM/IP", command=self._change_connection).pack(side="left", padx=2)
        ttk.Button(btns, text="Переместить...", command=self._move).pack(side="left", padx=2)
        ttk.Button(btns, text="Ремонт...", command=self._open_repair).pack(side="left", padx=2)
        ttk.Button(btns, text="Добавить ID...", command=self._add_id).pack(side="left", padx=2)
        self.writeoff_btn = ttk.Button(btns, text="Списать", command=self._write_off)
        self.writeoff_btn.pack(side="left", padx=2)
        if self.user["role"] != "admin":
            self.writeoff_btn.state(["disabled"])

        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, padx=10, pady=10)

        # --- "Активные ID" ---
        ids_frame = ttk.Frame(notebook)
        notebook.add(ids_frame, text="Активные ID")
        ids_cols = ("payment_id", "transit_account", "settlement_account", "m_id",
                    "owner_label", "point_label", "address", "phone")
        ids_headings = {
            "payment_id": "ID", "transit_account": "Транз.счёт", "settlement_account": "Расч.счёт",
            "m_id": "M/id", "owner_label": "ФИО/плательщик", "point_label": "Точка/назначение",
            "address": "Адрес", "phone": "Телефон",
        }
        self.ids_tree = ttk.Treeview(ids_frame, columns=ids_cols, show="headings", height=8)
        for c in ids_cols:
            self.ids_tree.heading(c, text=ids_headings[c])
            self.ids_tree.column(c, width=100, anchor="w")
        self.ids_tree.pack(fill="both", expand=True)
        self.ids_tree.bind("<Double-1>", lambda e: self._edit_selected_id())

        self._binding_ids_by_iid = {}

        btns_below = ttk.Frame(ids_frame)
        btns_below.pack(anchor="w", pady=(4, 0))
        ttk.Button(btns_below, text="Редактировать ID",
                   command=self._edit_selected_id).pack(side="left", padx=2)
        self.close_id_btn = ttk.Button(btns_below, text="Закрыть выбранный ID",
                                        command=self._close_selected_id)
        self.close_id_btn.pack(side="left", padx=2)

        # --- "SN история" ---
        hist_frame = ttk.Frame(notebook)
        notebook.add(hist_frame, text="SN история")
        hist_cols = ("payment_id", "owner_label", "point_label", "m_id", "bound_from", "bound_to")
        hist_headings = {
            "payment_id": "ID", "owner_label": "ФИО/плательщик", "point_label": "Точка/назначение",
            "m_id": "M/id", "bound_from": "Привязан с", "bound_to": "Отвязан",
        }
        self.history_tree = ttk.Treeview(hist_frame, columns=hist_cols, show="headings", height=10)
        for c in hist_cols:
            self.history_tree.heading(c, text=hist_headings[c])
            self.history_tree.column(c, width=120, anchor="w")
        self.history_tree.pack(fill="both", expand=True)

        self.conn_tree = self._make_tab(notebook, "SIM/IP история",
                                         ("sim_number", "ip_address", "valid_from", "valid_to"),
                                         {"sim_number": "SIM", "ip_address": "IP",
                                          "valid_from": "С", "valid_to": "По"})
        self.place_tree = self._make_tab(notebook, "Перемещения",
                                          ("place_type", "m_id", "moved_at", "comment"),
                                          {"place_type": "Место", "m_id": "M/id",
                                           "moved_at": "Когда", "comment": "Комментарий"})
        self.repair_tree = self._make_tab(notebook, "Ремонты",
                                           ("reason", "sent_at", "returned_at", "result"),
                                           {"reason": "Причина", "sent_at": "Отправлен",
                                            "returned_at": "Вернулся", "result": "Результат"})
        self.repair_tree.bind("<Double-1>", self._edit_repair_by_dbl)

        if self.read_only:
            for child in top.winfo_children():
                if isinstance(child, (ttk.Entry, ttk.Combobox)):
                    child.state(["disabled"])
            for b in btns.winfo_children():
                b.state(["disabled"])
            self.close_id_btn.state(["disabled"])

    def _make_tab(self, notebook, title, cols, headings):
        frame = ttk.Frame(notebook)
        notebook.add(frame, text=title)
        tree = ttk.Treeview(frame, columns=cols, show="headings", height=8)
        for c in cols:
            tree.heading(c, text=headings[c])
            tree.column(c, width=110, anchor="w")
        tree.pack(fill="both", expand=True)
        return tree

    def _load(self):
        with database.get_connection() as conn:
            data = database.get_terminal_full(conn, self.terminal_id)
        if data is None:
            messagebox.showerror("Ошибка", "Терминал не найден")
            self.destroy()
            return
        self.data = data
        t = data["terminal"]
        self.sn_var.set(t["serial_number"] or "(без S/N)")
        self.model_var.set(t["model"] or "")
        self.ownership_var.set(t["ownership"])
        self.note_var.set(t["note"] or "")
        self.state_label.config(
            text=f"Место: {PLACE_LABELS.get(data['current_place'], data['current_place'])}   "
                 f"Состояние: {CONDITION_LABELS.get(data['condition'], data['condition'])}"
        )

        self.ids_tree.delete(*self.ids_tree.get_children())
        self._binding_ids_by_iid.clear()
        for b in data["bindings"]:
            if b["bound_to"] is not None:
                continue
            iid = self.ids_tree.insert("", "end", values=(
                b["payment_id"], b["transit_account"] or "", b["settlement_account"] or "",
                b["m_id"] or "", b["owner_label"] or "", b["point_label"] or "",
                b["address"] or "", b["phone"] or "",
            ))
            self._binding_ids_by_iid[iid] = (b["id"], b["bound_to"])

        self.history_tree.delete(*self.history_tree.get_children())
        for b in data["bindings"]:
            if b["bound_to"] is None:
                continue
            self.history_tree.insert("", "end", values=(
                b["payment_id"], b["owner_label"] or "", b["point_label"] or "",
                b["m_id"] or "", b["bound_from"], b["bound_to"],
            ))

        self.conn_tree.delete(*self.conn_tree.get_children())
        for c in data["connections"]:
            self.conn_tree.insert("", "end", values=(
                c["sim_number"] or "", c["ip_address"] or "", c["valid_from"], c["valid_to"] or "сейчас",
            ))

        self.place_tree.delete(*self.place_tree.get_children())
        for p in data["placements"]:
            self.place_tree.insert("", "end", values=(
                PLACE_LABELS.get(p["place_type"], p["place_type"]),
                p["m_id"] or "", p["moved_at"], p["comment"] or "",
            ))

        self.repair_tree.delete(*self.repair_tree.get_children())
        self._repair_ids_by_iid = {}
        for r in data["repairs"]:
            iid = self.repair_tree.insert("", "end", values=(
                r["reason"] or "", r["sent_at"] or "", r["returned_at"] or "",
                r["result"] or "",
            ))
            self._repair_ids_by_iid[iid] = r["id"]

    def _save(self):
        if self.read_only:
            return
        with database.get_connection() as conn:
            database.update_terminal(
                conn, self.terminal_id, self.user["id"],
                model=self.model_var.get() or None,
                ownership=self.ownership_var.get(),
                note=self.note_var.get() or None,
            )
        self._load()
        messagebox.showinfo("Готово", "Изменения сохранены", parent=self)

    def _change_connection(self):
        if self.read_only:
            return
        sim = simpledialog.askstring("SIM", "Новый номер SIM (пусто, если Ethernet):", parent=self)
        if sim is None:
            return
        ip = simpledialog.askstring("IP", "Новый IP-адрес (пусто, если нет):", parent=self)
        with database.get_connection() as conn:
            database.change_connection(conn, self.terminal_id, sim or None, ip or None, self.user["id"])
        self._load()

    def _move(self):
        if self.read_only:
            return
        dlg = MoveDialog(self, self.data["current_place"] if self.data else "warehouse")
        place = dlg.result
        if place is None:
            return

        merchant_db_id = None
        if place == "merchant":
            m_id = simpledialog.askstring("M/id", "M/id мерчанта:", parent=self)
            if not m_id:
                return
            with database.get_connection() as conn:
                rows = database.search_merchants(conn, m_id)
            match = next((r for r in rows if r["m_id"] == m_id), None)
            if not match:
                messagebox.showerror("Ошибка", f"Мерчант с M/id={m_id} не найден", parent=self)
                return
            merchant_db_id = match["id"]

        comment = simpledialog.askstring("Комментарий", "Комментарий (необязательно):", parent=self) or None
        with database.get_connection() as conn:
            database.move_terminal(conn, self.terminal_id, place, self.user["id"],
                                    merchant_id=merchant_db_id, comment=comment)
        self._load()

    def _open_repair(self):
        if self.read_only:
            return
        dlg = RepairDialog(self, self.user, self.terminal_id)
        if dlg.result:
            self._load()

    def _edit_repair_by_dbl(self, event):
        if self.read_only:
            return
        selection = self.repair_tree.selection()
        if not selection:
            return
        repair_id = self._repair_ids_by_iid.get(selection[0])
        if repair_id is None:
            return
        dlg = RepairDialog(self, self.user, self.terminal_id, repair_id=repair_id)
        if dlg.result:
            self._load()

    def _write_off(self):
        if self.user["role"] != "admin":
            return
        reason = simpledialog.askstring("Списание", "Причина списания:", parent=self)
        if reason is None:
            return
        if not messagebox.askyesno("Подтверждение", "Списание необратимо. Продолжить?", parent=self):
            return
        with database.get_connection() as conn:
            try:
                database.write_off_terminal(conn, self.terminal_id, reason, self.user)
            except (PermissionError, ValueError) as exc:
                messagebox.showerror("Ошибка", str(exc), parent=self)
                return
        self._load()
        messagebox.showinfo("Готово", "Терминал списан.", parent=self)

    def _add_id(self):
        if self.read_only:
            return
        sn = self.data["terminal"]["serial_number"] if self.data else None
        dlg = NewIdDialog(self, self.user, prefill_sn=sn)
        if dlg.result:
            self._load()

    def _edit_selected_id(self):
        if self.read_only:
            return
        selection = self.ids_tree.selection()
        if not selection:
            messagebox.showinfo("Выбор", "Сначала выберите ID в таблице", parent=self)
            return
        binding_id, _ = self._binding_ids_by_iid[selection[0]]
        with database.get_connection() as conn:
            row = conn.execute(
                "SELECT terminal_id_ref FROM terminal_id_bindings WHERE id = ?",
                (binding_id,),
            ).fetchone()
        if row is None:
            return
        dlg = EditIdDialog(self, self.user, row["terminal_id_ref"])
        if dlg.result:
            self._load()

    def _close_selected_id(self):
        if self.read_only:
            return
        selection = self.ids_tree.selection()
        if not selection:
            return
        info = self._binding_ids_by_iid.get(selection[0])
        if info is None:
            return
        binding_id, bound_to = info
        if bound_to is not None:
            messagebox.showinfo("Инфо", "Этот ID уже закрыт", parent=self)
            return
        comment = simpledialog.askstring("Закрыть ID", "Причина закрытия (необязательно):", parent=self)
        try:
            with database.get_connection() as conn:
                moved_to_warehouse = database.close_terminal_id(
                    conn, binding_id, self.user["id"], comment=comment or None
                )
        except ValueError as exc:
            messagebox.showerror("Ошибка", str(exc), parent=self)
            return
        self._load()
        if moved_to_warehouse:
            messagebox.showinfo(
                "Готово",
                "ID закрыт. Это была последняя активная привязка -- терминал перемещён на склад.",
                parent=self,
            )

    def _on_close(self):
        if not self.read_only:
            with database.get_connection() as conn:
                database.release_lock(conn, "terminal", self.terminal_id, self.user["id"])
        if self.on_close_callback:
            self.on_close_callback()
        self.destroy()