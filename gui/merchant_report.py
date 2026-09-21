# -*- coding: utf-8 -*-
"""Окно отчёта по клиенту: сводка, ID, терминалы, история."""

import tkinter as tk
from tkinter import ttk, messagebox

import database


TYPE_LABELS = {"bank": "BANK", "edara": "EDARA", "telekeci": "TELEKEÇI"}
PLACE_LABELS = {"merchant": "У клиента", "warehouse": "Склад", "repair_shop": "Мастерская"}
CONDITION_LABELS = {"normal": "Норма", "in_repair": "В ремонте", "written_off": "Списан"}
OWNERSHIP_SHORT = {"bank": "Банк", "client": "Клиент"}


class MerchantReportWindow(tk.Toplevel):
    def __init__(self, master, user, merchant_id):
        super().__init__(master)
        self.user = user
        self.merchant_id = merchant_id
        self.title("Отчёт по клиенту")
        self.geometry("1080x740")

        with database.get_connection() as conn:
            data = database.get_merchant_full_report(conn, merchant_id)
        if data is None:
            messagebox.showerror("Ошибка", "Мерчант не найден", parent=self)
            self.destroy()
            return
        self.data = data
        self._row_by_iid = {}

        self._build()
        self.transient(master)
        self.grab_set()

    # ------------------------------------------------------------------
    def _build(self):
        m = self.data["merchant"]
        contact = self.data["current_contact"] or {}
        st = self.data["current_status"]
        status_text = "закрыт" if st == "closed" else "активен"

        info = ttk.LabelFrame(self, text="Клиент", padding=8)
        info.pack(fill="x", padx=10, pady=(10, 4))

        ttk.Label(info, text=f"M/id: {m['m_id']}",
                  font=("TkDefaultFont", 11, "bold")).grid(row=0, column=0, sticky="w", padx=(0, 20))
        ttk.Label(info, text=f"Тип: {TYPE_LABELS.get(m['merchant_type'], m['merchant_type'])}").grid(
            row=0, column=1, sticky="w", padx=(0, 20))
        ttk.Label(info, text=f"Статус: {status_text}",
                  foreground=("red" if st == "closed" else "green")).grid(
            row=0, column=2, sticky="w", padx=(0, 20))
        ttk.Label(info, text=f"Адрес: {contact.get('address') or '—'}").grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(4, 0))
        ttk.Label(info, text=f"Телефон: {contact.get('phone') or '—'}").grid(
            row=1, column=2, columnspan=2, sticky="w", pady=(4, 0))

        # Сводка
        s = self.data["stats"]
        stats = ttk.LabelFrame(self, text="Сводка", padding=8)
        stats.pack(fill="x", padx=10, pady=(0, 4))
        ttk.Label(stats, text=f"Терминалов: {s['terminals_total']}  (активных: {s['terminals_active']})",
                  font=("TkDefaultFont", 10, "bold")).pack(side="left", padx=15)
        ttk.Label(stats, text=f"ID: {s['ids_total']}  (активных: {s['ids_active']})",
                  font=("TkDefaultFont", 10, "bold")).pack(side="left", padx=15)

        # Вкладки
        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, padx=10, pady=(4, 4))

        self.tree_active = self._make_tree(
            notebook, "Активные",
            cols=("terminal", "owner", "point", "transit", "settle", "issue_date"),
            headings={"terminal": "S/N", "owner": "Ф.И. владельца",
                      "point": "Наименование", "transit": "Транз/счёт",
                      "settle": "Расч/счёт", "issue_date": "Дата выдачи"},
            widths={"terminal": 130, "owner": 180, "point": 220,
                    "transit": 160, "settle": 130, "issue_date": 100},
            show_tree=True,
        )
        self.tree_all_ids = self._make_tree(
            notebook, "Все ID",
            cols=("payment_id", "status", "sn", "owner", "point", "issue_date"),
            headings={"payment_id": "ID", "status": "Статус", "sn": "S/N",
                      "owner": "Ф.И. владельца", "point": "Наименование",
                      "issue_date": "Дата выдачи"},
            widths={"payment_id": 130, "status": 80, "sn": 130,
                    "owner": 180, "point": 240, "issue_date": 100},
        )
        self.tree_terminals = self._make_tree(
            notebook, "Терминалы",
            cols=("sn", "model", "ownership", "place", "condition", "active_ids"),
            headings={"sn": "S/N", "model": "Модель", "ownership": "Собств.",
                      "place": "Место", "condition": "Состояние", "active_ids": "Активных ID"},
            widths={"sn": 140, "model": 140, "ownership": 80, "place": 110,
                    "condition": 110, "active_ids": 90},
        )
        self.tree_history = self._make_tree(
            notebook, "История",
            cols=("changed_at", "user", "entity", "field", "old", "new"),
            headings={"changed_at": "Когда", "user": "Кто",
                      "entity": "Объект", "field": "Поле",
                      "old": "Было", "new": "Стало"},
            widths={"changed_at": 150, "user": 140, "entity": 120,
                    "field": 110, "old": 180, "new": 180},
        )
        self.tree_active.bind("<Double-1>", self._open_from_active)
        self.tree_all_ids.bind("<Double-1>", self._open_from_all_ids)
        self.tree_terminals.bind("<Double-1>", self._open_from_terminals)

        # Кнопки
        btns = ttk.Frame(self, padding=(10, 0, 10, 10))
        btns.pack(fill="x")
        ttk.Button(btns, text="Закрыть", command=self.destroy).pack(side="right", padx=2)

        self._render_all()

    def _make_tree(self, notebook, title, cols, headings, widths, show_tree=False):
        frame = ttk.Frame(notebook)
        notebook.add(frame, text=title)
        if show_tree:
            tree = ttk.Treeview(frame, columns=cols, show="tree headings", height=16)
            tree.heading("#0", text="Терминал / ID")
            tree.column("#0", width=260, anchor="w")
        else:
            tree = ttk.Treeview(frame, columns=cols, show="headings", height=16)
        for c in cols:
            tree.heading(c, text=headings[c])
            tree.column(c, width=widths[c], anchor="w")
        tree.pack(fill="both", expand=True)
        tree.tag_configure("group", font=("TkDefaultFont", 9, "bold"), background="#eef3f9")
        return tree

    # ------------------------------------------------------------------
    def _render_all(self):
        # --- Активные (дерево) ---
        self.tree_active.delete(*self.tree_active.get_children())
        self._row_by_iid = {}
        for term in self.data["active_terminals"]:
            n = len(term["ids"])
            node = self.tree_active.insert(
                "", "end",
                text=f"S/N {term['serial_number'] or '—'}  •  {term['model'] or '—'}  •  {n} ID",
                values=("", "", "", "", "", ""),
                tags=("group",),
                open=True,
            )
            self._row_by_iid[node] = ("terminal", term["terminal_id"])
            for r in term["ids"]:
                iid = self.tree_active.insert(
                    node, "end",
                    text=f"    {r['payment_id']}",
                    values=(term["serial_number"] or "", r["owner_label"] or "",
                            r["point_label"] or "", r["transit_account"] or "",
                            r["settlement_account"] or "", r["issue_date"] or ""),
                )
                self._row_by_iid[iid] = ("id", r["id"])

        # --- Все ID ---
        self.tree_all_ids.delete(*self.tree_all_ids.get_children())
        for r in self.data["all_ids"]:
            status = "активен" if r["status"] == "active" else "закрыт"
            iid = self.tree_all_ids.insert("", "end", values=(
                r["payment_id"], status, r["active_terminal_sn"] or "",
                r["owner_label"] or "", r["point_label"] or "",
                r["issue_date"] or "",
            ))
            self._row_by_iid[iid] = ("id", r["id"])

        # --- Терминалы ---
        self.tree_terminals.delete(*self.tree_terminals.get_children())
        for r in self.data["terminals"]:
            iid = self.tree_terminals.insert("", "end", values=(
                r["serial_number"] or "(без S/N)", r["model"] or "",
                OWNERSHIP_SHORT.get(r["ownership"], r["ownership"] or ""),
                PLACE_LABELS.get(r["current_place"], r["current_place"] or "—"),
                CONDITION_LABELS.get(r["condition"], r["condition"] or "—"),
                r["active_ids"],
            ))
            self._row_by_iid[iid] = ("terminal", r["terminal_id"])

        # --- История ---
        self.tree_history.delete(*self.tree_history.get_children())
        for h in self.data["history"]:
            entity_map = {
                "merchant": "Клиент",
                "terminal_id": "ID",
                "terminal": "Терминал",
                "terminal_repair": "Ремонт",
                "terminal_id_binding": "Привязка",
            }
            entity = entity_map.get(h["entity_type"], h["entity_type"])
            iid = self.tree_history.insert("", "end", values=(
                h["changed_at"], h["user_name"] or "—",
                entity, h["field_name"] or "",
                h["old_value"] or "", h["new_value"] or "",
            ))

    # ------------------------------------------------------------------
    def _selected(self, tree):
        sel = tree.selection()
        if not sel:
            return None
        return self._row_by_iid.get(sel[0])

    def _open_from_active(self, event):
        info = self._selected(self.tree_active)
        if not info:
            return
        kind, obj_id = info
        if kind == "terminal":
            self._open_terminal(obj_id)
        elif kind == "id":
            self._edit_id(obj_id)

    def _open_from_all_ids(self, event):
        info = self._selected(self.tree_all_ids)
        if info and info[0] == "id":
            self._edit_id(info[1])

    def _open_from_terminals(self, event):
        info = self._selected(self.tree_terminals)
        if info and info[0] == "terminal":
            self._open_terminal(info[1])

    def _open_terminal(self, terminal_id):
        from gui.terminal_card import TerminalCard
        TerminalCard(self, self.user, terminal_id, on_close=self._reload_report)

    def _edit_id(self, terminal_id_ref):
        from gui.edit_id_dialog import EditIdDialog
        dlg = EditIdDialog(self, self.user, terminal_id_ref)
        if dlg.result:
            self._reload_report()

    def _reload_report(self):
        with database.get_connection() as conn:
            data = database.get_merchant_full_report(conn, self.merchant_id)
        if data:
            self.data = data
            self._render_all()