# -*- coding: utf-8 -*-
"""Главное окно: вкладки под сводкой, дерево с группировкой
Тип клиента -> Физ.терминал -> ID."""

import tkinter as tk
from tkinter import ttk, messagebox, simpledialog

import config
import database
from gui import utils
from gui import column_settings
from gui import export_excel
from gui.terminal_card import TerminalCard
from gui.merchant_card import MerchantCard
from gui.users_window import UsersWindow
from gui.merchants_list_window import MerchantsListWindow
from gui.terminals_list_window import TerminalsListWindow
from gui.new_id_dialog import NewIdDialog
from gui.edit_id_dialog import EditIdDialog

TYPE_LABELS = {"bank": "BANK", "edara": "EDARA", "telekeci": "TELEKEÇI", "hk": "H/K"}
PLACE_LABELS = {"merchant": "У клиента", "warehouse": "Склад", "repair_shop": "Мастерская"}
CONDITION_LABELS = {
    "normal": "Норма",
    "in_repair": "В ремонте",
    "written_off": "Списан",
}
OWNERSHIP_SHORT = {"bank": "Банк", "client": "Клиент"}
OWNERSHIP_DISPLAY = {"bank": "Банк", "client": "Клиент"}
_PREFERRED_TYPE_ORDER = ("bank", "edara", "telekeci", "hk")


def _column_spec():
    return {
        "active": (
            ("point", "address", "phone", "own", "owner"),
            {"point": "Наименование организации", "address": "Адрес",
             "phone": "Телефон", "own": "Собств.", "owner": "Ф.И. владельца"},
            {"point": 260, "address": 190, "phone": 120, "own": 70, "owner": 200},
        ),
        "epos": (
            ("point", "address", "phone", "own", "owner"),
            {"point": "Наименование организации", "address": "Адрес",
             "phone": "Телефон", "own": "Собств.", "owner": "Ф.И. владельца"},
            {"point": 260, "address": 190, "phone": 120, "own": 70, "owner": 200},
        ),
        "warehouse": (
            ("num", "sn", "model", "own", "place", "condition", "moved_by", "moved_at", "comment"),
            {"num": "№", "sn": "S/N", "model": "Модель", "own": "Собств.",
             "place": "Место", "condition": "Состояние",
             "moved_by": "Кем перемещён", "moved_at": "Когда", "comment": "Комментарий"},
            {"num": 40, "sn": 110, "model": 110, "own": 70, "place": 90,
             "condition": 100, "moved_by": 130, "moved_at": 130, "comment": 160},
        ),
        "written_off": (
            ("num", "sn", "model", "own", "written_off_at", "reason", "comment", "approved_by"),
            {"num": "№", "sn": "S/N", "model": "Модель", "own": "Собств.",
             "written_off_at": "Дата списания", "reason": "Причина",
             "comment": "Комментарий", "approved_by": "Кто списал"},
            {"num": 40, "sn": 110, "model": 110, "own": 70,
             "written_off_at": 120, "reason": 180, "comment": 160, "approved_by": 130},
        ),
    }


def _type_label(code):
    return TYPE_LABELS.get(code, (code or "?").upper())


def _first_not_empty(rows, key):
    for r in rows:
        v = r.get(key)
        if v:
            return v
    return ""


def _date_sort_key(value):
    return value or ""


class MoveTerminalsDialog(tk.Toplevel):
    def __init__(self, master, count):
        super().__init__(master)
        self.title("Переместить терминалы")
        self.resizable(False, False)
        self.result = None

        ttk.Label(self, text=f"Выделено терминалов: {count}",
                  font=("TkDefaultFont", 10, "bold")).pack(padx=20, pady=(15, 10))

        btns = ttk.Frame(self, padding=10)
        btns.pack()
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
        self._current_cols = None
        self._current_tab_key = None

        self.title(f"Terminal Manager v{config.APP_VERSION} -- {user['full_name']} ({user['role']})")

        # Разворачиваем на весь экран (не блокирует кнопку свернуть/закрыть)
        self.geometry("1360x780")  # fallback
        try:
            self.state("zoomed")
        except Exception:
            try:
                self.attributes("-zoomed", True)
            except Exception:
                pass

        self._style = ttk.Style(self)
        self._style.configure("Selected.TButton", font=("TkDefaultFont", 9, "bold"))

        # Контекстное меню (правый клик по строке дерева)
        self.context_menu = tk.Menu(self, tearoff=0)

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

        # --- Файл ---
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Экспорт текущей вкладки в Excel...",
                              command=self._export_current_tab)
        file_menu.add_separator()
        file_menu.add_command(label="Выход", command=self.destroy)
        menubar.add_cascade(label="Файл", menu=file_menu)

        # --- Операции ---
        ops_menu = tk.Menu(menubar, tearoff=0)
        ops_menu.add_command(label="Выдать новый ID...", command=self._open_new_id_dialog)
        ops_menu.add_separator()
        ops_menu.add_command(label="Открыть карточку терминала",
                             command=self._open_selected_terminal_card)
        ops_menu.add_command(label="Открыть карточку мерчанта",
                             command=self._open_selected_merchant_card)
        ops_menu.add_command(label="Редактировать выбранный ID...",
                             command=self._edit_selected_id)
        ops_menu.add_separator()
        ops_menu.add_command(label="Закрыть выбранные ID...",
                             command=self._close_selected_ids)
        ops_menu.add_command(label="Переместить выбранные терминалы...",
                             command=self._move_selected_terminals)
        menubar.add_cascade(label="Операции", menu=ops_menu)

        # --- Справочники ---
        refs_menu = tk.Menu(menubar, tearoff=0)
        refs_menu.add_command(label="Мерчанты...", command=self._open_merchants_list)
        refs_menu.add_command(label="Терминалы...", command=self._open_terminals_list)
        refs_menu.add_separator()
        refs_menu.add_command(label="Настройки колонок...", command=self._open_column_settings)
        menubar.add_cascade(label="Справочники", menu=refs_menu)

        # --- Отчёты ---
        reports_menu = tk.Menu(menubar, tearoff=0)
        reports_menu.add_command(label="По моделям терминалов...", command=self._open_models_report)
        reports_menu.add_command(label="Отчёт по клиенту...", command=self._open_selected_merchant_report)
        menubar.add_cascade(label="Отчёты", menu=reports_menu)

        # --- Администрирование ---
        if self.user["role"] == "admin":
            admin_menu = tk.Menu(menubar, tearoff=0)
            admin_menu.add_command(label="Пользователи...", command=self._open_users_window)
            menubar.add_cascade(label="Администрирование", menu=admin_menu)

        # --- Справка ---
        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="Открыть папку с логами", command=self._open_logs_folder)
        help_menu.add_separator()
        help_menu.add_command(label="О программе", command=self._show_about)
        menubar.add_cascade(label="Справка", menu=help_menu)

        self.config(menu=menubar)

    def _open_users_window(self):
        UsersWindow(self, self.user)

    def _open_merchants_list(self):
        MerchantsListWindow(self, self.user)

    def _open_terminals_list(self):
        TerminalsListWindow(self, self.user)

    def _open_new_id_dialog(self):
        dlg = NewIdDialog(self, self.user)
        if dlg.result:
            self._refresh_current_list()

    def _open_models_report(self):
        from gui.models_report import ModelsReportWindow
        ModelsReportWindow(self, self.user)

    def _open_merchant_report(self, merchant_id):
        from gui.merchant_report import MerchantReportWindow
        MerchantReportWindow(self, self.user, merchant_id)

    def _open_logs_folder(self):
        import os
        import subprocess
        try:
            import logger
            path = logger.get_log_dir()
        except Exception:
            path = None
        if not path or not os.path.exists(path):
            messagebox.showinfo("Инфо", "Папка с логами ещё не создана.", parent=self)
            return
        try:
            subprocess.Popen(["explorer", os.path.normpath(path)])
        except Exception as exc:
            messagebox.showerror("Ошибка", f"Не удалось открыть папку:\n{exc}", parent=self)

    # ------------------------------------------------------------------
    # Действия по выделенной строке (меню верхнее + контекстное)
    # ------------------------------------------------------------------
    def _get_single_selection_info(self):
        """Если выделена ровно одна строка -- возвращает её info. Иначе None."""
        sel = self.tree.selection()
        if len(sel) != 1:
            return None
        return self._row_by_iid.get(sel[0])

    def _resolve_terminal_id_from_selection(self):
        """Возвращает terminal_id по выделенной строке (или None)."""
        info = self._get_single_selection_info()
        if info is None:
            return None
        kind = info[0]
        if kind == "terminal_node":
            return info[1]
        if kind in ("warehouse", "written_off"):
            return info[1]
        if kind == "active":
            with database.get_connection() as conn:
                d = database.get_terminal_id_detail(conn, info[1])
            if d:
                return d.get("terminal_id")
        return None

    def _resolve_merchant_id_from_selection(self):
        """Возвращает merchant_id по выделенной строке (или None)."""
        info = self._get_single_selection_info()
        if info is None:
            return None
        kind = info[0]
        if kind == "active":
            with database.get_connection() as conn:
                d = database.get_terminal_id_detail(conn, info[1])
            if d:
                return d.get("merchant_id")
        if kind in ("terminal_node", "warehouse", "written_off"):
            tid = info[1]
            with database.get_connection() as conn:
                row = conn.execute("""
                    SELECT current_merchant_id FROM terminal_current_state WHERE terminal_id = ?
                """, (tid,)).fetchone()
            if row and row["current_merchant_id"]:
                return row["current_merchant_id"]
            with database.get_connection() as conn:
                row = conn.execute("""
                    SELECT ti.merchant_id
                    FROM terminal_id_bindings b
                    JOIN terminal_ids ti ON ti.id = b.terminal_id_ref
                    WHERE b.terminal_id = ? AND b.bound_to IS NULL
                    LIMIT 1
                """, (tid,)).fetchone()
            if row:
                return row["merchant_id"]
        return None

    def _resolve_terminal_id_ref_from_selection(self):
        """Возвращает terminal_ids.id (не binding, а саму запись) по выделению."""
        info = self._get_single_selection_info()
        if info is None:
            return None
        if info[0] == "active":
            return info[2] if len(info) > 2 else None
        if info[0] == "epos" and len(info) > 3:
            return info[3]
        return None

    def _open_selected_terminal_card(self):
        tid = self._resolve_terminal_id_from_selection()
        if tid is None:
            messagebox.showinfo("Инфо",
                "Выделите строку терминала или ID, чтобы открыть карточку.",
                parent=self)
            return
        self._open_terminal_card(tid)

    def _open_selected_merchant_card(self):
        mid = self._resolve_merchant_id_from_selection()
        if mid is None:
            messagebox.showinfo("Инфо",
                "Выделите строку с ID или терминалом, связанным с клиентом.",
                parent=self)
            return
        self._open_merchant_card(mid)

    def _edit_selected_id(self):
        tid_ref = self._resolve_terminal_id_ref_from_selection()
        if tid_ref is None:
            messagebox.showinfo("Инфо",
                "Выделите строку с платёжным ID, чтобы его редактировать.",
                parent=self)
            return
        self._edit_id(tid_ref)

    def _open_selected_merchant_report(self):
        mid = self._resolve_merchant_id_from_selection()
        if mid is None:
            messagebox.showinfo("Инфо",
                "Выделите строку с ID или терминалом клиента, чтобы открыть отчёт.",
                parent=self)
            return
        self._open_merchant_report(mid)

    def _export_current_tab(self):
        from tkinter import filedialog
        tab_key = self.current_tab
        default_name = {
            "active": "Активные",
            "warehouse": "Склад",
            "written_off": "Списанные",
            "epos": "E-POS",
        }.get(tab_key, "Экспорт") + ".xlsx"

        path = filedialog.asksaveasfilename(
            parent=self,
            title="Экспорт в Excel",
            defaultextension=".xlsx",
            filetypes=[("Excel файлы", "*.xlsx")],
            initialfile=default_name,
        )
        if not path:
            return
        try:
            export_excel.export_tree_to_xlsx(self.tree, tab_key, path)
        except Exception as exc:
            messagebox.showerror("Ошибка экспорта", str(exc), parent=self)
            return
        messagebox.showinfo("Готово", f"Файл сохранён:\n{path}", parent=self)

    # ------------------------------------------------------------------
    # Массовые операции
    # ------------------------------------------------------------------
    def _close_selected_ids(self):
        selection = self.tree.selection()
        if not selection:
            messagebox.showinfo("Инфо", "Ничего не выделено", parent=self)
            return
        binding_ids = []
        for iid in selection:
            info = self._row_by_iid.get(iid)
            if info and info[0] == "active":
                binding_ids.append(info[1])
        if not binding_ids:
            messagebox.showinfo(
                "Инфо",
                "Среди выделенных строк нет ни одного активного ID.\n"
                "Выделите строки с ID (Ctrl+Click, Shift+Click или Ctrl+A).",
                parent=self,
            )
            return
        if not messagebox.askyesno(
            "Подтверждение",
            f"Закрыть {len(binding_ids)} ID у клиента(ов)?\n\n"
            "ID будут отвязаны от терминалов. Если у какого-то терминала\n"
            "не останется активных ID -- он автоматически уедет на склад.",
            parent=self,
        ):
            return
        comment = simpledialog.askstring(
            "Комментарий", "Комментарий (необязательно):", parent=self
        ) or None

        closed, moved, skipped = 0, 0, 0
        with database.get_connection() as conn:
            for bid in binding_ids:
                try:
                    if database.close_terminal_id(conn, bid, self.user["id"], comment=comment):
                        moved += 1
                    closed += 1
                except ValueError:
                    skipped += 1

        msg = f"Закрыто ID: {closed}"
        if moved:
            msg += f"\nТерминалов перемещено на склад: {moved}"
        if skipped:
            msg += f"\nПропущено (уже закрыты): {skipped}"
        messagebox.showinfo("Готово", msg, parent=self)
        self._refresh_current_list()

    def _move_selected_terminals(self):
        selection = self.tree.selection()
        if not selection:
            messagebox.showinfo("Инфо", "Ничего не выделено", parent=self)
            return

        terminal_ids = set()
        for iid in selection:
            info = self._row_by_iid.get(iid)
            if not info:
                continue
            kind = info[0]
            if kind in ("terminal_node", "warehouse", "written_off"):
                terminal_ids.add(info[1])
            elif kind == "active":
                with database.get_connection() as conn:
                    d = database.get_terminal_id_detail(conn, info[1])
                if d and d.get("terminal_id"):
                    terminal_ids.add(d["terminal_id"])

        if not terminal_ids:
            messagebox.showinfo(
                "Инфо",
                "Не удалось определить терминалы для перемещения.\n"
                "Выделите строки терминалов или ID.",
                parent=self,
            )
            return

        dlg = MoveTerminalsDialog(self, len(terminal_ids))
        place = dlg.result
        if place is None:
            return

        comment = simpledialog.askstring(
            "Комментарий", "Комментарий (необязательно):", parent=self
        ) or None

        with database.get_connection() as conn:
            for tid in terminal_ids:
                database.move_terminal(conn, tid, place, self.user["id"], comment=comment)

        messagebox.showinfo("Готово",
            f"Перемещено терминалов: {len(terminal_ids)}", parent=self)
        self._refresh_current_list()

    def _show_about(self):
        with database.get_connection() as conn:
            history = database.get_version_history(conn, limit=10)
        lines = [f"Terminal Manager, версия {config.APP_VERSION}", "", "История версий:"]
        for h in history:
            lines.append(f"  {h['version']} -- {h['installed_at']}" + (f" ({h['notes']})" if h["notes"] else ""))
        messagebox.showinfo("О программе", "\n".join(lines), parent=self)

    def _build_stats(self):
        self.stats_frame = ttk.LabelFrame(self, text="Сводка", padding=8)
        self.stats_frame.pack(fill="x", padx=10, pady=(10, 4))

    def _set_stats(self, lines):
        for w in self.stats_frame.winfo_children():
            w.destroy()
        for i, text in enumerate(lines):
            ttk.Label(self.stats_frame, text=text).grid(row=i // 5, column=i % 5, sticky="w", padx=10, pady=2)

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
        ttk.Button(search_row, text="+ Выдать ID...", command=self._open_new_id_dialog).pack(
            side="left", padx=(20, 4))

        self.filter_row = ttk.Frame(content)
        self.filter_row.pack(fill="x", pady=(0, 4))

        paned = ttk.PanedWindow(content, orient="horizontal")
        paned.pack(fill="both", expand=True)

        tree_frame = ttk.Frame(paned)
        paned.add(tree_frame, weight=3)
        self.detail_frame = ttk.LabelFrame(paned, text="Подробности", padding=10)
        paned.add(self.detail_frame, weight=2)

        self.tree = ttk.Treeview(tree_frame, show="headings", height=24,
                                  selectmode="extended")
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", lambda e: self._on_select())
        self.tree.bind("<Double-1>", lambda e: self._on_double_click())
        self.tree.bind("<Button-3>", self._on_right_click)
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

    def _apply_column_spec(self, tab_key):
        all_cols, headings, default_widths = _column_spec()[tab_key]
        settings = column_settings.load_settings()
        tab_settings = settings.get(tab_key, {})
        visible = tab_settings.get("visible") or list(all_cols)
        visible = [c for c in visible if c in all_cols] or list(all_cols)
        widths = tab_settings.get("widths", {})

        try:
            self.tree.configure(displaycolumns="#all")
        except Exception:
            pass
        self.tree.configure(columns=all_cols, show="tree headings")
        self.tree.heading("#0", text="№ / S/N / ID")
        w0 = widths.get("#0", 340)
        self.tree.column("#0", width=w0, anchor="w")
        for c in all_cols:
            self.tree.heading(c, text=headings[c])
            w = widths.get(c, default_widths[c])
            self.tree.column(c, width=w, anchor="w")
        try:
            self.tree.configure(displaycolumns=visible)
        except Exception:
            self.tree.configure(displaycolumns="#all")

        self._current_cols = all_cols
        self._current_tab_key = tab_key

    def _save_current_widths(self):
        if not self._current_cols or not self._current_tab_key:
            return
        settings = column_settings.load_settings()
        tab_settings = settings.setdefault(self._current_tab_key, {})
        widths = tab_settings.setdefault("widths", {})
        try:
            widths["#0"] = int(self.tree.column("#0", "width"))
        except Exception:
            pass
        for c in self._current_cols:
            try:
                widths[c] = int(self.tree.column(c, "width"))
            except Exception:
                pass
        column_settings.save_settings(settings)

    def _open_column_settings(self):
        tab_key = self.current_tab
        if tab_key not in _column_spec():
            messagebox.showinfo("Инфо", "Для этой вкладки настройка колонок недоступна", parent=self)
            return
        all_cols, headings, _ = _column_spec()[tab_key]
        settings = column_settings.load_settings()
        visible = settings.get(tab_key, {}).get("visible") or list(all_cols)
        visible = [c for c in visible if c in all_cols] or list(all_cols)

        def on_apply(new_visible):
            s = column_settings.load_settings()
            s.setdefault(tab_key, {})["visible"] = new_visible
            column_settings.save_settings(s)
            self._apply_column_spec(tab_key)

        ColumnSettingsDialog = column_settings.ColumnSettingsDialog
        ColumnSettingsDialog(self, all_cols, headings, visible, on_apply)

    def destroy(self):
        try:
            self._save_current_widths()
        except Exception:
            pass
        super().destroy()

    def _select_tab(self, tab):
        try:
            self._save_current_widths()
        except Exception:
            pass
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

    def _refresh_current_list(self):
        query = self.query_var.get().strip() or None
        model, ownership = self._read_filters()

        if self.current_tab == "active":
            self._apply_column_spec("active")
            with database.get_connection() as conn:
                rows = database.get_active_terminal_ids(
                    conn, merchant_type=self.filter_var.get() or None,
                    query=query, model=model, ownership=ownership,
                )
                stats = database.get_active_dashboard_stats(conn)
            self._render_active_tree(rows)
            self._set_stats(self._format_active_stats(stats))
        elif self.current_tab == "warehouse":
            self._apply_column_spec("warehouse")
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
            self._apply_column_spec("written_off")
            with database.get_connection() as conn:
                rows = database.get_written_off_terminals(conn, query=query, model=model, ownership=ownership)
                stats = database.get_written_off_dashboard_stats(conn)
            self._render_written_off_tree(rows)
            self._set_stats([f"Списано всего: {stats['total']}"])
        else:
            self._apply_column_spec("epos")
            with database.get_connection() as conn:
                rows = database.get_epos_terminals(conn, query=query, model=model)
                stats = database.get_epos_dashboard_stats(conn)
            self._render_epos_tree(rows)
            self._set_stats([f"E-POS терминалов: {stats['total']}"])

        self._clear_detail()
        self._restore_selection_if_needed()

    def _format_active_stats(self, stats):
        lines = [f"Активных: {stats['total_terminals']} терм. / {stats['total']} ID"]
        for t in _PREFERRED_TYPE_ORDER:
            terms = stats.get(f"terms_{t}")
            ids = stats.get(t)
            if terms is None and ids is None:
                continue
            terms = terms or 0
            ids = ids or 0
            lines.append(f"{_type_label(t)}: {terms} терм. / {ids} ID")
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

    def _render_active_tree(self, rows):
        self.tree.delete(*self.tree.get_children())
        self._row_by_iid = {}
        groups = {}
        for r in rows:
            groups.setdefault(r["merchant_type"] or "unknown", []).append(r)
        order = [t for t in _PREFERRED_TYPE_ORDER if t in groups]
        order += sorted(t for t in groups if t not in _PREFERRED_TYPE_ORDER)
        term_num = 0
        for t in order:
            group_rows = groups[t]
            terminals = {}
            for r in group_rows:
                terminals.setdefault(r["terminal_id"], []).append(r)

            def term_sort_key(item):
                _, t_rows = item
                dates = [_date_sort_key(r.get("issue_date")) for r in t_rows]
                return min(dates) if dates else ""

            terminals_sorted = sorted(terminals.items(), key=term_sort_key)
            type_node = self.tree.insert(
                "", "end",
                text=f"— {_type_label(t)} —   {len(terminals)} терм. / {len(group_rows)} ID",
                values=tuple([""] * len(self._current_cols)),
                tags=("group",),
                open=False,
            )
            self._row_by_iid[type_node] = ("type_node", t, len(terminals), len(group_rows))
            for term_id, term_rows in terminals_sorted:
                term_rows.sort(key=lambda r: _date_sort_key(r.get("issue_date")))
                term_num += 1
                sn = term_rows[0]["serial_number"] or "(без S/N)"
                model = term_rows[0]["model"] or "—"
                point = _first_not_empty(term_rows, "point_label")
                address = _first_not_empty(term_rows, "address")
                phone = _first_not_empty(term_rows, "phone")
                own = OWNERSHIP_SHORT.get(term_rows[0]["ownership"], "")
                values_map = {"point": point, "address": address, "phone": phone,
                              "own": own, "owner": ""}
                values = tuple(values_map.get(c, "") for c in self._current_cols)
                term_node = self.tree.insert(
                    type_node, "end",
                    text=f"{term_num}. S/N: {sn}  •  {model}  •  {len(term_rows)} ID",
                    values=values, tags=("terminal",), open=False,
                )
                self._row_by_iid[term_node] = ("terminal_node", term_id)
                for i, r in enumerate(term_rows, start=1):
                    vmap = {"point": r["point_label"] or "", "address": r["address"] or "",
                            "phone": r["phone"] or "",
                            "own": OWNERSHIP_SHORT.get(r["ownership"], ""),
                            "owner": r["owner_label"] or ""}
                    v = tuple(vmap.get(c, "") for c in self._current_cols)
                    iid = self.tree.insert(
                        term_node, "end",
                        text=f"    {i}. {r['payment_id']}",
                        values=v, tags=("item",),
                    )
                    self._row_by_iid[iid] = ("active", r["binding_id"], r["terminal_id_ref"])

    def _render_epos_tree(self, rows):
        self.tree.delete(*self.tree.get_children())
        self._row_by_iid = {}
        groups = {}
        for r in rows:
            groups.setdefault(r["merchant_type"] or "unknown", []).append(r)
        order = [t for t in _PREFERRED_TYPE_ORDER if t in groups]
        order += sorted(t for t in groups if t not in _PREFERRED_TYPE_ORDER)
        term_num = 0
        for t in order:
            group_rows = groups[t]
            terminals = {}
            for r in group_rows:
                terminals.setdefault(r["terminal_id"], []).append(r)
            type_node = self.tree.insert(
                "", "end",
                text=f"— {_type_label(t)} —   {len(terminals)} терм. / {len(group_rows)} ID",
                values=tuple([""] * len(self._current_cols)),
                tags=("group",), open=False,
            )
            self._row_by_iid[type_node] = ("type_node", t, len(terminals), len(group_rows))
            for term_id, term_rows in terminals.items():
                term_num += 1
                model = term_rows[0]["model"] or "E-POS"
                own = OWNERSHIP_SHORT.get(term_rows[0]["ownership"], "")
                point = _first_not_empty(term_rows, "point_label")
                address = _first_not_empty(term_rows, "address")
                phone = _first_not_empty(term_rows, "phone")
                values_map = {"point": point, "address": address, "phone": phone,
                              "own": own, "owner": ""}
                values = tuple(values_map.get(c, "") for c in self._current_cols)
                term_node = self.tree.insert(
                    type_node, "end",
                    text=f"{term_num}. {model}  •  {own}  •  {len(term_rows)} ID",
                    values=values, tags=("terminal",), open=False,
                )
                self._row_by_iid[term_node] = ("terminal_node", term_id)
                for r in term_rows:
                    vmap = {"point": r["point_label"] or "", "address": r["address"] or "",
                            "phone": r["phone"] or "", "own": "",
                            "owner": r["owner_label"] or ""}
                    v = tuple(vmap.get(c, "") for c in self._current_cols)
                    iid = self.tree.insert(
                        term_node, "end",
                        text=f"    {r['payment_id'] or '(без ID)'}",
                        values=v, tags=("item",),
                    )
                    self._row_by_iid[iid] = ("epos", r["binding_id"], r["terminal_id"], r["terminal_id"])

    def _render_warehouse_tree(self, rows):
        self.tree.delete(*self.tree.get_children())
        self._row_by_iid = {}
        for i, r in enumerate(rows, start=1):
            place_text = PLACE_LABELS.get(r["current_place"], r["current_place"])
            vmap = {"num": i, "sn": r["serial_number"] or "(без S/N)", "model": r["model"] or "",
                    "own": OWNERSHIP_SHORT.get(r["ownership"], ""), "place": place_text,
                    "condition": CONDITION_LABELS.get(r["condition"], r["condition"]),
                    "moved_by": r["moved_by_name"] or "", "moved_at": r["last_moved_at"] or "",
                    "comment": r["last_comment"] or ""}
            v = tuple(vmap.get(c, "") for c in self._current_cols)
            iid = self.tree.insert("", "end", text="", values=v, tags=("item",))
            self._row_by_iid[iid] = ("warehouse", r["terminal_id"], r)

    def _render_written_off_tree(self, rows):
        self.tree.delete(*self.tree.get_children())
        self._row_by_iid = {}
        for i, r in enumerate(rows, start=1):
            vmap = {"num": i, "sn": r["serial_number"] or "(без S/N)", "model": r["model"] or "",
                    "own": OWNERSHIP_SHORT.get(r["ownership"], ""),
                    "written_off_at": r["written_off_at"] or "",
                    "reason": r["reason"] or "", "comment": r["comment"] or "",
                    "approved_by": r["approved_by_name"] or ""}
            v = tuple(vmap.get(c, "") for c in self._current_cols)
            iid = self.tree.insert("", "end", text="", values=v, tags=("item",))
            self._row_by_iid[iid] = ("written_off", r["terminal_id"], r)

    # ------------------------------------------------------------------
    # Контекстное меню (правый клик по строке)
    # ------------------------------------------------------------------
    def _on_right_click(self, event):
        iid = self.tree.identify_row(event.y)
        if not iid:
            return
        if iid not in self.tree.selection():
            self.tree.selection_set(iid)
        self._populate_context_menu()
        try:
            self.context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.context_menu.grab_release()

    def _populate_context_menu(self):
        self.context_menu.delete(0, "end")
        info = self._get_single_selection_info()

        if info is None:
            self.context_menu.add_command(label="Закрыть выбранные ID...",
                                          command=self._close_selected_ids)
            self.context_menu.add_command(label="Переместить выбранные терминалы...",
                                          command=self._move_selected_terminals)
            return

        kind = info[0]
        if kind == "active":
            self.context_menu.add_command(label="Редактировать ID...",
                                          command=self._edit_selected_id)
            self.context_menu.add_command(label="Закрыть ID",
                                          command=lambda: self._close_active(info[1]))
            self.context_menu.add_separator()
            self.context_menu.add_command(label="Карточка терминала",
                                          command=self._open_selected_terminal_card)
            self.context_menu.add_command(label="Карточка мерчанта",
                                          command=self._open_selected_merchant_card)
            self.context_menu.add_separator()
            self.context_menu.add_command(label="Отчёт по клиенту...",
                                          command=self._open_selected_merchant_report)
        elif kind == "terminal_node":
            self.context_menu.add_command(label="Карточка терминала",
                                          command=self._open_selected_terminal_card)
            self.context_menu.add_command(label="Карточка мерчанта",
                                          command=self._open_selected_merchant_card)
            self.context_menu.add_separator()
            self.context_menu.add_command(label="Отчёт по клиенту...",
                                          command=self._open_selected_merchant_report)
        elif kind in ("warehouse", "written_off"):
            self.context_menu.add_command(label="Карточка терминала",
                                          command=self._open_selected_terminal_card)
            self.context_menu.add_separator()
            self.context_menu.add_command(label="Переместить терминал...",
                                          command=self._move_selected_terminals)
        elif kind == "type_node":
            self.context_menu.add_command(label="Закрыть выбранные ID...",
                                          command=self._close_selected_ids)
        elif kind == "epos":
            self.context_menu.add_command(label="Карточка терминала",
                                          command=self._open_selected_terminal_card)
            if info[1]:
                self.context_menu.add_command(label="Редактировать ID...",
                                              command=self._edit_selected_id)

    # ------------------------------------------------------------------
    # Обработка выбора
    # ------------------------------------------------------------------
    def _on_select(self):
        selection = self.tree.selection()
        if not selection:
            self._clear_detail()
            return
        if len(selection) > 1:
            self._show_multi_selection_summary(selection)
            return
        info = self._row_by_iid.get(selection[0])
        if info is None:
            self._clear_detail()
            return
        kind = info[0]
        if kind in ("active", "epos"):
            self._show_id_detail(info[1], info[2] if len(info) > 2 else None)
        elif kind == "terminal_node":
            self._show_terminal_node_detail(info[1])
        elif kind == "type_node":
            self._clear_detail()
        elif kind == "warehouse":
            self._show_warehouse_detail(info[1], info[2])
        elif kind == "written_off":
            self._show_written_off_detail(info[1], info[2])

    def _show_multi_selection_summary(self, selection):
        n_active = 0
        n_terminals = set()
        for iid in selection:
            info = self._row_by_iid.get(iid)
            if not info:
                continue
            if info[0] == "active":
                n_active += 1
            elif info[0] in ("terminal_node", "warehouse", "written_off"):
                n_terminals.add(info[1])
        fields = [
            ("Выделено строк", str(len(selection))),
            ("Активных ID", str(n_active)),
            ("Уникальных терминалов", str(len(n_terminals))),
            ("", ""),
            ("Действия", "Правый клик по строке или меню «Операции»"),
        ]
        self._show_detail(fields, [])

    def _on_double_click(self):
        selection = self.tree.selection()
        if not selection:
            return
        info = self._row_by_iid.get(selection[0])
        if info is None:
            return
        kind = info[0]
        if kind == "active":
            if len(info) > 2 and info[2]:
                self._edit_id(info[2])
                return
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
                row=i, column=0, sticky="ne", padx=4, pady=3)
            ttk.Label(self.detail_body, text=value or "-", wraplength=280, justify="left").grid(
                row=i, column=1, sticky="nw", padx=4, pady=3)
        for w in self.detail_actions.winfo_children():
            w.destroy()
        for label, cmd in actions:
            ttk.Button(self.detail_actions, text=label, command=cmd).pack(side="left", padx=2)

    def _show_id_detail(self, binding_id, terminal_id_ref=None):
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
            ("Дата установки", d.get("install_date")),
            ("Дата выдачи", d.get("issue_date")),
            ("", ""),
            ("Действия", "Правый клик по строке или меню «Операции» / «Отчёты»"),
        ]
        self._show_detail(fields, [])

    def _edit_id(self, terminal_id_ref):
        if not terminal_id_ref:
            messagebox.showinfo("Инфо", "Не удалось определить ID для редактирования", parent=self)
            return
        dlg = EditIdDialog(self, self.user, terminal_id_ref)
        if dlg.result:
            self._refresh_current_list()

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
            ("", ""),
            ("Действия", "Правый клик по строке или меню «Операции» / «Отчёты»"),
        ]
        self._show_detail(fields, [])

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
            ("", ""),
            ("Действия", "Правый клик по строке или меню «Операции»"),
        ]
        self._show_detail(fields, [])

    def _show_written_off_detail(self, terminal_id, row):
        fields = [
            ("S/N", row["serial_number"] or "(без S/N)"),
            ("Модель", row["model"]),
            ("Собственность", OWNERSHIP_SHORT.get(row["ownership"], row["ownership"])),
            ("Дата списания", row["written_off_at"]),
            ("Причина", row["reason"]),
            ("Комментарий", row["comment"]),
            ("Кто списал", row["approved_by_name"]),
            ("", ""),
            ("Действия", "Правый клик по строке или меню «Операции»"),
        ]
        self._show_detail(fields, [])

    def _close_active(self, binding_id):
        if not messagebox.askyesno("Подтверждение", "Закрыть этот ID у клиента?", parent=self):
            return
        comment = simpledialog.askstring("Комментарий", "Комментарий (необязательно):", parent=self) or None
        with database.get_connection() as conn:
            moved_to_warehouse = database.close_terminal_id(conn, binding_id, self.user["id"], comment=comment)
        if moved_to_warehouse:
            messagebox.showinfo("Готово",
                "ID закрыт. Это был последний активный ID терминала -- он автоматически перемещён на склад.",
                parent=self)
        else:
            messagebox.showinfo("Готово", "ID закрыт.", parent=self)
        self._refresh_current_list()

    def _open_terminal_card(self, terminal_id):
        self._remember_selection()
        TerminalCard(self, self.user, terminal_id, on_close=self._after_card_closed)

    def _open_merchant_card(self, merchant_id):
        self._remember_selection()
        MerchantCard(self, self.user, merchant_id, on_close=self._after_card_closed)

    def _remember_selection(self):
        self._pending_restore = None
        sel = self.tree.selection()
        if sel and len(sel) == 1:
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