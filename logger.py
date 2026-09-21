# -*- coding: utf-8 -*-
"""
Логирование Terminal Manager.

Куда пишем:
  data/logs/app.log     -- текущий лог
  data/logs/app.log.1   -- старый (при переполнении)
  ...
Максимум 5 архивных файлов по 1 МБ -- старые удаляются автоматически.

Что логируем:
  - запуск / выход программы
  - вход / выход пользователя
  - необработанные исключения (с полным traceback)
  - ошибки при работе с БД
  - действия с данными (создание/закрытие ID, перемещения) -- на уровне INFO

Вызов:
    import logger
    logger.setup()             # при старте (в main.py)
    logger.log.info("...")     # обычные события
    logger.log.warning("...")  # предупреждения
    logger.log.error("...")    # ошибки
"""

import logging
import os
import sys
from logging.handlers import RotatingFileHandler

import config


LOG_DIR = os.path.join(os.path.dirname(config.DB_PATH), "logs")
LOG_FILE = os.path.join(LOG_DIR, "app.log")

MAX_BYTES = 1_000_000    # 1 МБ на файл
BACKUP_COUNT = 5         # храним 5 старых файлов

log = logging.getLogger("terminal_manager")
_setup_done = False


def setup():
    """Настраивает логирование. Идемпотентно -- повторный вызов ничего не делает."""
    global _setup_done
    if _setup_done:
        return
    _setup_done = True

    try:
        os.makedirs(LOG_DIR, exist_ok=True)
    except Exception:
        # Если не удалось создать папку логов -- просто не пишем
        return

    log.setLevel(logging.INFO)
    log.propagate = False

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Файл с ротацией
    try:
        fh = RotatingFileHandler(
            LOG_FILE, maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT, encoding="utf-8"
        )
        fh.setFormatter(fmt)
        log.addHandler(fh)
    except Exception:
        pass

    # Дублируем в консоль (пригодится при запуске из исходников)
    try:
        ch = logging.StreamHandler(sys.stderr)
        ch.setFormatter(fmt)
        log.addHandler(ch)
    except Exception:
        pass

    log.info("=" * 60)
    log.info(f"Terminal Manager v{config.APP_VERSION} -- старт")


def install_exception_hook():
    """Перехватывает все необработанные исключения и пишет их в лог."""
    def handle(exc_type, exc_value, exc_tb):
        log.critical(
            "Необработанное исключение",
            exc_info=(exc_type, exc_value, exc_tb),
        )
        # Всё равно вызываем стандартный обработчик (показывает traceback в консоли)
        sys.__excepthook__(exc_type, exc_value, exc_tb)

    sys.excepthook = handle


def shutdown():
    """Финальная запись при закрытии программы."""
    log.info("Terminal Manager -- завершение работы")
    log.info("=" * 60)
    logging.shutdown()


def get_log_dir():
    """Путь к папке с логами -- для кнопки "Открыть папку с логами"."""
    return LOG_DIR