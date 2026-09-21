# -*- coding: utf-8 -*-
"""Окно логина -- с логотипом и аккуратным оформлением.

При успешном входе кладёт пользователя в self.result и закрывает себя.
main.py дальше запускает главное окно приложения отдельно."""

import tkinter as tk
from tkinter import ttk, messagebox

import config
import database
from gui import utils
from gui.icons import set_window_icon, get_logo_path


class LoginWindow(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Terminal Manager -- вход")
        self.resizable(False, False)
        self.result = None

        set_window_icon(self)

        # --- Основной контейнер ---
        outer = ttk.Frame(self, padding=(40, 24, 40, 24))
        outer.pack(fill="both", expand=True)

        # --- Логотип ---
        self._logo_image = None   # держим ссылку, иначе Tk удалит картинку
        logo_path = get_logo_path()
        if logo_path:
            try:
                self._logo_image = tk.PhotoImage(file=logo_path)
                ttk.Label(outer, image=self._logo_image).pack(pady=(0, 10))
            except Exception:
                self._logo_image = None

        # --- Заголовок ---
        ttk.Label(
            outer, text="Terminal Manager",
            font=("TkDefaultFont", 16, "bold"),
        ).pack(pady=(0, 2))

        ttk.Label(
            outer, text=f"версия {config.APP_VERSION}",
            font=("TkDefaultFont", 9),
            foreground="gray",
        ).pack(pady=(0, 18))

        # --- Форма ---
        form = ttk.Frame(outer)
        form.pack()

        ttk.Label(form, text="Логин:").grid(row=0, column=0, sticky="w", pady=(4, 4))
        self.username_var = tk.StringVar()
        username_entry = ttk.Entry(form, textvariable=self.username_var, width=28)
        username_entry.grid(row=0, column=1, pady=(4, 4), padx=(8, 0))

        ttk.Label(form, text="Пароль:").grid(row=1, column=0, sticky="w", pady=(4, 4))
        self.password_var = tk.StringVar()
        password_entry = ttk.Entry(form, textvariable=self.password_var, show="*", width=28)
        password_entry.grid(row=1, column=1, pady=(4, 4), padx=(8, 0))

        self.error_label = ttk.Label(outer, text="", foreground="red")
        self.error_label.pack(pady=(8, 0))

        # --- Кнопки ---
        btn_frame = ttk.Frame(outer)
        btn_frame.pack(pady=(12, 0))
        ttk.Button(btn_frame, text="Войти", width=12,
                   command=self._try_login).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="Отмена", width=12,
                   command=self._cancel).pack(side="left", padx=4)

        # --- Хоткеи и фокус ---
        utils.fix_paste_bindings(username_entry)
        utils.fix_paste_bindings(password_entry)

        username_entry.focus_set()
        username_entry.bind("<Return>", lambda e: password_entry.focus_set())
        password_entry.bind("<Return>", lambda e: self._try_login())
        self.bind("<Escape>", lambda e: self._cancel())

        self.protocol("WM_DELETE_WINDOW", self._cancel)

        # Размер окна -- по содержимому
        self.update_idletasks()
        self._center_on_screen()

        # Принудительно на передний план (частая проблема на Windows)
        self.lift()
        self.attributes("-topmost", True)
        self.after(300, lambda: self.attributes("-topmost", False))
        self.focus_force()

    def _center_on_screen(self):
        self.update_idletasks()
        w = self.winfo_width()
        h = self.winfo_height()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        x = (sw - w) // 2
        y = (sh - h) // 2 - 40   # чуть выше центра
        self.geometry(f"+{x}+{y}")

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