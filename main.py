# -*- coding: utf-8 -*-
"""Terminal Manager -- точка входа.

Запуск: python main.py

При старте:
  1. Инициализируется логирование (см. logger.py).
  2. Проверяется блокировка (только один пользователь за раз).
  3. Если БД нет -- создаётся пустая и заводится admin/admin.
  4. Догоняется схема БД до текущей версии.
  5. Проверка целостности (не пустая ли БД, доступна ли).
  6. Окно логина -> главное окно.

При любом закрытии (штатном или через "Выход") снимается блокировка.
"""

import traceback

import config
import database
import instance_lock
import logger
from gui.login_window import LoginWindow
from gui.main_window import MainWindow


def ensure_bootstrap_admin():
    is_new = database.init_db()
    if is_new:
        with database.get_connection() as conn:
            database.create_user(conn, "admin", "admin", "Администратор", "admin")
        logger.log.info(f"Создана новая БД: {config.DB_PATH}")
        logger.log.info("Создан пользователь admin / admin -- смените пароль после входа.")


def ensure_schema_and_version():
    with database.get_connection() as conn:
        database.ensure_schema_upgrades(conn)
        database.log_app_version_if_new(conn)


def check_database_integrity():
    from tkinter import messagebox
    try:
        with database.get_connection() as conn:
            n = conn.execute("SELECT COUNT(*) FROM terminals").fetchone()[0]
        if n == 0:
            messagebox.showwarning(
                "Пустая база",
                "В базе данных нет ни одного терминала.\n\n"
                "Возможные причины:\n"
                "  - База не заполнена (свежая установка).\n"
                "  - Импорт из Excel не выполнялся.\n\n"
                "Обратитесь к администратору, если это не так.",
            )
        return True
    except Exception as exc:
        logger.log.exception("Ошибка чтения БД при старте")
        messagebox.showerror(
            "Ошибка базы данных",
            f"Не удалось прочитать базу:\n{exc}\n\n"
            f"Путь: {config.DB_PATH}\n\n"
            "Программа будет закрыта.",
        )
        return False


def show_lock_error(owner_info):
    from tkinter import messagebox, Tk
    root = Tk()
    root.withdraw()
    try:
        if "error" in owner_info:
            messagebox.showerror(
                "Ошибка блокировки",
                owner_info["error"] +
                "\n\nПроверьте доступ к сетевой папке с базой данных.",
            )
        else:
            messagebox.showwarning(
                "Программа уже запущена",
                "В данный момент программу использует:\n\n"
                f"{instance_lock.describe_lock_owner(owner_info)}\n\n"
                "Одновременно может работать только один пользователь.\n"
                "Попробуйте позже или обратитесь к текущему пользователю.",
            )
    finally:
        root.destroy()


def main():
    # 1. Логирование -- самое первое, до всего остального
    logger.setup()
    logger.install_exception_hook()

    # 2. Блокировка -- только один пользователь одновременно
    ok, owner = instance_lock.try_acquire_lock()
    if not ok:
        if "error" in owner:
            logger.log.error(f"Не удалось занять блокировку: {owner['error']}")
        else:
            logger.log.warning(
                f"Программа уже занята: пользователь={owner.get('user')}, "
                f"компьютер={owner.get('computer')}"
            )
        show_lock_error(owner)
        logger.shutdown()
        return

    logger.log.info(
        f"Блокировка занята: пользователь={instance_lock._lock_info['user']}, "
        f"компьютер={instance_lock._lock_info['computer']}"
    )

    try:
        # 3. Инициализация БД
        ensure_bootstrap_admin()
        ensure_schema_and_version()

        # 4. Проверка целостности
        if not check_database_integrity():
            return

        # 5. Heartbeat
        instance_lock.start_heartbeat()

        # 6. Логин
        login = LoginWindow()
        login.mainloop()
        if login.result is None:
            logger.log.info("Вход отменён пользователем")
            return

        user = login.result
        logger.log.info(f"Вход: {user['username']} ({user['full_name']}, {user['role']})")

        # 7. Главное окно
        app = MainWindow(user)
        app.mainloop()

        logger.log.info(f"Выход: {user['username']}")
    except Exception:
        logger.log.exception("Необработанная ошибка в main")
        raise
    finally:
        instance_lock.release_lock()
        logger.shutdown()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # На самый крайний случай -- если main() вообще не смог стартовать
        traceback.print_exc()
        logger.log.exception("Критическая ошибка при запуске")