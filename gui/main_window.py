# -*- coding: utf-8 -*-
"""Главное окно: вкладки под сводкой, дерево с группировкой
Тип клиента -> Физ.терминал -> ID."""

import tkinter as tk
from tkinter import ttk, messagebox, simpledialog

import config
import database
from gui import utils
from gui.terminal_card import TerminalCard
from gui.merchant_card import MerchantCard
from gui.users_window import UsersWindow
from gui.merchants_list_window import MerchantsListWindow
from gui.terminals_list_window import TerminalsListWindow

TYPE_LABELS = {"bank": "BANK", "edara": "EDARA", "telekeci": "TELEKEÇI", "hk": "H/K"}
PLACE_LABELS = {"merchant": "У клиента", "warehouse": "Склад", "repair_shop": "Мастерская"}
CONDITION_LABELS = {
    "normal": "Норма", "in_repair": "В ремонте",
    "awaiting_firmware": "Ждёт прошивку", "written_off": "Списан",
}
OWNERSHIP_SHORT = {"bank": "Банк", "client": "Клиент"}
OWNERSHIP_DISPLAY = {"bank": "Банк", "client": "Клиент"}
_PREFERRED_TYPE_ORDER = ("bank", "edara", "telekeci", "hk")


def _type_label(code):
    return TYPE_LABELS.get(code, (code or "?").upper())


def _first_not_empty(rows, key):
    """Первое непустое значение среди строк (для агрегации по терминалу)."""
    for r in rows:
        v = r.get(key)
        if v:
            return v
    return ""


class MainWindow(tk.Tk):
    def __init__(self, user):
        super().__init__()
        self.user = user
        self.current_tab = "active"
        self.filter_var = tk.StringVar(value="")
        self.model_filter_var = tk.StringVar(value="")
        self.ownership_filter_var = tk.StringVar(value="Все")
        self.query_var = tk.StringVar()
        self._pending_restore = None
        self._row_by_iid = {}

        self.title(f"HalkTerminalManager v{config.APP_VERSION} -- {user['full_name']} ({user['role']})")
        self.geometry("1360x780")

        self._style = ttk.Style(self)
        self._style.configure("Selected.TButton", font=("TkDefaultFont", 9, "bold"))

        self._build_menu()
        self._build_stats()
        self._build_tabs()
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

        refs_menu = tk.Menu(menubar, tearoff=0)
        refs_menu.add_command(label="Мерчанты...", command=self._open_merchants_list)
        refs_menu.add_command(label="Терминалы...", command=self._open_terminals_list)
        menubar.add_cascade(label="Справочники", menu=refs_menu)

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

    def _open_merchants_list(self):
        MerchantsListWindow(self, self.user)

    def _open_terminals_list(self):
        TerminalsListWindow(self, self.user)

    def _show_about(self):
        with database.get_connection() as conn:
            history = database.get_version_history(conn, limit=10)
        lines = [f"HalkTerminalManager, версия {config.APP_VERSION}", "", "История версий:"]
        for h in history:
            lines.append(f"  {h['version']} -- {h['installed_at']}" + (f" ({h['notes']})" if h["notes"] else ""))
        messagebox.showinfo("О программе", "\n".join(lines), parent=self)

    # ------------------------------------------------------------------
    # Сводка
    # ------------------------------------------------------------------
    def _build_stats(self):
        self.stats_frame = ttk.LabelFrame(self, text="Сводка", padding=8)
        self.stats_frame.pack(fill="x", padx=10, pady=(10, 4))

    def _set_stats(self, lines):
        for w in self.stats_frame.winfo_children():
            w.destroy()
        for i, text in enumerate(lines):
            ttk.Label(self.stats_frame, text=text).grid(row=i // 5, column=i % 5, sticky="w", padx=10, pady=2)

    # ------------------------------------------------------------------
    # Вкладки (горизонтально под сводкой)
    # ------------------------------------------------------------------
    def _build_tabs(self):
        self.tab_bar = ttk.Frame(self, padding=(10, 0))
        self.tab_bar.pack(fill="x")
        self.tab_buttons = {}
        for key, label in (
            ("active", "Активные"),
            ("warehouse", "Склад"),
            ("written_off", "Списанные"),
            ("epos", "E-POS"),
        ):
            b = ttk.Button(self.tab_bar, text=label, command=lambda k=key: self._select_tab(k))
            b.pack(side="left", padx=1, pady=2)
            self.tab_buttons[key] = b

    # ------------------------------------------------------------------
    # Основная разметка
    # ------------------------------------------------------------------
    def _build_body(self):
        content = ttk.Frame(self)
        content.pack(fill="both", expand=True, padx=10, pady=(4, 10))

        search_row = ttk.Frame(content)
        search_row.pack(fill="x", pady=(0, 4))
        ttk.Label(search_row, text="Поиск:").pack(side="left")
        search_entry = ttk.Entry(search_row, textvariable=self.query_var, width=40)
        search_entry.pack(side="left", padx=6)
        search_entry.bind("<Return>", lambda e: self._refresh_current_list())
        ttk.Button(search_row, text="Найти", command=self._refresh_current_list).pack(side="left")
        ttk.Button(search_row, text="Сброс", command=self._reset_search).pack(side="left", padx=4)

        self.filter_row = ttk.Frame(content)
        self.filter_row.pack(fill="x", pady=(0, 4))

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
        self.tree.tag_configure("group", font=("TkDefaultFont", 9, "bold"), background="#d9e2ef")
        self.tree.tag_configure("terminal", font=("TkDefaultFont", 9, "bold"), background="#eef3f9")

        self.detail_body = ttk.Frame(self.detail_frame)
        self.detail_body.pack(fill="both", expand=True)
        self.detail_actions = ttk.Frame(self.detail_frame)
        self.detail_actions.pack(fill="x", pady=(10, 0))
        self._clear_detail()

    def _reset_search(self):
        self.query_var.set("")
        self.model_filter_var.set("")
        self.ownership_filter_var.set("Все")
        self._refresh_current_list()

    # ------------------------------------------------------------------
    # Переключение вкладок
    # ------------------------------------------------------------------
    def _select_tab(self, tab):
        self.current_tab = tab
        for key, b in self.tab_buttons.items():
            b.configure(style="Selected.TButton" if key == tab else "TButton")
        self.filter_var.set("")
        self.model_filter_var.set("")
        self.ownership_filter_var.set("Все")
        self._pending_restore = None
        self._build_filter_row()
        self._refresh_current_list()

    def _build_filter_row(self):
        for w in self.filter_row.winfo_children():
            w.destroy()

        with database.get_connection() as conn:
            if self.current_tab == "active":
                types = sorted({r["merchant_type"] for r in database.get_active_terminal_ids(conn) if r["merchant_type"]})
            elif self.current_tab == "epos":
                types = sorted({r["merchant_type"] for r in database.get_epos_terminals(conn) if r["merchant_type"]})
            else:
                types = []
            models = database.get_distinct_models(conn)
            ownerships = database.get_distinct_ownerships(conn)

        if types:
            ttk.Label(self.filter_row, text="Тип:").pack(side="left", padx=(0, 2))
            ordered = [t for t in _PREFERRED_TYPE_ORDER if t in types] + [t for t in types if t not in _PREFERRED_TYPE_ORDER]
            ttk.Radiobutton(self.filter_row, text="Все", variable=self.filter_var, value="",
                            command=self._refresh_current_list).pack(side="left", padx=2)
            for t in ordered:
                ttk.Radiobutton(self.filter_row, text=_type_label(t), variable=self.filter_var, value=t,
                                command=self._refresh_current_list).pack(side="left", padx=2)

        ttk.Label(self.filter_row, text="  Модель:").pack(side="left", padx=(12, 2))
        model_cb = ttk.Combobox(self.filter_row, textvariable=self.model_filter_var,
                                values=[""] + models, state="readonly", width=18)
        model_cb.pack(side="left")
        model_cb.bind("<<ComboboxSelected>>", lambda e: self._refresh_current_list())

        ttk.Label(self.filter_row, text="  Собств.:").pack(side="left", padx=(12, 2))
        own_values = ["Все"] + [OWNERSHIP_DISPLAY.get(o, o) for o in ownerships]
        own_cb = ttk.Combobox(self.filter_row, textvariable=self.ownership_filter_var,
                              values=own_values, state="readonly", width=10)
        own_cb.pack(side="left")
        own_cb.bind("<<ComboboxSelected>>", lambda e: self._refresh_current_list())

    def _read_filters(self):
        model = self.model_filter_var.get().strip() or None
        own_display = self.ownership_filter_var.get()
        own_code = None
        if own_display and own_display != "Все":
            for k, v in OWNERSHIP_DISPLAY.items():
                if v == own_display:
                    own_code = k
                    break
        return model, own_code

    # ------------------------------------------------------------------
    # Обновление списка + сводки
    # ------------------------------------------------------------------
    def _refresh_current_list(self):
        query = self.query_var.get().strip() or None
        model, ownership = self._read_filters()

        if self.current_tab == "active":
            self._configure_active_columns()
            with database.get_connection() as conn:
                rows = database.get_active_terminal_ids(
                    conn, merchant_type=self.filter_var.get() or None,
                    query=query, model=model, ownership=ownership,
                )
                stats = database.get_active_dashboard_stats(conn)
            self._render_active_tree(rows)
            self._set_stats(self._format_active_stats(stats))

        elif self.current_tab == "warehouse":
            self._configure_warehouse_columns()
            with database.get_connection() as conn:
                rows = database.get_warehouse_terminals(conn, query=query, model=model, ownership=ownership)
                stats = database.get_warehouse_dashboard_stats(conn)
            self._render_warehouse_tree(rows)
            self._set_stats([
                f"На складе: {stats['warehouse']}",
                f"В мастерской: {stats['repair_shop']}",
                f"Всего: {stats['total']}",
            ])

        elif self.current_tab == "written_off":
            self._configure_written_off_columns()
            with database.get_connection() as conn:
                rows = database.get_written_off_terminals(conn, query=query, model=model, ownership=ownership)
                stats = database.get_written_off_dashboard_stats(conn)
            self._render_written_off_tree(rows)
            self._set_stats([f"Списано всего: {stats['total']}"])

        else:  # epos
            self._configure_active_columns()
            with database.get_connection() as conn:
                rows = database.get_epos_terminals(conn, query=query, model=model)
                stats = database.get_epos_dashboard_stats(conn)
            self._render_epos_tree(rows)
            self._set_stats([f"E-POS терминалов: {stats['total']}"])

        self._clear_detail()
        self._restore_selection_if_needed()

    def _format_active_stats(self, stats):
        """Сводка: сколько терминалов и сколько ID по каждому типу."""
        lines = [f"Активных: {stats['total_terminals']} терм. / {stats['total']} ID"]
        for t in _PREFERRED_TYPE_ORDER:
            terms = stats.get(f"terms_{t}")
            ids = stats.get(t)
            if terms is None and ids is None:
                continue
            terms = terms or 0
            ids = ids or 0
            lines.append(f"{_type_label(t)}: {terms} терм. / {ids} ID")
        # прочие типы
        other_types = set()
        for k in stats.keys():
            if k in ("total", "total_terminals"):
                continue
            if k.startswith("terms_"):
                other_types.add(k[6:])
            elif k not in _PREFERRED_TYPE_ORDER:
                other_types.add(k)
        for t in sorted(other_types):
            if t in _PREFERRED_TYPE_ORDER:
                continue
            terms = stats.get(f"terms_{t}", 0)
            ids = stats.get(t, 0)
            if terms or ids:
                lines.append(f"{_type_label(t)}: {terms} терм. / {ids} ID")
        return lines

    # ------------------------------------------------------------------
    # Вкладка "Активные" -- дерево: Тип -> Физ.терминал -> ID
    # ------------------------------------------------------------------
    def _configure_active_columns(self):
        cols = ("num", "point", "address", "phone", "own", "owner")
        headings = {
            "num": "№",
            "point": "Наименование организации",
            "address": "Адрес",
            "phone": "Телефон",
            "own": "Собств.",
            "owner": "Ф.И. владельца",
        }
        widths = {"num": 45, "point": 260, "address": 190, "phone": 120, "own": 70, "owner": 200}
        self.tree.configure(columns=cols, show="tree headings")
        self.tree.heading("#0", text="Тип / Терминал / ID")
        self.tree.column("#0", width=340, anchor="w")
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

        term_num = 0  # сквозной счётчик терминалов (как SAN в Excel)

        for t in order:
            group_rows = groups[t]
            terminals = {}
            for r in group_rows:
                terminals.setdefault(r["terminal_id"], []).append(r)

            type_node = self.tree.insert(
                "", "end",
                text=f"— {_type_label(t)} —   {len(terminals)} терм. / {len(group_rows)} ID",
                values=("", "", "", "", "", ""),
                tags=("group",),
                open=False,
            )
            self._row_by_iid[type_node] = ("type_node", t, len(terminals), len(group_rows))

            for term_id, term_rows in terminals.items():
                term_num += 1
                sn = term_rows[0]["serial_number"] or "(без S/N)"
                model = term_rows[0]["model"] or "—"

                # Агрегируем наименование/адрес/телефон терминала (первое непустое)
                point = _first_not_empty(term_rows, "point_label")
                address = _first_not_empty(term_rows, "address")
                phone = _first_not_empty(term_rows, "phone")
                own = OWNERSHIP_SHORT.get(term_rows[0]["ownership"], "")

                term_node = self.tree.insert(
                    type_node, "end",
                    text=f"S/N: {sn}  •  {model}  •  {len(term_rows)} ID",
                    values=(term_num, point, address, phone, own, ""),
                    tags=("terminal",),
                    open=False,
                )
                self._row_by_iid[term_node] = ("terminal_node", term_id)

                for i, r in enumerate(term_rows, start=1):
                    iid = self.tree.insert(
                        term_node, "end",
                        text=f"    {i}. {r['payment_id']}",
                        values=(
                            "",
                            r["point_label"] or "",
                            r["address"] or "",
                            r["phone"] or "",
                            OWNERSHIP_SHORT.get(r["ownership"], ""),
                            r["owner_label"] or "",
                        ),
                        tags=("item",),
                    )
                    self._row_by_iid[iid] = ("active", r["binding_id"])

    # ------------------------------------------------------------------
    # Вкладка "E-POS"
    # ------------------------------------------------------------------
    def _render_epos_tree(self, rows):
        self.tree.delete(*self.tree.get_children())
        self._row_by_iid = {}
        groups = {}
        for r in rows:
            groups.setdefault(r["merchant_type"] or "unknown", []).append(r)
        order = [t for t in _PREFERRED_TYPE_ORDER if t in groups]
        order += sorted(t for t in groups if t not in _PREFERRED_TYPE_ORDER)

        term_num = 0  # сквозной счётчик терминалов

        for t in order:
            group_rows = groups[t]
            terminals = {}
            for r in group_rows:
                terminals.setdefault(r["terminal_id"], []).append(r)

            type_node = self.tree.insert(
                "", "end",
                text=f"— {_type_label(t)} —   {len(terminals)} терм. / {len(group_rows)} ID",
                values=("", "", "", "", "", ""),
                tags=("group",),
                open=False,
            )
            self._row_by_iid[type_node] = ("type_node", t, len(terminals), len(group_rows))

            for term_id, term_rows in terminals.items():
                term_num += 1
                model = term_rows[0]["model"] or "E-POS"
                own = OWNERSHIP_SHORT.get(term_rows[0]["ownership"], "")
                point = _first_not_empty(term_rows, "point_label")
                address = _first_not_empty(term_rows, "address")
                phone = _first_not_empty(term_rows, "phone")

                term_node = self.tree.insert(
                    type_node, "end",
                    text=f"{model}  •  {own}  •  {len(term_rows)} ID",
                    values=(term_num, point, address, phone, own, ""),
                    tags=("terminal",),
                    open=False,
                )
                self._row_by_iid[term_node] = ("terminal_node", term_id)

                for r in term_rows:
                    iid = self.tree.insert(
                        term_node, "end",
                        text=f"    {r['payment_id'] or '(без ID)'}",
                        values=(
                            "",
                            r["point_label"] or "",
                            r["address"] or "",
                            r["phone"] or "",
                            "",
                            r["owner_label"] or "",
                        ),
                        tags=("item",),
                    )
                    self._row_by_iid[iid] = ("epos", r["binding_id"], r["terminal_id"])

    # ------------------------------------------------------------------
    # Вкладка "Склад"
    # ------------------------------------------------------------------
    def _configure_warehouse_columns(self):
        self.tree.configure(show="headings")
        cols = ("num", "sn", "model", "own", "place", "condition", "moved_by", "moved_at", "comment")
        headings = {
            "num": "№", "sn": "S/N", "model": "Модель", "own": "Собств.",
            "place": "Место", "condition": "Состояние",
            "moved_by": "Кем перемещён", "moved_at": "Когда", "comment": "Комментарий",
        }
        widths = {"num": 40, "sn": 110, "model": 110, "own": 70, "place": 90, "condition": 100,
                  "moved_by": 130, "moved_at": 130, "comment": 160}
        self.tree.configure(columns=cols)
        for c in cols:
            self.tree.heading(c, text=headings[c])
            self.tree.column(c, width=widths[c], anchor="w")

    def _render_warehouse_tree(self, rows):
        self.tree.delete(*self.tree.get_children())
        self._row_by_iid = {}
        for i, r in enumerate(rows, start=1):
            place_text = PLACE_LABELS.get(r["current_place"], r["current_place"])
            iid = self.tree.insert(
                "", "end",
                values=(i, r["serial_number"] or "(без S/N)", r["model"] or "",
                        OWNERSHIP_SHORT.get(r["ownership"], ""), place_text,
                        CONDITION_LABELS.get(r["condition"], r["condition"]),
                        r["moved_by_name"] or "", r["last_moved_at"] or "", r["last_comment"] or ""),
                tags=("item",),
            )
            self._row_by_iid[iid] = ("warehouse", r["terminal_id"], r)

    # ------------------------------------------------------------------
    # Вкладка "Списанные"
    # ------------------------------------------------------------------
    def _configure_written_off_columns(self):
        self.tree.configure(show="headings")
        cols = ("num", "sn", "model", "own", "written_off_at", "reason", "comment", "approved_by")
        headings = {
            "num": "№", "sn": "S/N", "model": "Модель", "own": "Собств.",
            "written_off_at": "Дата списания", "reason": "Причина",
            "comment": "Комментарий", "approved_by": "Кто списал",
        }
        widths = {"num": 40, "sn": 110, "model": 110, "own": 70,
                  "written_off_at": 120, "reason": 180, "comment": 160, "approved_by": 130}
        self.tree.configure(columns=cols)
        for c in cols:
            self.tree.heading(c, text=headings[c])
            self.tree.column(c, width=widths[c], anchor="w")

    def _render_written_off_tree(self, rows):
        self.tree.delete(*self.tree.get_children())
        self._row_by_iid = {}
        for i, r in enumerate(rows, start=1):
            iid = self.tree.insert(
                "", "end",
                values=(i, r["serial_number"] or "(без S/N)", r["model"] or "",
                        OWNERSHIP_SHORT.get(r["ownership"], ""),
                        r["written_off_at"] or "", r["reason"] or "",
                        r["comment"] or "", r["approved_by_name"] or ""),
                tags=("item",),
            )
            self._row_by_iid[iid] = ("written_off", r["terminal_id"], r)

    # ------------------------------------------------------------------
    # Обработка выбора
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
        kind = info[0]
        if kind in ("active", "epos"):
            self._show_id_detail(info[1])
        elif kind == "terminal_node":
            self._show_terminal_node_detail(info[1])
        elif kind == "type_node":
            self._clear_detail()
        elif kind == "warehouse":
            self._show_warehouse_detail(info[1], info[2])
        elif kind == "written_off":
            self._show_written_off_detail(info[1], info[2])

    def _on_double_click(self):
        selection = self.tree.selection()
        if not selection:
            return
        info = self._row_by_iid.get(selection[0])
        if info is None:
            return
        kind = info[0]
        if kind == "active":
            with database.get_connection() as conn:
                d = database.get_terminal_id_detail(conn, info[1])
            if d:
                self._open_terminal_card(d["terminal_id"])
        elif kind == "epos":
            self._open_terminal_card(info[2])
        elif kind == "terminal_node":
            self._open_terminal_card(info[1])
        elif kind in ("warehouse", "written_off"):
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
            ttk.Label(self.detail_body, text=value or "-", wraplength=280, justify="left").grid(
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
            ("Собственность", OWNERSHIP_SHORT.get(d["ownership"], d["ownership"])),
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
            actions.insert(0, ("Закрыть ID", lambda: self._close_active(binding_id)))
        self._show_detail(fields, actions)

    def _show_terminal_node_detail(self, terminal_id):
        with database.get_connection() as conn:
            d = database.get_terminal_full(conn, terminal_id)
        if d is None:
            self._clear_detail()
            return
        t = d["terminal"]
        active_ids = [b for b in d["bindings"] if b["bound_to"] is None]
        fields = [
            ("S/N", t["serial_number"] or "(без S/N)"),
            ("Модель", t["model"]),
            ("Собственность", OWNERSHIP_SHORT.get(t["ownership"], t["ownership"])),
            ("Место", PLACE_LABELS.get(d["current_place"], d["current_place"])),
            ("Состояние", CONDITION_LABELS.get(d["condition"], d["condition"])),
            ("Активных ID", str(len(active_ids))),
        ]
        actions = [("Карточка терминала", lambda: self._open_terminal_card(terminal_id))]
        self._show_detail(fields, actions)

    def _show_warehouse_detail(self, terminal_id, row):
        place_text = PLACE_LABELS.get(row["current_place"], row["current_place"])
        fields = [
            ("S/N", row["serial_number"] or "(без S/N)"),
            ("Модель", row["model"]),
            ("Собственность", OWNERSHIP_SHORT.get(row["ownership"], row["ownership"])),
            ("Место", place_text),
            ("Состояние", CONDITION_LABELS.get(row["condition"], row["condition"])),
            ("Кем перемещён", row["moved_by_name"]),
            ("Когда", row["last_moved_at"]),
            ("Комментарий", row["last_comment"]),
        ]
        actions = [("Карточка терминала", lambda: self._open_terminal_card(terminal_id))]
        self._show_detail(fields, actions)

    def _show_written_off_detail(self, terminal_id, row):
        fields = [
            ("S/N", row["serial_number"] or "(без S/N)"),
            ("Модель", row["model"]),
            ("Собственность", OWNERSHIP_SHORT.get(row["ownership"], row["ownership"])),
            ("Дата списания", row["written_off_at"]),
            ("Причина", row["reason"]),
            ("Комментарий", row["comment"]),
            ("Кто списал", row["approved_by_name"]),
        ]
        actions = [("Карточка терминала", lambda: self._open_terminal_card(terminal_id))]
        self._show_detail(fields, actions)

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

    # ------------------------------------------------------------------
    def _open_terminal_card(self, terminal_id):
        self._remember_selection()
        TerminalCard(self, self.user, terminal_id, on_close=self._after_card_closed)

    def _open_merchant_card(self, merchant_id):
        self._remember_selection()
        MerchantCard(self, self.user, merchant_id, on_close=self._after_card_closed)

    def _remember_selection(self):
        self._pending_restore = None
        sel = self.tree.selection()
        if sel:
            info = self._row_by_iid.get(sel[0])
            if info:
                self._pending_restore = info[:2]

    def _after_card_closed(self):
        self._refresh_current_list()

    def _restore_selection_if_needed(self):
        if self._pending_restore is None:
            return
        target = None
        for iid, info in self._row_by_iid.items():
            if info[:2] == self._pending_restore:
                target = iid
                break
        if target:
            parent = self.tree.parent(target)
            while parent:
                self.tree.item(parent, open=True)
                parent = self.tree.parent(parent)
            self.tree.selection_set(target)
            self.tree.see(target)
        self._pending_restore = None