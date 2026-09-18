# -*- coding: utf-8 -*-
"""Справочник пользователей (доступен только admin): создание, смена
пароля, изменение ФИО/роли, архивация ("удаление" -- на самом деле
is_active = 0, физически запись не удаляется) и восстановление из архива."""

import tkinter as tk
from tkinter import ttk, messagebox, simpledialog

import database
from gui import utils


class UsersWindow(tk.Toplevel):
    def __init__(self, master, admin_user):
        super().__init__(master)
        self.admin_user = admin_user
        self.title("Пользователи")
        self.geometry("640x420")

        self._build()
        utils.apply_to_all_entries(self)
        self._load()

    # ------------------------------------------------------------------
    def _build(self):
        cols = ("username", "full_name", "role", "status")
        headings = {"username": "Логин", "full_name": "ФИО", "role": "Роль", "status": "Статус"}
        self.tree = ttk.Treeview(self, columns=cols, show="headings", height=14)
        for c in cols:
            self.tree.heading(c, text=headings[c])
            self.tree.column(c, width=140, anchor="w")
        self.tree.pack(fill="both", expand=True, padx=10, pady=10)
        self._user_ids_by_iid = {}

        btns = ttk.Frame(self, padding=(10, 0, 10, 10))
        btns.pack(fill="x")
        ttk.Button(btns, text="Создать...", command=self._create_user).pack(side="left", padx=2)
        ttk.Button(btns, text="Изменить ФИО/роль...", command=self._edit_user).pack(side="left", padx=2)
        ttk.Button(btns, text="Сменить пароль...", command=self._change_password).pack(side="left", padx=2)
        ttk.Button(btns, text="Архивировать", command=self._archive_user).pack(side="left", padx=2)
        ttk.Button(btns, text="Восстановить", command=self._restore_user).pack(side="left", padx=2)
        ttk.Button(btns, text="Обновить", command=self._load).pack(side="right", padx=2)

    def _load(self):
        with database.get_connection() as conn:
            users = database.list_users(conn, include_archived=True)
        self.tree.delete(*self.tree.get_children())
        self._user_ids_by_iid.clear()
        for u in users:
            status = "активен" if u["is_active"] else "в архиве"
            iid = self.tree.insert("", "end", values=(u["username"], u["full_name"] or "", u["role"], status))
            self._user_ids_by_iid[iid] = u

    def _selected_user(self):
        selection = self.tree.selection()
        if not selection:
            messagebox.showinfo("Выбор", "Сначала выберите пользователя в списке", parent=self)
            return None
        return self._user_ids_by_iid.get(selection[0])

    # ------------------------------------------------------------------
    def _create_user(self):
        username = simpledialog.askstring("Новый пользователь", "Логин:", parent=self)
        if not username:
            return
        full_name = simpledialog.askstring("Новый пользователь", "ФИО:", parent=self) or None
        role = simpledialog.askstring("Новый пользователь", "Роль (admin / user):", parent=self)
        if role not in ("admin", "user"):
            messagebox.showerror("Ошибка", "Роль должна быть admin или user", parent=self)
            return
        password = simpledialog.askstring("Новый пользователь", "Пароль:", parent=self, show="*")
        if not password:
            return
        try:
            with database.get_connection() as conn:
                database.create_user_checked(conn, self.admin_user, username, password, full_name, role)
        except (ValueError, PermissionError) as exc:
            messagebox.showerror("Ошибка", str(exc), parent=self)
            return
        self._load()

    def _edit_user(self):
        user = self._selected_user()
        if user is None:
            return
        full_name = simpledialog.askstring("ФИО", "ФИО:", initialvalue=user["full_name"] or "", parent=self)
        if full_name is None:
            return
        role = simpledialog.askstring(
            "Роль", "Роль (admin / user):", initialvalue=user["role"], parent=self
        )
        if role not in ("admin", "user"):
            messagebox.showerror("Ошибка", "Роль должна быть admin или user", parent=self)
            return
        try:
            with database.get_connection() as conn:
                database.update_user(conn, self.admin_user, user["id"], full_name=full_name or None, role=role)
        except PermissionError as exc:
            messagebox.showerror("Ошибка", str(exc), parent=self)
            return
        self._load()

    def _change_password(self):
        user = self._selected_user()
        if user is None:
            return
        password = simpledialog.askstring(
            "Новый пароль", f"Новый пароль для {user['username']}:", parent=self, show="*"
        )
        if not password:
            return
        with database.get_connection() as conn:
            database.change_user_password(conn, self.admin_user, user["id"], password)
        messagebox.showinfo("Готово", "Пароль изменён", parent=self)

    def _archive_user(self):
        user = self._selected_user()
        if user is None:
            return
        if not messagebox.askyesno(
            "Подтверждение",
            f"Отправить пользователя {user['username']} в архив? Он не сможет войти в программу, "
            f"но история его действий сохранится.",
            parent=self,
        ):
            return
        try:
            with database.get_connection() as conn:
                database.archive_user(conn, self.admin_user, user["id"])
        except (ValueError, PermissionError) as exc:
            messagebox.showerror("Ошибка", str(exc), parent=self)
            return
        self._load()

    def _restore_user(self):
        user = self._selected_user()
        if user is None:
            return
        with database.get_connection() as conn:
            database.restore_user(conn, self.admin_user, user["id"])
        self._load()
