-- =============================================================================
-- HalkTerminalManager -- схема БД (SQLite), версия 2
-- Исправлено по итогам разбора: убраны дублирующие источники истины
-- (terminals.status, is_active), разделены "место" и "состояние",
-- ФИО/наименование перенесены с мерчанта на конкретный ID (см. обоснование
-- в чате: M/id для типа Bank -- это счёт/касса, а не клиент).
-- =============================================================================

PRAGMA foreign_keys = ON;

-- ---------------------------------------------------------------------------
-- Пользователи и права
-- ---------------------------------------------------------------------------
CREATE TABLE users (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    username        TEXT NOT NULL UNIQUE,
    password_hash   TEXT NOT NULL,
    full_name       TEXT,
    role            TEXT NOT NULL CHECK (role IN ('admin', 'user')),
    is_active       INTEGER NOT NULL DEFAULT 1,   -- это реальный флаг учётки, не вычисляемый статус бизнес-сущности
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Блокировка "по карточке": кто сейчас редактирует конкретную запись
CREATE TABLE edit_locks (
    entity_type     TEXT NOT NULL,      -- 'terminal' / 'merchant' / ...
    entity_id       INTEGER NOT NULL,
    locked_by       INTEGER NOT NULL REFERENCES users(id),
    locked_at       TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (entity_type, entity_id)
);

-- Журнал версий приложения -- заполняется автоматически при запуске,
-- если config.APP_VERSION ещё не встречается в этой таблице (см.
-- database.log_app_version_if_new()). Не связан со схемой БД --
-- это версия именно программы (GUI/database.py), не структуры таблиц.
CREATE TABLE app_version_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    version         TEXT NOT NULL UNIQUE,
    installed_at    TEXT NOT NULL DEFAULT (datetime('now')),
    notes           TEXT
);

-- ---------------------------------------------------------------------------
-- Мерчанты: только то, что реально стабильно на уровне клиента.
-- НЕ храним здесь ФИО/наименование -- см. terminal_ids.owner_label/point_label
-- ---------------------------------------------------------------------------
CREATE TABLE merchants (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    m_id            TEXT NOT NULL UNIQUE,        -- проверено на реальных данных: не конфликтует между разными клиентами
    merchant_type   TEXT NOT NULL CHECK (merchant_type IN ('telekeci', 'edara', 'bank')),
    note            TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Активность мерчанта -- ТОЛЬКО через историю, без кэш-флага
CREATE TABLE merchant_status_history (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    merchant_id     INTEGER NOT NULL REFERENCES merchants(id),
    status          TEXT NOT NULL CHECK (status IN ('opened', 'closed')),
    changed_at      TEXT NOT NULL DEFAULT (datetime('now')),
    comment         TEXT,
    changed_by      INTEGER REFERENCES users(id)
);

-- Адрес/телефон -- тоже могут меняться, тоже история
CREATE TABLE merchant_contact_history (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    merchant_id     INTEGER NOT NULL REFERENCES merchants(id),
    address         TEXT,
    phone           TEXT,
    valid_from      TEXT NOT NULL DEFAULT (datetime('now')),
    valid_to        TEXT,
    changed_by      INTEGER REFERENCES users(id)
);

-- ---------------------------------------------------------------------------
-- Физический терминал
-- ---------------------------------------------------------------------------
CREATE TABLE terminals (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    serial_number       TEXT UNIQUE,             -- NULL допустим только для E-POS
    is_epos             INTEGER NOT NULL DEFAULT 0,
    model               TEXT,
    ownership           TEXT NOT NULL DEFAULT 'bank' CHECK (ownership IN ('bank', 'client')),
    connection_type     TEXT CHECK (connection_type IN ('sim', 'ethernet', NULL)),
    note                TEXT,
    created_at          TEXT NOT NULL DEFAULT (datetime('now'))
    -- статус НЕ хранится здесь -- см. VIEW terminal_current_state в конце файла
);
CREATE INDEX idx_terminals_model ON terminals(model);

CREATE TABLE connection_history (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    terminal_id     INTEGER NOT NULL REFERENCES terminals(id),
    sim_number      TEXT,
    ip_address      TEXT,
    valid_from      TEXT NOT NULL DEFAULT (datetime('now')),
    valid_to        TEXT,
    changed_by      INTEGER REFERENCES users(id)
);
CREATE INDEX idx_conn_hist_terminal ON connection_history(terminal_id);
CREATE INDEX idx_conn_hist_sim ON connection_history(sim_number);
CREATE INDEX idx_conn_hist_ip ON connection_history(ip_address);

-- Физическое МЕСТО терминала (не путать с состоянием ремонта/списания)
CREATE TABLE terminal_placements (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    terminal_id     INTEGER NOT NULL REFERENCES terminals(id),
    place_type      TEXT NOT NULL CHECK (place_type IN ('merchant', 'warehouse', 'repair_shop')),
    merchant_id     INTEGER REFERENCES merchants(id),   -- заполнено только когда place_type = 'merchant'
    moved_at        TEXT NOT NULL DEFAULT (datetime('now')),
    comment         TEXT,
    changed_by      INTEGER REFERENCES users(id)
);
CREATE INDEX idx_placements_terminal ON terminal_placements(terminal_id, moved_at);
CREATE INDEX idx_placements_merchant ON terminal_placements(merchant_id);

-- ---------------------------------------------------------------------------
-- Платёжный ID: payment_id + транз.счёт (строго 1:1, подтверждено) +
-- owner_label/point_label -- то, что раньше пытались хранить на мерчанте
-- ---------------------------------------------------------------------------
CREATE TABLE terminal_ids (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    payment_id          TEXT NOT NULL,
    transit_account     TEXT,
    merchant_id         INTEGER NOT NULL REFERENCES merchants(id),
    owner_label         TEXT,     -- бывшее "Ф.И. владельца" -- у Bank это может быть плательщик, у Telekeçi -- сам предприниматель
    point_label         TEXT,     -- бывшее "Наименование организации" -- точка/назначение платежа
    address             TEXT,
    phone               TEXT,
    install_date        TEXT,     -- дата установки (со слов исходной таблицы)
    issue_date          TEXT,     -- дата выдачи
    settlement_account  TEXT,     -- расчётный счёт -- пока не заполняется при импорте, поле на будущее
    note                TEXT
    -- активность НЕ хранится здесь -- см. terminal_id_bindings.bound_to IS NULL
);
CREATE INDEX idx_terminal_ids_payment_id ON terminal_ids(payment_id);
CREATE INDEX idx_terminal_ids_merchant ON terminal_ids(merchant_id);

-- Связь физический терминал <-> платёжный ID, многие-ко-многим, с датами
CREATE TABLE terminal_id_bindings (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    terminal_id     INTEGER NOT NULL REFERENCES terminals(id),
    terminal_id_ref INTEGER NOT NULL REFERENCES terminal_ids(id),
    bound_from      TEXT NOT NULL DEFAULT (datetime('now')),
    bound_to        TEXT,                        -- NULL = привязка активна сейчас
    changed_by      INTEGER REFERENCES users(id)
);
CREATE INDEX idx_bindings_terminal ON terminal_id_bindings(terminal_id);
CREATE INDEX idx_bindings_terminal_id_ref ON terminal_id_bindings(terminal_id_ref);

-- ---------------------------------------------------------------------------
-- Ремонт -- это же источник "состояния" (в ремонте / ожидает прошивку)
-- ---------------------------------------------------------------------------
CREATE TABLE terminal_repairs (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    terminal_id         INTEGER NOT NULL REFERENCES terminals(id),
    reason              TEXT,
    reported_at         TEXT,                    -- клиент сообщил
    sent_at             TEXT,                    -- отправлен в ремонт
    returned_at         TEXT,                    -- вернулся из ремонта (значит: ожидает прошивку, пока firmware_at пуст)
    firmware_at         TEXT,                    -- прошит после ремонта (значит: ремонт полностью завершён)
    result              TEXT,
    comment             TEXT,
    created_by          INTEGER REFERENCES users(id)
);
CREATE INDEX idx_repairs_terminal ON terminal_repairs(terminal_id);

-- Списание -- финальное, необратимое состояние
CREATE TABLE terminal_writeoffs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    terminal_id     INTEGER NOT NULL UNIQUE REFERENCES terminals(id),
    written_off_at  TEXT NOT NULL DEFAULT (datetime('now')),
    reason          TEXT,
    comment         TEXT,
    approved_by     INTEGER REFERENCES users(id)   -- только admin
);

-- ---------------------------------------------------------------------------
-- Импорт: нераспознанные строки "Состояние" -- на ручной разбор
-- ---------------------------------------------------------------------------
CREATE TABLE import_review_queue (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    sheet_name      TEXT NOT NULL,
    serial_number   TEXT,
    payment_id      TEXT,
    raw_status_text TEXT,
    resolved        INTEGER NOT NULL DEFAULT 0,
    resolution_note TEXT
);

-- ---------------------------------------------------------------------------
-- Глобальный журнал изменений (аудит отдельных полей)
-- ---------------------------------------------------------------------------
CREATE TABLE audit_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER REFERENCES users(id),
    entity_type     TEXT NOT NULL,
    entity_id       INTEGER NOT NULL,
    field_name      TEXT,
    old_value       TEXT,
    new_value       TEXT,
    changed_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_audit_entity ON audit_log(entity_type, entity_id);
CREATE INDEX idx_audit_user ON audit_log(user_id);

-- =============================================================================
-- ВЫЧИСЛЯЕМОЕ СОСТОЯНИЕ ТЕРМИНАЛА -- единственная точка правды.
-- place: последняя запись в terminal_placements
-- condition: производится из terminal_repairs / terminal_writeoffs
-- =============================================================================
CREATE VIEW terminal_current_state AS
SELECT
    t.id AS terminal_id,
    t.serial_number,
    (SELECT p.place_type FROM terminal_placements p
        WHERE p.terminal_id = t.id ORDER BY p.moved_at DESC LIMIT 1) AS current_place,
    (SELECT p.merchant_id FROM terminal_placements p
        WHERE p.terminal_id = t.id ORDER BY p.moved_at DESC LIMIT 1) AS current_merchant_id,
    CASE
        WHEN EXISTS (SELECT 1 FROM terminal_writeoffs w WHERE w.terminal_id = t.id)
            THEN 'written_off'
        WHEN EXISTS (SELECT 1 FROM terminal_repairs r
                      WHERE r.terminal_id = t.id AND r.sent_at IS NOT NULL AND r.returned_at IS NULL)
            THEN 'in_repair'
        WHEN EXISTS (SELECT 1 FROM terminal_repairs r
                      WHERE r.terminal_id = t.id AND r.returned_at IS NOT NULL AND r.firmware_at IS NULL)
            THEN 'awaiting_firmware'
        ELSE 'normal'
    END AS condition
FROM terminals t;

-- Активность мерчанта -- тоже вычисляемая, а не хранимая
CREATE VIEW merchant_current_status AS
SELECT
    m.id AS merchant_id,
    m.m_id,
    (SELECT h.status FROM merchant_status_history h
        WHERE h.merchant_id = m.id ORDER BY h.changed_at DESC LIMIT 1) AS current_status
FROM merchants m;

-- Активность привязки ID к терминалу -- тоже вычисляемая
CREATE VIEW terminal_id_current_bindings AS
SELECT b.*
FROM terminal_id_bindings b
WHERE b.bound_to IS NULL;
