# -*- coding: utf-8 -*-
"""
database.py -- слой доступа к данным HalkTerminalManager.

Все функции (кроме get_connection/init_db) принимают уже открытое
соединение `conn` первым аргументом -- это позволяет GUI объединять
несколько операций в одну транзакцию там, где это нужно (например,
"переместить терминал" + "закрыть привязку ID" одним коммитом).

Типичное использование из GUI:

    import database

    with database.get_connection() as conn:
        results = database.search_terminals(conn, "CT2506")

    with database.get_connection() as conn:
        user = database.authenticate(conn, login, password)

get_connection() сам делает commit() при успешном выходе из `with`
и rollback() при исключении -- отдельно вызывать conn.commit() не нужно.
"""

import binascii
import hashlib
import os
from contextlib import contextmanager
from datetime import datetime, timedelta

import config


# =============================================================================
# Подключение и инициализация
# =============================================================================

@contextmanager
def get_connection():
    conn = sqlite3_connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def sqlite3_connect():
    import sqlite3
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    """Создаёт БД по схеме, если файла ещё нет. Существующую БД не трогает."""
    os.makedirs(os.path.dirname(config.DB_PATH) or ".", exist_ok=True)
    is_new = not os.path.exists(config.DB_PATH)
    if is_new:
        with get_connection() as conn:
            with open(config.SCHEMA_SQL_PATH, encoding="utf-8") as f:
                conn.executescript(f.read())
    return is_new


# Колонки, добавленные в схему уже ПОСЛЕ первого запуска у пользователя --
# чтобы не заставлять пересоздавать/переимпортировать существующую БД
# при обновлении программы. Добавлять сюда новую запись при каждом
# ALTER TABLE в будущем; ensure_schema_upgrades() идемпотентна -- безопасно
# вызывать при каждом запуске.
_SCHEMA_UPGRADES = {
    "terminal_ids": {
        "address": "TEXT",
        "phone": "TEXT",
        "install_date": "TEXT",
        "issue_date": "TEXT",
        "settlement_account": "TEXT",
    },
}


def ensure_schema_upgrades(conn):
    """Добавляет отсутствующие колонки (см. _SCHEMA_UPGRADES) в уже
    существующую БД. Ничего не делает, если колонка уже есть, поэтому
    безопасно вызывать при каждом запуске программы."""
    for table, columns in _SCHEMA_UPGRADES.items():
        existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
        for col_name, col_type in columns.items():
            if col_name not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_type}")
    if not _table_exists(conn, "app_version_log"):
        conn.execute(
            "CREATE TABLE app_version_log (id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "version TEXT NOT NULL UNIQUE, installed_at TEXT NOT NULL DEFAULT (datetime('now')), notes TEXT)"
        )


def _table_exists(conn, table_name):
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table_name,)
    ).fetchone()
    return row is not None


def log_app_version_if_new(conn, notes=None):
    """Пишет текущую config.APP_VERSION в app_version_log, если такой
    версии там ещё нет. Вызывается один раз при старте программы --
    так история версий ведётся автоматически, без ручного журнала."""
    exists = conn.execute(
        "SELECT 1 FROM app_version_log WHERE version = ?", (config.APP_VERSION,)
    ).fetchone()
    if exists is None:
        conn.execute(
            "INSERT INTO app_version_log (version, notes) VALUES (?, ?)",
            (config.APP_VERSION, notes),
        )


def get_version_history(conn, limit=50):
    return [
        dict(r) for r in conn.execute(
            "SELECT * FROM app_version_log ORDER BY installed_at DESC LIMIT ?", (limit,)
        ).fetchall()
    ]


# =============================================================================
# Пароли (без внешних библиотек)
# =============================================================================

def hash_password(password, salt=None):
    if salt is None:
        salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, config.PBKDF2_ITERATIONS)
    return f"{binascii.hexlify(salt).decode()}${binascii.hexlify(dk).decode()}"


def verify_password(password, stored_hash):
    try:
        salt_hex, _ = stored_hash.split("$")
    except (ValueError, AttributeError):
        return False
    salt = binascii.unhexlify(salt_hex)
    return hash_password(password, salt) == stored_hash


# =============================================================================
# Пользователи и аутентификация
# =============================================================================

def create_user(conn, username, password, full_name, role):
    if role not in ("admin", "user"):
        raise ValueError("role должен быть 'admin' или 'user'")
    conn.execute(
        "INSERT INTO users (username, password_hash, full_name, role) VALUES (?, ?, ?, ?)",
        (username, hash_password(password), full_name, role),
    )


def authenticate(conn, username, password):
    """Возвращает dict пользователя при успехе, иначе None."""
    row = conn.execute(
        "SELECT * FROM users WHERE username = ? AND is_active = 1", (username,)
    ).fetchone()
    if row is None or not verify_password(password, row["password_hash"]):
        return None
    return dict(row)


def list_users(conn, include_archived=True):
    query = "SELECT id, username, full_name, role, is_active, created_at FROM users"
    if not include_archived:
        query += " WHERE is_active = 1"
    query += " ORDER BY is_active DESC, full_name"
    return [dict(r) for r in conn.execute(query).fetchall()]


def _require_admin(admin_user):
    if admin_user.get("role") != "admin":
        raise PermissionError("Управлять пользователями может только администратор")


def create_user_checked(conn, admin_user, username, password, full_name, role):
    """Как create_user, но с проверкой прав и понятной ошибкой при дубле логина."""
    _require_admin(admin_user)
    existing = conn.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone()
    if existing is not None:
        raise ValueError(f"Логин '{username}' уже занят")
    create_user(conn, username, password, full_name, role)


def update_user(conn, admin_user, user_id, **fields):
    """fields: full_name, role. Логин и статус архивации меняются отдельными функциями."""
    _require_admin(admin_user)
    allowed = {"full_name", "role"}
    changes = {k: v for k, v in fields.items() if k in allowed and v is not None}
    if "role" in changes and changes["role"] not in ("admin", "user"):
        raise ValueError("role должен быть 'admin' или 'user'")
    if not changes:
        return
    set_clause = ", ".join(f"{f} = ?" for f in changes)
    conn.execute(f"UPDATE users SET {set_clause} WHERE id = ?", (*changes.values(), user_id))


def change_user_password(conn, admin_user, user_id, new_password):
    _require_admin(admin_user)
    conn.execute(
        "UPDATE users SET password_hash = ? WHERE id = ?",
        (hash_password(new_password), user_id),
    )


def change_own_password(conn, user, old_password, new_password):
    """Пользователь сам меняет свой пароль (не требует роли admin), но
    должен подтвердить текущий пароль."""
    row = conn.execute("SELECT * FROM users WHERE id = ?", (user["id"],)).fetchone()
    if row is None or not verify_password(old_password, row["password_hash"]):
        raise ValueError("Текущий пароль указан неверно")
    conn.execute(
        "UPDATE users SET password_hash = ? WHERE id = ?",
        (hash_password(new_password), user["id"]),
    )


def archive_user(conn, admin_user, user_id):
    """'Удаление' пользователя -- на самом деле архивация (is_active = 0),
    без физического удаления, чтобы не потерять ссылки в audit_log/истории."""
    _require_admin(admin_user)
    if user_id == admin_user["id"]:
        raise ValueError("Нельзя архивировать самого себя, пока вы в системе под этим пользователем")
    conn.execute("UPDATE users SET is_active = 0 WHERE id = ?", (user_id,))
    # На всякий случай снимаем все блокировки карточек, которые держал архивируемый пользователь
    conn.execute("DELETE FROM edit_locks WHERE locked_by = ?", (user_id,))


def restore_user(conn, admin_user, user_id):
    _require_admin(admin_user)
    conn.execute("UPDATE users SET is_active = 1 WHERE id = ?", (user_id,))


# =============================================================================
# Блокировка карточек на редактирование ("занято пользователем Х")
# =============================================================================

def acquire_lock(conn, entity_type, entity_id, user_id):
    """Пытается захватить карточку на редактирование.
    Возвращает (True, None) при успехе.
    Возвращает (False, lock_info) если занято другим активным пользователем;
    lock_info -- dict с полями locked_by, locked_by_name, locked_at.
    Зависшие блокировки (старше EDIT_LOCK_TIMEOUT_MINUTES) снимаются автоматически.
    """
    row = conn.execute(
        "SELECT l.locked_by, l.locked_at, u.full_name AS locked_by_name "
        "FROM edit_locks l LEFT JOIN users u ON u.id = l.locked_by "
        "WHERE l.entity_type = ? AND l.entity_id = ?",
        (entity_type, entity_id),
    ).fetchone()

    if row is not None:
        locked_at = datetime.fromisoformat(row["locked_at"])
        is_stale = datetime.now() - locked_at > timedelta(minutes=config.EDIT_LOCK_TIMEOUT_MINUTES)
        if row["locked_by"] != user_id and not is_stale:
            return False, dict(row)
        conn.execute(
            "DELETE FROM edit_locks WHERE entity_type = ? AND entity_id = ?",
            (entity_type, entity_id),
        )

    conn.execute(
        "INSERT INTO edit_locks (entity_type, entity_id, locked_by) VALUES (?, ?, ?)",
        (entity_type, entity_id, user_id),
    )
    return True, None


def release_lock(conn, entity_type, entity_id, user_id):
    conn.execute(
        "DELETE FROM edit_locks WHERE entity_type = ? AND entity_id = ? AND locked_by = ?",
        (entity_type, entity_id, user_id),
    )


def get_lock(conn, entity_type, entity_id):
    row = conn.execute(
        "SELECT l.locked_by, l.locked_at, u.full_name AS locked_by_name "
        "FROM edit_locks l LEFT JOIN users u ON u.id = l.locked_by "
        "WHERE l.entity_type = ? AND l.entity_id = ?",
        (entity_type, entity_id),
    ).fetchone()
    return dict(row) if row else None


# =============================================================================
# Аудит: журнал изменений отдельных полей
# =============================================================================

def log_change(conn, user_id, entity_type, entity_id, field_name, old_value, new_value):
    if old_value == new_value:
        return
    conn.execute(
        "INSERT INTO audit_log (user_id, entity_type, entity_id, field_name, old_value, new_value) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (
            user_id, entity_type, entity_id, field_name,
            None if old_value is None else str(old_value),
            None if new_value is None else str(new_value),
        ),
    )


def update_row_with_audit(conn, table, entity_type, row_id, user_id, changes):
    """changes: {имя_колонки: новое_значение}.
    ВАЖНО: ключи changes должны быть только захардкоженными в коде именами
    колонок (см. вызовы ниже) -- никогда не передавать сюда текст,
    введённый пользователем как имя поля (SQL-инъекция через имя колонки)."""
    if not changes:
        return
    old_row = conn.execute(f"SELECT * FROM {table} WHERE id = ?", (row_id,)).fetchone()
    if old_row is None:
        raise ValueError(f"{table} id={row_id} не найден")
    set_clause = ", ".join(f"{field} = ?" for field in changes)
    conn.execute(f"UPDATE {table} SET {set_clause} WHERE id = ?", (*changes.values(), row_id))
    for field, new_value in changes.items():
        log_change(conn, user_id, entity_type, row_id, field, old_row[field], new_value)


def get_audit_log(conn, entity_type=None, entity_id=None, limit=200):
    query = (
        "SELECT a.*, u.full_name AS user_name FROM audit_log a "
        "LEFT JOIN users u ON u.id = a.user_id WHERE 1=1"
    )
    params = []
    if entity_type:
        query += " AND a.entity_type = ?"
        params.append(entity_type)
    if entity_id:
        query += " AND a.entity_id = ?"
        params.append(entity_id)
    query += " ORDER BY a.changed_at DESC LIMIT ?"
    params.append(limit)
    return [dict(r) for r in conn.execute(query, params).fetchall()]


# =============================================================================
# Мерчанты
# =============================================================================

def search_merchants(conn, query, limit=200):
    q = f"%{query}%"
    rows = conn.execute(
        """
        SELECT DISTINCT m.id, m.m_id, m.merchant_type, m.note
        FROM merchants m
        LEFT JOIN terminal_ids ti ON ti.merchant_id = m.id
        WHERE m.m_id LIKE ? OR ti.owner_label LIKE ? OR ti.point_label LIKE ?
        ORDER BY m.m_id
        LIMIT ?
        """,
        (q, q, q, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def get_merchant(conn, merchant_id):
    merchant = conn.execute("SELECT * FROM merchants WHERE id = ?", (merchant_id,)).fetchone()
    if merchant is None:
        return None
    terminal_ids = conn.execute(
        "SELECT * FROM terminal_ids WHERE merchant_id = ? ORDER BY id", (merchant_id,)
    ).fetchall()
    status_row = conn.execute(
        "SELECT current_status FROM merchant_current_status WHERE merchant_id = ?", (merchant_id,)
    ).fetchone()
    contact = conn.execute(
        "SELECT * FROM merchant_contact_history WHERE merchant_id = ? AND valid_to IS NULL "
        "ORDER BY valid_from DESC LIMIT 1",
        (merchant_id,),
    ).fetchone()
    return {
        "merchant": dict(merchant),
        "current_status": status_row["current_status"] if status_row else None,
        "current_contact": dict(contact) if contact else None,
        "terminal_ids": [dict(r) for r in terminal_ids],
    }


def create_merchant(conn, m_id, merchant_type, user_id, note=None):
    cur = conn.execute(
        "INSERT INTO merchants (m_id, merchant_type, note) VALUES (?, ?, ?)",
        (m_id, merchant_type, note),
    )
    merchant_id = cur.lastrowid
    log_change(conn, user_id, "merchant", merchant_id, "created", None, m_id)
    return merchant_id


def update_merchant(conn, merchant_id, user_id, **fields):
    allowed = {"merchant_type", "note"}
    changes = {k: v for k, v in fields.items() if k in allowed}
    update_row_with_audit(conn, "merchants", "merchant", merchant_id, user_id, changes)


def set_merchant_status(conn, merchant_id, status, user_id, comment=None):
    if status not in ("opened", "closed"):
        raise ValueError("status должен быть 'opened' или 'closed'")
    conn.execute(
        "INSERT INTO merchant_status_history (merchant_id, status, comment, changed_by) VALUES (?, ?, ?, ?)",
        (merchant_id, status, comment, user_id),
    )


def set_merchant_contact(conn, merchant_id, address, phone, user_id):
    conn.execute(
        "UPDATE merchant_contact_history SET valid_to = datetime('now') "
        "WHERE merchant_id = ? AND valid_to IS NULL",
        (merchant_id,),
    )
    conn.execute(
        "INSERT INTO merchant_contact_history (merchant_id, address, phone, changed_by) VALUES (?, ?, ?, ?)",
        (merchant_id, address, phone, user_id),
    )


# =============================================================================
# Терминалы
# =============================================================================

def find_by_serial(conn, serial_number):
    row = conn.execute("SELECT * FROM terminals WHERE serial_number = ?", (serial_number,)).fetchone()
    return dict(row) if row else None


def search_terminals(conn, query, limit=200):
    q = f"%{query}%"
    rows = conn.execute(
        """
        SELECT DISTINCT t.id, t.serial_number, t.model, t.ownership, t.connection_type,
               s.current_place, s.condition
        FROM terminals t
        JOIN terminal_current_state s ON s.terminal_id = t.id
        LEFT JOIN terminal_id_bindings b ON b.terminal_id = t.id AND b.bound_to IS NULL
        LEFT JOIN terminal_ids ti ON ti.id = b.terminal_id_ref
        LEFT JOIN merchants m ON m.id = ti.merchant_id
        LEFT JOIN connection_history ch ON ch.terminal_id = t.id AND ch.valid_to IS NULL
        WHERE t.serial_number LIKE ? OR t.model LIKE ?
           OR ti.payment_id LIKE ? OR ti.owner_label LIKE ? OR ti.point_label LIKE ?
           OR m.m_id LIKE ? OR ch.sim_number LIKE ? OR ch.ip_address LIKE ?
        ORDER BY t.serial_number
        LIMIT ?
        """,
        (q, q, q, q, q, q, q, q, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def get_terminal_full(conn, terminal_id):
    """Полная карточка терминала: сам терминал + текущее состояние +
    вся история (подключение, перемещения, привязки ID, ремонты, списание)."""
    terminal = conn.execute("SELECT * FROM terminals WHERE id = ?", (terminal_id,)).fetchone()
    if terminal is None:
        return None
    state = conn.execute(
        "SELECT * FROM terminal_current_state WHERE terminal_id = ?", (terminal_id,)
    ).fetchone()
    connections = conn.execute(
        "SELECT * FROM connection_history WHERE terminal_id = ? ORDER BY valid_from DESC",
        (terminal_id,),
    ).fetchall()
    placements = conn.execute(
        "SELECT p.*, m.m_id FROM terminal_placements p "
        "LEFT JOIN merchants m ON m.id = p.merchant_id "
        "WHERE p.terminal_id = ? ORDER BY p.moved_at DESC",
        (terminal_id,),
    ).fetchall()
    bindings = conn.execute(
        """
        SELECT b.*, ti.payment_id, ti.transit_account, ti.settlement_account,
               ti.owner_label, ti.point_label, ti.address, ti.phone, m.m_id
        FROM terminal_id_bindings b
        JOIN terminal_ids ti ON ti.id = b.terminal_id_ref
        LEFT JOIN merchants m ON m.id = ti.merchant_id
        WHERE b.terminal_id = ?
        ORDER BY (b.bound_to IS NULL) DESC, b.bound_from DESC
        """,
        (terminal_id,),
    ).fetchall()
    repairs = conn.execute(
        "SELECT * FROM terminal_repairs WHERE terminal_id = ? ORDER BY id DESC", (terminal_id,)
    ).fetchall()
    writeoff = conn.execute(
        "SELECT * FROM terminal_writeoffs WHERE terminal_id = ?", (terminal_id,)
    ).fetchone()
    return {
        "terminal": dict(terminal),
        "current_place": state["current_place"] if state else None,
        "current_merchant_id": state["current_merchant_id"] if state else None,
        "condition": state["condition"] if state else None,
        "connections": [dict(r) for r in connections],
        "placements": [dict(r) for r in placements],
        "bindings": [dict(r) for r in bindings],
        "repairs": [dict(r) for r in repairs],
        "writeoff": dict(writeoff) if writeoff else None,
    }


def create_terminal(conn, serial_number, model, ownership, connection_type, user_id, note=None):
    if serial_number and find_by_serial(conn, serial_number):
        raise ValueError(f"Терминал с S/N {serial_number} уже существует")
    cur = conn.execute(
        "INSERT INTO terminals (serial_number, model, ownership, connection_type, note) "
        "VALUES (?, ?, ?, ?, ?)",
        (serial_number, model, ownership, connection_type, note),
    )
    terminal_id = cur.lastrowid
    log_change(conn, user_id, "terminal", terminal_id, "created", None, serial_number)
    return terminal_id


def update_terminal(conn, terminal_id, user_id, **fields):
    allowed = {"model", "ownership", "connection_type", "note"}
    changes = {k: v for k, v in fields.items() if k in allowed}
    update_row_with_audit(conn, "terminals", "terminal", terminal_id, user_id, changes)


def change_connection(conn, terminal_id, sim_number, ip_address, user_id):
    """Закрывает текущую запись подключения и открывает новую -- сохраняя историю."""
    conn.execute(
        "UPDATE connection_history SET valid_to = datetime('now') "
        "WHERE terminal_id = ? AND valid_to IS NULL",
        (terminal_id,),
    )
    conn.execute(
        "INSERT INTO connection_history (terminal_id, sim_number, ip_address, changed_by) "
        "VALUES (?, ?, ?, ?)",
        (terminal_id, sim_number, ip_address, user_id),
    )
    log_change(conn, user_id, "terminal", terminal_id, "connection",
               None, f"sim={sim_number} ip={ip_address}")


def move_terminal(conn, terminal_id, place_type, user_id, merchant_id=None, comment=None):
    """Перемещает терминал: у мерчанта / склад / мастерская.
    Место -- отдельная ось от состояния ремонта/списания (см. схему)."""
    if place_type not in ("merchant", "warehouse", "repair_shop"):
        raise ValueError("place_type должен быть merchant/warehouse/repair_shop")
    if place_type == "merchant" and merchant_id is None:
        raise ValueError("Для place_type='merchant' нужно указать merchant_id")
    conn.execute(
        "INSERT INTO terminal_placements (terminal_id, place_type, merchant_id, comment, changed_by) "
        "VALUES (?, ?, ?, ?, ?)",
        (terminal_id, place_type, merchant_id if place_type == "merchant" else None, comment, user_id),
    )


# =============================================================================
# Платёжные ID и их привязка к физическим терминалам
# =============================================================================

def create_terminal_id(conn, payment_id, transit_account, merchant_id, owner_label, point_label):
    cur = conn.execute(
        "INSERT INTO terminal_ids (payment_id, transit_account, merchant_id, owner_label, point_label) "
        "VALUES (?, ?, ?, ?, ?)",
        (payment_id, transit_account, merchant_id, owner_label, point_label),
    )
    return cur.lastrowid


def bind_terminal_id(conn, terminal_id, terminal_id_ref, user_id):
    conn.execute(
        "INSERT INTO terminal_id_bindings (terminal_id, terminal_id_ref, changed_by) VALUES (?, ?, ?)",
        (terminal_id, terminal_id_ref, user_id),
    )


def unbind_terminal_id(conn, binding_id, user_id):
    conn.execute(
        "UPDATE terminal_id_bindings SET bound_to = datetime('now'), changed_by = ? "
        "WHERE id = ? AND bound_to IS NULL",
        (user_id, binding_id),
    )


def close_terminal_id(conn, binding_id, user_id, comment=None):
    """Действие "Закрыть" на активной вкладке главного окна: отвязывает
    один платёжный ID от терминала. Если у терминала после этого не
    осталось ни одной активной привязки -- терминал автоматически
    перемещается на склад (см. move_terminal), с комментарием и
    отметкой, кто и когда это сделал (terminal_placements.changed_by/moved_at).
    Возвращает True, если терминал в результате уехал на склад."""
    row = conn.execute(
        "SELECT terminal_id FROM terminal_id_bindings WHERE id = ? AND bound_to IS NULL",
        (binding_id,),
    ).fetchone()
    if row is None:
        raise ValueError("Привязка не найдена или уже закрыта")
    terminal_id = row["terminal_id"]

    unbind_terminal_id(conn, binding_id, user_id)
    log_change(conn, user_id, "terminal_id_binding", binding_id, "closed", "active", "closed")

    remaining = conn.execute(
        "SELECT COUNT(*) c FROM terminal_id_bindings WHERE terminal_id = ? AND bound_to IS NULL",
        (terminal_id,),
    ).fetchone()["c"]
    state = conn.execute(
        "SELECT current_place FROM terminal_current_state WHERE terminal_id = ?", (terminal_id,)
    ).fetchone()
    if remaining == 0 and state and state["current_place"] == "merchant":
        move_terminal(
            conn, terminal_id, "warehouse", user_id,
            comment=comment or "автоматически: закрыт последний активный ID у мерчанта",
        )
        return True
    return False


# =============================================================================
# Ремонт и списание
# =============================================================================

def create_repair(conn, terminal_id, reason, user_id, reported_at=None, sent_at=None):
    cur = conn.execute(
        "INSERT INTO terminal_repairs (terminal_id, reason, reported_at, sent_at, created_by) "
        "VALUES (?, ?, ?, ?, ?)",
        (terminal_id, reason, reported_at, sent_at, user_id),
    )
    return cur.lastrowid


def update_repair(conn, repair_id, user_id, **fields):
    allowed = {"reported_at", "sent_at", "returned_at", "firmware_at", "result", "comment"}
    changes = {k: v for k, v in fields.items() if k in allowed}
    update_row_with_audit(conn, "terminal_repairs", "terminal_repair", repair_id, user_id, changes)


def write_off_terminal(conn, terminal_id, reason, user, comment=None):
    """Списание -- необратимое действие, разрешено только пользователю с role='admin'.
    user -- dict, как возвращает authenticate()."""
    if user.get("role") != "admin":
        raise PermissionError("Списывать терминалы может только администратор")
    conn.execute(
        "INSERT INTO terminal_writeoffs (terminal_id, reason, comment, approved_by) VALUES (?, ?, ?, ?)",
        (terminal_id, reason, comment, user["id"]),
    )


# =============================================================================
# Сводная статистика для главного экрана
# =============================================================================

def get_dashboard_stats(conn):
    stats = {}
    stats["merchants_total"] = conn.execute("SELECT COUNT(*) FROM merchants").fetchone()[0]
    stats["terminals_total"] = conn.execute("SELECT COUNT(*) FROM terminals").fetchone()[0]
    for row in conn.execute(
        "SELECT current_place, COUNT(*) c FROM terminal_current_state GROUP BY current_place"
    ):
        stats[f"place_{row['current_place']}"] = row["c"]
    for row in conn.execute(
        "SELECT condition, COUNT(*) c FROM terminal_current_state GROUP BY condition"
    ):
        stats[f"condition_{row['condition']}"] = row["c"]
    for row in conn.execute("SELECT ownership, COUNT(*) c FROM terminals GROUP BY ownership"):
        stats[f"ownership_{row['ownership']}"] = row["c"]
    for row in conn.execute("SELECT model, COUNT(*) c FROM terminals GROUP BY model ORDER BY c DESC"):
        stats.setdefault("by_model", []).append((row["model"], row["c"]))
    return stats


# =============================================================================
# Представления для главного окна: вкладки "Активные" / "Склад" / "E-POS"
# =============================================================================
# Один физический терминал может иметь несколько активных платёжных ID --
# на вкладке "Активные" (как раньше в Excel) строка -- это один активный
# ID, а не один физический терминал; группировка в дереве -- по merchant_type.

_ACTIVE_BASE_QUERY = """
    SELECT
        b.id AS binding_id, b.terminal_id, ti.id AS terminal_id_ref,
        ti.payment_id, ti.transit_account, ti.settlement_account,
        ti.owner_label, ti.point_label, ti.address, ti.phone,
        m.id AS merchant_id, m.m_id, m.merchant_type,
        t.serial_number, t.model
    FROM terminal_id_bindings b
    JOIN terminal_ids ti ON ti.id = b.terminal_id_ref
    JOIN merchants m ON m.id = ti.merchant_id
    JOIN terminals t ON t.id = b.terminal_id
    JOIN terminal_current_state s ON s.terminal_id = b.terminal_id
    WHERE b.bound_to IS NULL
      AND t.is_epos = 0
      AND s.current_place = 'merchant'
      AND s.condition != 'written_off'
"""


def get_active_terminal_ids(conn, merchant_type=None, query=None, limit=2000):
    """Список для вкладки "Активные": один активный платёжный ID = одна строка,
    как раньше выглядело в Excel. merchant_type -- фильтр 'bank'/'edara'/'telekeci'/...,
    None = все типы."""
    sql = _ACTIVE_BASE_QUERY
    params = []
    if merchant_type:
        sql += " AND m.merchant_type = ?"
        params.append(merchant_type)
    if query:
        q = f"%{query}%"
        sql += (
            " AND (ti.payment_id LIKE ? OR ti.owner_label LIKE ? OR ti.point_label LIKE ? "
            "OR m.m_id LIKE ? OR t.serial_number LIKE ? OR ti.address LIKE ? OR ti.phone LIKE ?)"
        )
        params += [q, q, q, q, q, q, q]
    sql += " ORDER BY m.merchant_type, ti.owner_label, ti.payment_id LIMIT ?"
    params.append(limit)
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def get_terminal_id_detail(conn, binding_id):
    """Детали для правой панели при выборе строки на вкладке "Активные"."""
    row = conn.execute(
        _ACTIVE_BASE_QUERY.replace("WHERE b.bound_to IS NULL", "WHERE b.id = ?"),
        (binding_id,),
    ).fetchone()
    if row is None:
        # привязка могла быть уже закрыта -- ищем без ограничения по текущему состоянию
        row = conn.execute(
            """
            SELECT b.id AS binding_id, b.terminal_id, ti.id AS terminal_id_ref,
                   ti.payment_id, ti.transit_account, ti.settlement_account,
                   ti.owner_label, ti.point_label, ti.address, ti.phone,
                   m.id AS merchant_id, m.m_id, m.merchant_type,
                   t.serial_number, t.model
            FROM terminal_id_bindings b
            JOIN terminal_ids ti ON ti.id = b.terminal_id_ref
            JOIN merchants m ON m.id = ti.merchant_id
            JOIN terminals t ON t.id = b.terminal_id
            WHERE b.id = ?
            """,
            (binding_id,),
        ).fetchone()
    if row is None:
        return None
    data = dict(row)
    conn_row = conn.execute(
        "SELECT sim_number, ip_address FROM connection_history "
        "WHERE terminal_id = ? AND valid_to IS NULL",
        (data["terminal_id"],),
    ).fetchone()
    data["sim_number"] = conn_row["sim_number"] if conn_row else None
    data["ip_address"] = conn_row["ip_address"] if conn_row else None
    return data


def get_active_dashboard_stats(conn):
    """Сводка для вкладки "Активные" -- считает только то, что реально
    показано в списке (активно у мерчанта, не списано, не E-POS)."""
    rows = conn.execute(
        """
        SELECT m.merchant_type, COUNT(*) c
        FROM terminal_id_bindings b
        JOIN terminal_ids ti ON ti.id = b.terminal_id_ref
        JOIN merchants m ON m.id = ti.merchant_id
        JOIN terminals t ON t.id = b.terminal_id
        JOIN terminal_current_state s ON s.terminal_id = b.terminal_id
        WHERE b.bound_to IS NULL AND t.is_epos = 0
          AND s.current_place = 'merchant' AND s.condition != 'written_off'
        GROUP BY m.merchant_type
        """
    ).fetchall()
    stats = {"total": 0}
    for row in rows:
        stats[row["merchant_type"] or "unknown"] = row["c"]
        stats["total"] += row["c"]
    return stats


def get_warehouse_terminals(conn, query=None, limit=2000):
    """Список для вкладки "Склад": физические терминалы, которые сейчас
    НЕ у мерчанта (склад/мастерская) либо списаны. Показывает, кто и когда
    последний раз переместил терминал (terminal_placements)."""
    sql = """
        SELECT t.id AS terminal_id, t.serial_number, t.model, t.ownership,
               s.current_place, s.condition,
               lp.moved_at AS last_moved_at, lp.comment AS last_comment,
               u.full_name AS moved_by_name
        FROM terminals t
        JOIN terminal_current_state s ON s.terminal_id = t.id
        LEFT JOIN (
            SELECT terminal_id, MAX(id) AS last_id FROM terminal_placements GROUP BY terminal_id
        ) lpm ON lpm.terminal_id = t.id
        LEFT JOIN terminal_placements lp ON lp.id = lpm.last_id
        LEFT JOIN users u ON u.id = lp.changed_by
        WHERE t.is_epos = 0
          AND (s.current_place != 'merchant' OR s.condition = 'written_off')
    """
    params = []
    if query:
        q = f"%{query}%"
        sql += " AND (t.serial_number LIKE ? OR t.model LIKE ?)"
        params += [q, q]
    sql += " ORDER BY (s.condition = 'written_off'), lp.moved_at DESC LIMIT ?"
    params.append(limit)
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def get_warehouse_dashboard_stats(conn):
    stats = {"warehouse": 0, "repair_shop": 0, "written_off": 0, "total": 0}
    rows = conn.execute(
        """
        SELECT s.current_place, s.condition, COUNT(*) c
        FROM terminal_current_state s
        JOIN terminals t ON t.id = s.terminal_id
        WHERE t.is_epos = 0 AND (s.current_place != 'merchant' OR s.condition = 'written_off')
        GROUP BY s.current_place, s.condition
        """
    ).fetchall()
    for row in rows:
        if row["condition"] == "written_off":
            stats["written_off"] += row["c"]
        elif row["current_place"] in ("warehouse", "repair_shop"):
            stats[row["current_place"]] += row["c"]
        stats["total"] += row["c"]
    return stats


def get_epos_terminals(conn, query=None, limit=2000):
    """Список для вкладки "E-POS": терминалы с is_epos = 1, вместе с их
    активными платёжными ID (если есть)."""
    sql = """
        SELECT t.id AS terminal_id, t.model, t.note,
               b.id AS binding_id, ti.payment_id, ti.owner_label, ti.point_label,
               ti.address, ti.phone, m.m_id, m.merchant_type
        FROM terminals t
        LEFT JOIN terminal_id_bindings b ON b.terminal_id = t.id AND b.bound_to IS NULL
        LEFT JOIN terminal_ids ti ON ti.id = b.terminal_id_ref
        LEFT JOIN merchants m ON m.id = ti.merchant_id
        WHERE t.is_epos = 1
    """
    params = []
    if query:
        q = f"%{query}%"
        sql += " AND (ti.payment_id LIKE ? OR ti.owner_label LIKE ? OR ti.point_label LIKE ? OR m.m_id LIKE ?)"
        params += [q, q, q, q]
    sql += " ORDER BY m.merchant_type, ti.owner_label LIMIT ?"
    params.append(limit)
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def get_epos_dashboard_stats(conn):
    total = conn.execute("SELECT COUNT(*) c FROM terminals WHERE is_epos = 1").fetchone()["c"]
    return {"total": total}
