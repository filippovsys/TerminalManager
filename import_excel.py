# -*- coding: utf-8 -*-
"""
Импорт "СВЕДЕНИЯ о терминалах г.Балканабат.xlsx" в новую БД (db_schema.sql).

ВАЖНО (исправлено после проверки реальных чисел с пользователем):
Один физический терминал в Excel -- это не "уникальный S/N", а ГРУППА строк
под одним значением столбца "№" (A), где A стоит только на первой строке
группы, а остальные строки этой же группы (другие ID того же терминала)
идут с пустым A (объединённые ячейки). Есть терминалы вообще без S/N --
раньше они молча терялись при группировке по S/N, теперь группировка идёт
по A, и такие терминалы тоже создаются (с serial_number = NULL).

Прочие решения (см. обсуждение):
  - Клиентам без известного типа (только в листе "ЗАКРЫТЫЕ", где нет
    колонки "Тип") тип проставляется как 'telekeci' по умолчанию.
  - Строки без M/id вообще не импортируются как платёжные ID, но сам
    физический терминал (группа) всё равно создаётся, если он из TERM
    (это действующий терминал независимо от того, привязан ли к клиенту
    каждый его ID).
  - Столбец "Состояние" не используется.
"""

import os
import sqlite3
from collections import defaultdict

import openpyxl

SRC_XLSX = "/mnt/user-data/uploads/СВЕДЕНИЯ_о_терминалах_г_Балканабат.xlsx"
SCHEMA_SQL = "/home/claude/db_schema.sql"
DB_PATH = "/home/claude/terminals.db"

TYPE_MAP = {"telekeçi": "telekeci", "edara": "edara", "bank": "bank"}
DEFAULT_MERCHANT_TYPE = "telekeci"


def load_groups(ws, has_type_col, sheet_name):
    """Возвращает список групп; каждая группа -- один физический терминал:
    список строк-словарей (одна строка = один платёжный ID)."""
    rows = list(ws.iter_rows(min_row=2, values_only=True))
    style_rows = list(ws.iter_rows(min_row=2))  # для доступа к заливке ячейки модели

    groups = []
    current_group = None
    for r, sr in zip(rows, style_rows):
        if r[1] is None and r[5] is None and r[0] is None:
            continue  # полностью пустая строка
        if r[0] is not None or current_group is None:
            current_group = []
            groups.append(current_group)

        cell = sr[4]  # колонка E -- модель/тип терминала
        fill = cell.fill
        is_client_owned = bool(
            fill and fill.fgColor and fill.fgColor.rgb not in (None, "00000000")
        )

        current_group.append({
            "id": r[1],
            "transit": r[2],
            "m_id": r[3],
            "model": r[4],
            "sn": str(r[5]).strip() if r[5] is not None else None,
            "sim": str(r[6]).strip() if r[6] is not None else None,
            "ip": str(r[7]).strip() if r[7] is not None else None,
            "owner_type": (r[8] if has_type_col else None),
            "owner_label": r[9],
            "point_label": r[10],
            "client_owned": is_client_owned,
            "sheet": sheet_name,
        })
    return groups


def main():
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

    con = sqlite3.connect(DB_PATH)
    with open(SCHEMA_SQL, encoding="utf-8") as f:
        con.executescript(f.read())
    cur = con.cursor()

    wb = openpyxl.load_workbook(SRC_XLSX, data_only=True)
    term_groups = load_groups(wb["TERM"], has_type_col=True, sheet_name="TERM")
    closed_groups = load_groups(wb["ЗАКРЫТЫЕ"], has_type_col=False, sheet_name="ЗАКРЫТЫЕ")

    stats = defaultdict(int)
    review_items = []

    # ---------------------------------------------------------------
    # 1. Мерчанты: один по каждому m_id, встреченному хоть в одной строке
    #    (среди строк, где m_id вообще указан).
    # ---------------------------------------------------------------
    merchant_type_by_mid = {}
    for grp in term_groups:
        for r in grp:
            if r["m_id"] is not None and r["owner_type"]:
                merchant_type_by_mid.setdefault(
                    r["m_id"], TYPE_MAP.get(str(r["owner_type"]).strip().lower())
                )

    all_mids = set()
    for grp in term_groups + closed_groups:
        for r in grp:
            if r["m_id"] is not None:
                all_mids.add(r["m_id"])

    merchant_db_id = {}
    for m_id in sorted(all_mids, key=str):
        mtype = merchant_type_by_mid.get(m_id) or DEFAULT_MERCHANT_TYPE
        is_guessed = m_id not in merchant_type_by_mid
        cur.execute(
            "INSERT INTO merchants (m_id, merchant_type, note) VALUES (?, ?, ?)",
            (str(m_id), mtype, "тип определён по умолчанию (только в ЗАКРЫТЫЕ)" if is_guessed else None),
        )
        merchant_db_id[m_id] = cur.lastrowid
        stats["merchants_created"] += 1
        if is_guessed:
            stats["merchants_default_type"] += 1

    # ---------------------------------------------------------------
    # 2. Физические терминалы -- по группам. Группы из TERM создаются
    #    всегда (это действующий терминал). Группы из ЗАКРЫТЫЕ создаются,
    #    только если их S/N не совпал ни с одной группой из TERM --
    #    иначе это тот же самый терминал, переоткрытый повторно.
    # ---------------------------------------------------------------
    terminal_db_id_by_sn = {}   # для терминалов С серийным номером
    term_group_by_sn = {}

    def base_attrs(grp):
        base = grp[0]
        connection_type = None
        if base["sim"]:
            connection_type = "ethernet" if base["sim"].lower() == "ethernet" else "sim"
        ownership = "client" if any(x["client_owned"] for x in grp) else "bank"
        return base["model"], ownership, connection_type

    def insert_connections(grp, terminal_id):
        existing = {
            (row[0], row[1])
            for row in cur.execute(
                "SELECT sim_number, ip_address FROM connection_history WHERE terminal_id = ?",
                (terminal_id,),
            ).fetchall()
        }
        seen = set(existing)
        for x in grp:
            sim_val = None if (x["sim"] and x["sim"].lower() == "ethernet") else x["sim"]
            key = (sim_val, x["ip"])
            if key in seen or (sim_val is None and x["ip"] is None):
                continue
            seen.add(key)
            cur.execute(
                "INSERT INTO connection_history (terminal_id, sim_number, ip_address) VALUES (?, ?, ?)",
                (terminal_id, sim_val, x["ip"]),
            )

    def insert_terminal_ids(grp, terminal_id):
        for r in grp:
            if r["id"] is None:
                continue
            if r["m_id"] is None:
                stats["ids_skipped_no_merchant"] += 1
                continue
            cur.execute(
                "INSERT INTO terminal_ids (payment_id, transit_account, merchant_id, owner_label, point_label) "
                "VALUES (?, ?, ?, ?, ?)",
                (str(r["id"]), r["transit"], merchant_db_id[r["m_id"]], r["owner_label"], r["point_label"]),
            )
            tid_db_id = cur.lastrowid
            stats["terminal_ids_created"] += 1
            cur.execute(
                "INSERT INTO terminal_id_bindings (terminal_id, terminal_id_ref) VALUES (?, ?)",
                (terminal_id, tid_db_id),
            )

    # -- 2a. Терминалы из TERM: создаются все, независимо от S/N/M-id --
    for grp in term_groups:
        sn = next((r["sn"] for r in grp if r["sn"]), None)
        model, ownership, connection_type = base_attrs(grp)
        cur.execute(
            "INSERT INTO terminals (serial_number, model, ownership, connection_type) VALUES (?, ?, ?, ?)",
            (sn, model, ownership, connection_type),
        )
        terminal_id = cur.lastrowid
        stats["terminals_created_from_term"] += 1
        if sn:
            terminal_db_id_by_sn[sn] = terminal_id
            term_group_by_sn[sn] = grp

        insert_connections(grp, terminal_id)

        m_id = next((r["m_id"] for r in grp if r["m_id"] is not None), None)
        if m_id is not None:
            cur.execute(
                "INSERT INTO terminal_placements (terminal_id, place_type, merchant_id, comment) "
                "VALUES (?, 'merchant', ?, 'импорт из TERM')",
                (terminal_id, merchant_db_id[m_id]),
            )
        else:
            cur.execute(
                "INSERT INTO terminal_placements (terminal_id, place_type, comment) "
                "VALUES (?, 'warehouse', 'импорт из TERM: ни у одного ID нет M/id')",
                (terminal_id,),
            )
            review_items.append(("TERM", sn, None, "ни у одного ID в группе нет M/id"))

        insert_terminal_ids(grp, terminal_id)

    # -- 2b. Терминалы из ЗАКРЫТЫЕ. ВАЖНО: один и тот же S/N здесь часто
    #    встречается в НЕСКОЛЬКИХ разных группах (терминал "бегал по рукам"
    #    между клиентами) -- 73 таких S/N в реальных данных. Сначала
    #    объединяем все строки одного S/N из ЗАКРЫТЫЕ вместе, и только
    #    потом решаем: это продолжение терминала из TERM, или отдельный
    #    (уже полностью закрытый) терминал.
    closed_by_sn = defaultdict(list)
    closed_no_sn_groups = []
    for grp in closed_groups:
        sn = next((r["sn"] for r in grp if r["sn"]), None)
        if sn:
            closed_by_sn[sn].extend(grp)
        else:
            closed_no_sn_groups.append(grp)

    def process_closed_bundle(sn, rows_bundle):
        if sn and sn in terminal_db_id_by_sn:
            terminal_id = terminal_db_id_by_sn[sn]
            stats["closed_merged_into_term"] += 1
            insert_connections(rows_bundle, terminal_id)
            insert_terminal_ids(rows_bundle, terminal_id)
            return

        model, ownership, connection_type = base_attrs(rows_bundle)
        cur.execute(
            "INSERT INTO terminals (serial_number, model, ownership, connection_type) VALUES (?, ?, ?, ?)",
            (sn, model, ownership, connection_type),
        )
        terminal_id = cur.lastrowid
        stats["terminals_created_from_closed_only"] += 1

        insert_connections(rows_bundle, terminal_id)
        cur.execute(
            "INSERT INTO terminal_placements (terminal_id, place_type, comment) "
            "VALUES (?, 'warehouse', 'импорт: терминал встречен только в ЗАКРЫТЫЕ -- текущее место неизвестно, для истории')",
            (terminal_id,),
        )
        review_items.append(("ЗАКРЫТЫЕ", sn, None, "терминал только в ЗАКРЫТЫЕ, текущее место неизвестно"))
        insert_terminal_ids(rows_bundle, terminal_id)

    for sn, rows_bundle in closed_by_sn.items():
        process_closed_bundle(sn, rows_bundle)

    for grp in closed_no_sn_groups:
        process_closed_bundle(None, grp)

    for sheet, sn, pid, note in review_items:
        cur.execute(
            "INSERT INTO import_review_queue (sheet_name, serial_number, payment_id, raw_status_text, resolution_note) "
            "VALUES (?, ?, ?, '', ?)",
            (sheet, sn, pid, note),
        )

    con.commit()

    # ---------------------------------------------------------------
    # Отчёт
    # ---------------------------------------------------------------
    print("=" * 70)
    print(f"ИМПОРТ ЗАВЕРШЁН -> {DB_PATH}")
    print("=" * 70)
    print(f"Групп(терминалов) в TERM:                 {len(term_groups)}")
    print(f"Групп(терминалов) в ЗАКРЫТЫЕ:              {len(closed_groups)}")
    print(f"Создано мерчантов:                         {stats['merchants_created']}")
    print(f"  из них тип по умолчанию (telekeci):      {stats['merchants_default_type']}")
    print(f"Создано терминалов из TERM:                {stats['terminals_created_from_term']}")
    print(f"Создано терминалов только из ЗАКРЫТЫЕ:     {stats['terminals_created_from_closed_only']}")
    print(f"ЗАКРЫТЫЕ-групп, объединённых с TERM по S/N: {stats['closed_merged_into_term']}")
    print(f"Всего терминалов в БД:                      "
          f"{stats['terminals_created_from_term'] + stats['terminals_created_from_closed_only']}")
    print(f"Создано платёжных ID:                       {stats['terminal_ids_created']}")
    print(f"  ID пропущено (нет M/id):                  {stats['ids_skipped_no_merchant']}")

    cur.execute("SELECT COUNT(*) FROM import_review_queue")
    print()
    print(f"Строк в очереди на ручную проверку: {cur.fetchone()[0]}")

    cur.execute("SELECT current_place, COUNT(*) FROM terminal_current_state GROUP BY current_place")
    print()
    print("Текущее место терминалов:")
    for place, cnt in cur.fetchall():
        print(f"    {place:12s}: {cnt}")

    cur.execute(
        """
        SELECT m.merchant_type, COUNT(DISTINCT p.terminal_id)
        FROM terminal_placements p
        JOIN merchants m ON m.id = p.merchant_id
        WHERE p.id IN (SELECT MAX(id) FROM terminal_placements GROUP BY terminal_id)
        GROUP BY m.merchant_type
        """
    )
    print()
    print("Действующие терминалы (сейчас у мерчанта) по типу клиента:")
    for t, cnt in cur.fetchall():
        print(f"    {t or 'NULL':12s}: {cnt}")

    con.close()


if __name__ == "__main__":
    main()
