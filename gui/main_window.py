# -*- coding: utf-8 -*-
"""Главное окно приложения.

Слева -- вкладки (в виде кнопок) "Активные" / "Склад" / "E-POS". Сверху --
сводка, которая пересчитывается под текущую открытую вкладку. По центру --
список (сгруппированный по типу клиента на вкладке "Активные"), справа --
подробности выбранной строки и действия над ней."""

import tkinter as tk
from tkinter import ttk, messagebox, simpledialog

import config
import database
from gui import utils
from gui.terminal_card import TerminalCard
from gui.merchant_card import MerchantCard
from gui.users_window import UsersWindow

TYPE_LABELS = {"bank": "BANK", "edara": "EDARA", "telekeci": "TELEKEÇI", "hk": "H/K"}
PLACE_LABELS = {"merchant": "У клиента", "warehouse": "Склад", "repair_shop": "Мастерская"}
CONDITION_LABELS = {
    "normal": "Норма", "in_repair": "В ремонте",
    "awaiting_firmware": "Ждёт прошивку", "written_off": "Списан",
}
_PREFERRED_TYPE_ORDER = ("bank", "edara", "telekeci", "hk")


def _type_label(code):
    return TYPE_LABELS.get(code, (code or "?").upper())


class MainWindow(tk.Tk):
    def __init__(self, user):
        super().__init__()
        self.user = user
        self.current_tab = "active"
        self.filter_var = tk.StringVar(value="")
        self.query_var = tk.StringVar()

        self.title(f"HalkTerminalManager v{config.APP_VERSION} -- {user['full_name']} ({user['role']})")
        self.geometry("1250x720")

        self._style = ttk.Style(self)
        self._style.configure("Selected.TButton", font=("TkDefaultFont", 9, "bold"))

        self._build_menu()
        self._build_stats()
        self._build_body()
        utils.apply_to_all_entries(self)

        self._select_tab("active")

    # ------------------------------------------------------------------
    # Меню
    # ------------------------------------------------------------------
    def _build_menu(self):
        menubar = tk.Menu(self)

        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Выход", command=self.destroy)
        menubar.add_cascade(label="Файл", menu=file_menu)

        if self.user["role"] == "admin":
            admin_menu = tk.Menu(menubar, tearoff=0)
            admin_menu.add_command(label="Пользователи...", command=self._open_users_window)
            menubar.add_cascade(label="Администрирование", menu=admin_menu)

        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="О программе", command=self._show_about)
        menubar.add_cascade(label="Справка", menu=help_menu)

        self.config(menu=menubar)

    def _open_users_window(self):
        UsersWindow(self, self.user)

    def _show_about(self):
        with database.get_connection() as conn:
            history = database.get_version_history(conn, limit=10)
        lines = [f"HalkTerminalManager, версия {config.APP_VERSION}", "", "История версий:"]
        for h in history:
            lines.append(f"  {h['version']} -- {h['installed_at']}" + (f" ({h['notes']})" if h["notes"] else ""))
        messagebox.showinfo("О программе", "\n".join(lines), parent=self)

    # ------------------------------------------------------------------
    # Сводка (пересчитывается под текущую вкладку)
    # ------------------------------------------------------------------
    def _build_stats(self):
        self.stats_frame = ttk.LabelFrame(self, text="Сводка", padding=10)
        self.stats_frame.pack(fill="x", padx=10, pady=(10, 5))

    def _set_stats(self, lines):
        for w in self.stats_frame.winfo_children():
            w.destroy()
        for i, text in enumerate(lines):
            ttk.Label(self.stats_frame, text=text).grid(row=i // 4, column=i % 4, sticky="w", padx=10, pady=2)

    # ------------------------------------------------------------------
    # Основная разметка: сайдбар слева, список + детали справа
    # ------------------------------------------------------------------
    def _build_body(self):
        body = ttk.Frame(self)
        body.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        self.sidebar = ttk.Frame(body, padding=(0, 0, 10, 0))
        self.sidebar.pack(side="left", fill="y")
        self.tab_buttons = {}
        for key, label in (("active", "Активные"), ("warehouse", "Склад"), ("epos", "E-POS")):
            b = ttk.Button(self.sidebar, text=label, command=lambda k=key: self._select_tab(k))
            b.pack(fill="x", pady=2)
            self.tab_buttons[key] = b

        content = ttk.Frame(body)
        content.pack(side="left", fill="both", expand=True)

        search_row = ttk.Frame(content)
        search_row.pack(fill="x", pady=(0, 5))
        ttk.Label(search_row, text="Поиск:").pack(side="left")
        search_entry = ttk.Entry(search_row, textvariable=self.query_var, width=40)
        search_entry.pack(side="left", padx=6)
        search_entry.bind("<Return>", lambda e: self._refresh_current_list())
        ttk.Button(search_row, text="Найти", command=self._refresh_current_list).pack(side="left")
        ttk.Button(search_row, text="Сброс", command=self._reset_search).pack(side="left", padx=4)

        self.filter_row = ttk.Frame(content)
        self.filter_row.pack(fill="x", pady=(0, 5))

        paned = ttk.PanedWindow(content, orient="horizontal")
        paned.pack(fill="both", expand=True)

        tree_frame = ttk.Frame(paned)
        paned.add(tree_frame, weight=3)
        self.detail_frame = ttk.LabelFrame(paned, text="Подробности", padding=10)
        paned.add(self.detail_frame, weight=2)

        self.tree = ttk.Treeview(tree_frame, show="headings", height=24)
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", lambda e: self._on_select())
        self.tree.bind("<Double-1>", lambda e: self._on_double_click())
        self.tree.tag_configure("group", font=("TkDefaultFont", 9, "bold"), background="#e6e6e6")

        self.detail_body = ttk.Frame(self.detail_frame)
        self.detail_body.pack(fill="both", expand=True)
        self.detail_actions = ttk.Frame(self.detail_frame)
        self.detail_actions.pack(fill="x", pady=(10, 0))
        self._clear_detail()

    def _reset_search(self):
        self.query_var.set("")
        self._refresh_current_list()

    # ------------------------------------------------------------------
    # Переключение вкладок
    # ------------------------------------------------------------------
    def _select_tab(self, tab):
        self.current_tab = tab
        for key, b in self.tab_buttons.items():
            b.configure(style="Selected.TButton" if key == tab else "TButton")
        self._build_filter_row()
        self._refresh_current_list()

    def _build_filter_row(self):
        for w in self.filter_row.winfo_children():
            w.destroy()
        if self.current_tab not in ("active", "epos"):
            return
        with database.get_connection() as conn:
            if self.current_tab == "active":
                types = sorted({r["merchant_type"] for r in database.get_active_terminal_ids(conn) if r["merchant_type"]})
            else:
                types = sorted({r["merchant_type"] for r in database.get_epos_terminals(conn) if r["merchant_type"]})
        ordered = [t for t in _PREFERRED_TYPE_ORDER if t in types] + [t for t in types if t not in _PREFERRED_TYPE_ORDER]
        ttk.Label(self.filter_row, text="Фильтр:").pack(side="left")
        ttk.Radiobutton(
            self.filter_row, text="Все", variable=self.filter_var, value="",
            command=self._refresh_current_list,
        ).pack(side="left", padx=4)
        for t in ordered:
            ttk.Radiobutton(
                self.filter_row, text=_type_label(t), variable=self.filter_var, value=t,
                command=self._refresh_current_list,
            ).pack(side="left", padx=4)
        self.filter_var.set("")

    # ------------------------------------------------------------------
    # Обновление списка + сводки под текущую вкладку
    # ------------------------------------------------------------------
    def _refresh_current_list(self):
        query = self.query_var.get().strip() or None
        if self.current_tab == "active":
            self._configure_active_columns()
            with database.get_connection() as conn:
                rows = database.get_active_terminal_ids(conn, merchant_type=self.filter_var.get() or None, query=query)
                stats = database.get_active_dashboard_stats(conn)
            self._render_active_tree(rows)
            lines = [f"Активных всего: {stats['total']}"]
            lines += [f"{_type_label(k)}: {v}" for k, v in stats.items() if k != "total"]
            self._set_stats(lines)
        elif self.current_tab == "warehouse":
            self._configure_warehouse_columns()
            with database.get_connection() as conn:
                rows = database.get_warehouse_terminals(conn, query=query)
                stats = database.get_warehouse_dashboard_stats(conn)
            self._render_warehouse_tree(rows)
            self._set_stats([
                f"На складе: {stats['warehouse']}",
                f"В мастерской: {stats['repair_shop']}",
                f"Списано: {stats['written_off']}",
                f"Всего: {stats['total']}",
            ])
        else:  # epos
            self._configure_active_columns()
            with database.get_connection() as conn:
                rows = database.get_epos_terminals(conn, query=query)
                stats = database.get_epos_dashboard_stats(conn)
            self._render_epos_tree(rows)
            self._set_stats([f"E-POS терминалов: {stats['total']}"])
        self._clear_detail()

    # ------------------------------------------------------------------
    # Вкладка "Активные"
    # ------------------------------------------------------------------
    def _configure_active_columns(self):
        cols = ("num", "id", "type", "owner", "point", "address", "phone")
        headings = {
            "num": "№", "id": "ID", "type": "Тип", "owner": "Ф.И. владельца",
            "point": "Наименование организации", "address": "Адрес", "phone": "Телефон",
        }
        widths = {"num": 45, "id": 90, "type": 70, "owner": 160, "point": 200, "address": 160, "phone": 110}
        self.tree.configure(columns=cols)
        for c in cols:
            self.tree.heading(c, text=headings[c])
            self.tree.column(c, width=widths[c], anchor="w")

    def _render_active_tree(self, rows):
        self.tree.delete(*self.tree.get_children())
        self._row_by_iid = {}
        groups = {}
        for r in rows:
            groups.setdefault(r["merchant_type"] or "unknown", []).append(r)
        order = [t for t in _PREFERRED_TYPE_ORDER if t in groups]
        order += sorted(t for t in groups if t not in _PREFERRED_TYPE_ORDER)
        seq = 0
        for t in order:
            group_rows = groups[t]
            self.tree.insert(
                "", "end",
                values=("", f"— {_type_label(t)} ({len(group_rows)}) —", "", "", "", "", ""),
                tags=("group",),
            )
            for r in group_rows:
                seq += 1
                iid = self.tree.insert(
                    "", "end",
                    values=(seq, r["payment_id"], _type_label(t), r["owner_label"] or "",
                            r["point_label"] or "", r["address"] or "", r["phone"] or ""),
                    tags=("item",),
                )
                self._row_by_iid[iid] = ("active", r["binding_id"])

    # ------------------------------------------------------------------
    # Вкладка "E-POS" (те же колонки, что у "Активные")
    # ------------------------------------------------------------------
    def _render_epos_tree(self, rows):
        self.tree.delete(*self.tree.get_children())
        self._row_by_iid = {}
        groups = {}
        for r in rows:
            groups.setdefault(r["merchant_type"] or "unknown", []).append(r)
        order = [t for t in _PREFERRED_TYPE_ORDER if t in groups]
        order += sorted(t for t in groups if t not in _PREFERRED_TYPE_ORDER)
        seq = 0
        for t in order:
            group_rows = groups[t]
            self.tree.insert(
                "", "end",
                values=("", f"— {_type_label(t)} ({len(group_rows)}) —", "", "", "", "", ""),
                tags=("group",),
            )
            for r in group_rows:
                seq += 1
                iid = self.tree.insert(
                    "", "end",
                    values=(seq, r["payment_id"] or "(без ID)", _type_label(t), r["owner_label"] or "",
                            r["point_label"] or "", r["address"] or "", r["phone"] or ""),
                    tags=("item",),
                )
                self._row_by_iid[iid] = ("epos", r["binding_id"], r["terminal_id"])

    # ------------------------------------------------------------------
    # Вкладка "Склад"
    # ------------------------------------------------------------------
    def _configure_warehouse_columns(self):
        cols = ("num", "sn", "model", "place", "condition", "moved_by", "moved_at", "comment")
        headings = {
            "num": "№", "sn": "S/N", "model": "Модель", "place": "Место", "condition": "Состояние",
            "moved_by": "Кем перемещён", "moved_at": "Когда", "comment": "Комментарий",
        }
        widths = {"num": 40, "sn": 110, "model": 110, "place": 90, "condition": 100,
                  "moved_by": 130, "moved_at": 130, "comment": 160}
        self.tree.configure(columns=cols)
        for c in cols:
            self.tree.heading(c, text=headings[c])
            self.tree.column(c, width=widths[c], anchor="w")

    def _render_warehouse_tree(self, rows):
        self.tree.delete(*self.tree.get_children())
        self._row_by_iid = {}
        for i, r in enumerate(rows, start=1):
            place_text = "Списан" if r["condition"] == "written_off" else PLACE_LABELS.get(r["current_place"], r["current_place"])
            iid = self.tree.insert(
                "", "end",
                values=(i, r["serial_number"] or "(без S/N)", r["model"] or "", place_text,
                        CONDITION_LABELS.get(r["condition"], r["condition"]),
                        r["moved_by_name"] or "", r["last_moved_at"] or "", r["last_comment"] or ""),
                tags=("item",),
            )
            self._row_by_iid[iid] = ("warehouse", r["terminal_id"], r)

    # ------------------------------------------------------------------
    # Выбор строки / детали
    # ------------------------------------------------------------------
    def _on_select(self):
        selection = self.tree.selection()
        if not selection:
            self._clear_detail()
            return
        info = self._row_by_iid.get(selection[0])
        if info is None:
            self._clear_detail()
            return
        if info[0] in ("active", "epos"):
            self._show_id_detail(info[1])
        elif info[0] == "warehouse":
            self._show_warehouse_detail(info[1], info[2])

    def _on_double_click(self):
        selection = self.tree.selection()
        if not selection:
            return
        info = self._row_by_iid.get(selection[0])
        if info is None:
            return
        if info[0] == "active":
            with database.get_connection() as conn:
                d = database.get_terminal_id_detail(conn, info[1])
            if d:
                self._open_terminal_card(d["terminal_id"])
        elif info[0] == "epos":
            self._open_terminal_card(info[2])
        elif info[0] == "warehouse":
            self._open_terminal_card(info[1])

    def _clear_detail(self):
        for w in self.detail_body.winfo_children():
            w.destroy()
        for w in self.detail_actions.winfo_children():
            w.destroy()
        ttk.Label(self.detail_body, text="Выберите строку слева, чтобы увидеть подробности.").pack(anchor="w")

    def _show_detail(self, fields, actions):
        for w in self.detail_body.winfo_children():
            w.destroy()
        for i, (caption, value) in enumerate(fields):
            ttk.Label(self.detail_body, text=f"{caption}:", font=("TkDefaultFont", 9, "bold")).grid(
                row=i, column=0, sticky="ne", padx=4, pady=3
            )
            ttk.Label(self.detail_body, text=value or "-", wraplength=260, justify="left").grid(
                row=i, column=1, sticky="nw", padx=4, pady=3
            )
        for w in self.detail_actions.winfo_children():
            w.destroy()
        for label, cmd in actions:
            ttk.Button(self.detail_actions, text=label, command=cmd).pack(side="left", padx=2)

    def _show_id_detail(self, binding_id):
        with database.get_connection() as conn:
            d = database.get_terminal_id_detail(conn, binding_id)
        if d is None:
            self._clear_detail()
            return
        fields = [
            ("ID", d["payment_id"]),
            ("M/id", d["m_id"]),
            ("Модель терминала", d["model"]),
            ("S/N", d["serial_number"]),
            ("Номер СИМ", d["sim_number"]),
            ("IP", d["ip_address"]),
            ("Тип", _type_label(d["merchant_type"])),
            ("Транз/счёт", d["transit_account"]),
            ("Расчётный счёт", d["settlement_account"]),
        ]
        actions = [
            ("Карточка терминала", lambda: self._open_terminal_card(d["terminal_id"])),
            ("Карточка мерчанта", lambda: self._open_merchant_card(d["merchant_id"])),
        ]
        if self.current_tab == "active":
            actions.insert(0, ("Закрыть", lambda: self._close_active(binding_id)))
        self._show_detail(fields, actions)

    def _show_warehouse_detail(self, terminal_id, row):
        place_text = "Списан" if row["condition"] == "written_off" else PLACE_LABELS.get(row["current_place"], row["current_place"])
        fields = [
            ("S/N", row["serial_number"] or "(без S/N)"),
            ("Модель", row["model"]),
            ("Владение", row["ownership"]),
            ("Место", place_text),
            ("Состояние", CONDITION_LABELS.get(row["condition"], row["condition"])),
            ("Кем перемещён", row["moved_by_name"]),
            ("Когда", row["last_moved_at"]),
            ("Комментарий", row["last_comment"]),
        ]
        actions = [("Карточка терминала", lambda: self._open_terminal_card(terminal_id))]
        self._show_detail(fields, actions)

    # ------------------------------------------------------------------
    # Действия
    # ------------------------------------------------------------------
    def _close_active(self, binding_id):
        if not messagebox.askyesno("Подтверждение", "Закрыть этот ID у клиента?", parent=self):
            return
        comment = simpledialog.askstring("Комментарий", "Комментарий (необязательно):", parent=self) or None
        with database.get_connection() as conn:
            moved_to_warehouse = database.close_terminal_id(conn, binding_id, self.user["id"], comment=comment)
        if moved_to_warehouse:
            messagebox.showinfo(
                "Готово",
                "ID закрыт. Это был последний активный ID терминала -- он автоматически перемещён на склад.",
                parent=self,
            )
        else:
            messagebox.showinfo("Готово", "ID закрыт.", parent=self)
        self._refresh_current_list()

    def _open_terminal_card(self, terminal_id):
        TerminalCard(self, self.user, terminal_id, on_close=self._refresh_current_list)

    def _open_merchant_card(self, merchant_id):
        MerchantCard(self, self.user, merchant_id, on_close=self._refresh_current_list)
