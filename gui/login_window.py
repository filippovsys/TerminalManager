# -*- coding: utf-8 -*-
"""Окно логина -- самостоятельное окно (не Toplevel), чтобы не зависеть
от скрытого родительского окна (частая причина 'ничего не появляется'
на Windows из-за withdraw()+grab_set()).

После успешного входа кладёт пользователя в self.result и закрывает себя;
main.py дальше запускает главное окно приложения отдельно."""

import tkinter as tk
from tkinter import ttk, messagebox

import database
from gui import utils


class LoginWindow(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("HalkTerminalManager -- вход")
        self.resizable(False, False)
        self.result = None

        frame = ttk.Frame(self, padding=20)
        frame.grid()

        ttk.Label(frame, text="Логин:").grid(row=0, column=0, sticky="w", pady=4)
        self.username_var = tk.StringVar()
        username_entry = ttk.Entry(frame, textvariable=self.username_var, width=28)
        username_entry.grid(row=0, column=1, pady=4)

        ttk.Label(frame, text="Пароль:").grid(row=1, column=0, sticky="w", pady=4)
        self.password_var = tk.StringVar()
        password_entry = ttk.Entry(frame, textvariable=self.password_var, show="*", width=28)
        password_entry.grid(row=1, column=1, pady=4)

        self.error_label = ttk.Label(frame, text="", foreground="red")
        self.error_label.grid(row=2, column=0, columnspan=2)

        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=3, column=0, columnspan=2, pady=(10, 0))
        ttk.Button(btn_frame, text="Войти", command=self._try_login).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="Отмена", command=self._cancel).pack(side="left", padx=4)

        utils.fix_paste_bindings(username_entry)
        utils.fix_paste_bindings(password_entry)

        username_entry.focus_set()
        password_entry.bind("<Return>", lambda e: self._try_login())
        self.protocol("WM_DELETE_WINDOW", self._cancel)

        # Принудительно вывести окно на передний план при запуске (частая
        # проблема на Windows -- окно открывается, но остаётся за другими)
        self.lift()
        self.attributes("-topmost", True)
        self.after(300, lambda: self.attributes("-topmost", False))
        self.focus_force()

    def _try_login(self):
        username = self.username_var.get().strip()
        password = self.password_var.get()
        if not username or not password:
            self.error_label.config(text="Введите логин и пароль")
            return
        try:
            with database.get_connection() as conn:
                user = database.authenticate(conn, username, password)
        except Exception as exc:
            messagebox.showerror("Ошибка", f"Не удалось подключиться к БД:\n{exc}")
            return
        if user is None:
            self.error_label.config(text="Неверный логин или пароль")
            return
        self.result = user
        self.destroy()

    def _cancel(self):
        self.result = None
        self.destroy()
