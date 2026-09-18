# -*- coding: utf-8 -*-
"""HalkTerminalManager -- точка входа.

Запуск: python main.py
При первом запуске (если файла БД ещё нет) создаёт пустую БД по схеме
и одного пользователя admin/admin -- обязательно смените пароль после
первого входа.
"""

import config
import database
from gui.login_window import LoginWindow
from gui.main_window import MainWindow


def ensure_bootstrap_admin():
    is_new = database.init_db()
    if is_new:
        with database.get_connection() as conn:
            database.create_user(conn, "admin", "admin", "Администратор", "admin")
        print(f"Создана новая БД: {config.DB_PATH}")
        print("Создан пользователь admin / admin -- смените пароль после входа.")


def ensure_schema_and_version():
    """Догоняет схему уже существующей БД до текущей версии (новые колонки,
    таблица app_version_log) и фиксирует текущую версию программы в журнале --
    без этого при обновлении программы пришлось бы пересоздавать/переимпортировать
    базу, как раньше было с HalkAssetsGUI."""
    with database.get_connection() as conn:
        database.ensure_schema_upgrades(conn)
        database.log_app_version_if_new(conn)


def main():
    ensure_bootstrap_admin()
    ensure_schema_and_version()

    login = LoginWindow()
    login.mainloop()  # окно логина -- отдельный полноценный root, без withdraw/Toplevel

    if login.result is None:
        return

    app = MainWindow(login.result)
    app.mainloop()


if __name__ == "__main__":
    main()
