# -*- coding: utf-8 -*-
"""
Синхронизация активных привязок с листом TERM.

Корректно обрабатывает объединённые ячейки SAN (столбец A):
  * при появлении нового SAN -- S/N сбрасывается;
  * пустые строки остаются частью той же группы.

Привязку ищет по паре (терминал по S/N + payment_id), что надёжно
работает при повторяющихся ID.
"""

import os
import shutil
import sqlite3
import sys
from datetime import datetime

import config


def read_term_pairs(path):
    """Возвращает список (payment_id, sn) с учётом SAN-групп."""
    try:
        import openpyxl
    except ImportError:
        print("Нужна библиотека openpyxl: pip install openpyxl")
        sys.exit(1)

    wb = openpyxl.load_workbook(path, data_only=True)
    if "TERM" not in wb.sheetnames:
        print(f"Нет листа TERM. Есть: {wb.sheetnames}")
        sys.exit(1)
    ws = wb["TERM"]

    pairs = []
    current_sn = None
    for row in ws.iter_rows(min_row=2, values_only=True):
        if len(row) < 6:
            continue
        # Новый SAN = новый физический терминал -> сбрасываем S/N
        if row[0] is not None:
            current_sn = str(row[5]).strip() if row[5] is not None else None
        payment_id = row[1]
        if payment_id is None:
            continue
        pid = str(payment_id).strip()
        pairs.append((pid, current_sn))
    return pairs


def find_terminal_by_sn(conn, sn):
    if sn is None:
        return None
    row = conn.execute(
        "SELECT id FROM terminals WHERE serial_number = ?", (sn,)
    ).fetchone()
    return row["id"] if row else None


def find_binding(conn, terminal_id, payment_id):
    """Ищет привязку между данным терминалом и terminal_ids с данным payment_id.
    Возвращает dict(id, terminal_id_ref, bound_to) или None."""
    row = conn.execute("""
        SELECT b.id, b.terminal_id_ref, b.bound_to
        FROM terminal_id_bindings b
        JOIN terminal_ids ti ON ti.id = b.terminal_id_ref
        WHERE b.terminal_id = ? AND ti.payment_id = ?
        ORDER BY b.id DESC LIMIT 1
    """, (terminal_id, payment_id)).fetchone()
    return dict(row) if row else None


def find_terminal_id_ref(conn, payment_id):
    row = conn.execute(
        "SELECT id FROM terminal_ids WHERE payment_id = ? ORDER BY id LIMIT 1",
        (payment_id,),
    ).fetchone()
    return row["id"] if row else None


def main():
    if len(sys.argv) < 2:
        print('Использование: python fix_sync_term.py "СВЕДЕНИЯ IMPORT.xlsx"')
        return 1
    xlsx_path = sys.argv[1]
    if not os.path.exists(xlsx_path):
        print(f"Файл не найден: {xlsx_path}")
        return 1

    print("Читаю лист TERM...")
    term_pairs = read_term_pairs(xlsx_path)
    term_set = set(term_pairs)
    print(f"  Уникальных пар (ID, S/N) в TERM: {len(term_set)}")

    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row

    # --- 1. Что надо ВОССТАНОВИТЬ ---
    print("\nИщу, что нужно ВОССТАНОВИТЬ...")
    missing = []       # (payment_id, sn, terminal_id, binding_id, mode)
    not_found_term = []
    not_found_tid = []

    for pid, sn in term_set:
        terminal_id = find_terminal_by_sn(conn, sn)
        if terminal_id is None:
            not_found_term.append((pid, sn))
            continue

        binding = find_binding(conn, terminal_id, pid)
        if binding is None:
            # Нет ни одной привязки -- надо создать
            tid_ref = find_terminal_id_ref(conn, pid)
            if tid_ref is None:
                not_found_tid.append(pid)
                continue
            missing.append((pid, sn, terminal_id, None, tid_ref, "create"))
        elif binding["bound_to"] is not None:
            missing.append((pid, sn, terminal_id, binding["id"], None, "reactivate"))
        # иначе -- уже активна, ничего не делаем

    print(f"  Требуют восстановления: {len(missing)}")
    if not_found_term:
        print(f"  Не найден терминал по S/N: {len(not_found_term)}")
        for pid, sn in not_found_term[:5]:
            print(f"    ID={pid} S/N={sn}")
    if not_found_tid:
        print(f"  Не найден terminal_ids по ID: {len(not_found_tid)}")
        for pid in not_found_tid[:5]:
            print(f"    ID={pid}")

    # --- 2. Что надо ЗАКРЫТЬ ---
    print("\nИщу, что нужно ЗАКРЫТЬ...")
    extra = []
    for r in conn.execute("""
        SELECT b.id AS bid, ti.payment_id, t.serial_number
        FROM terminal_id_bindings b
        JOIN terminal_ids ti ON ti.id = b.terminal_id_ref
        JOIN terminals t ON t.id = b.terminal_id
        WHERE b.bound_to IS NULL
    """).fetchall():
        pid = str(r["payment_id"])
        sn = str(r["serial_number"]).strip() if r["serial_number"] is not None else None
        if (pid, sn) not in term_set:
            extra.append((r["bid"], pid, sn))
    print(f"  Требуют закрытия: {len(extra)}")
    for bid, pid, sn in extra[:10]:
        print(f"    ID={pid} S/N={sn}")

    # --- 3. Терминалы "у клиента" без активных ID (после восстановления) ---
    print("\nИщу терминалы для перемещения на склад...")
    terminals_with_restore = set(m[2] for m in missing)
    orphans = conn.execute("""
        SELECT t.id, t.serial_number
        FROM terminals t
        JOIN terminal_current_state s ON s.terminal_id = t.id
        WHERE t.is_epos = 0
          AND s.current_place = 'merchant'
          AND t.id NOT IN (
              SELECT terminal_id FROM terminal_id_bindings WHERE bound_to IS NULL
          )
    """).fetchall()
    orphans_final = [o for o in orphans if o["id"] not in terminals_with_restore]
    print(f"  Будет перемещено на склад: {len(orphans_final)}")
    for o in orphans_final[:10]:
        print(f"    S/N={o['serial_number'] or '(без)'}")

    # --- Подтверждение ---
    print()
    print("=" * 62)
    print(f"ВОССТАНОВИТЬ:   {len(missing)} привязок")
    print(f"ЗАКРЫТЬ:        {len(extra)} привязок")
    print(f"НА СКЛАД:       {len(orphans_final)} терминалов")
    print("=" * 62)
    ans = input("Применить? (y/n): ").strip().lower()
    if ans != "y":
        print("Отменено.")
        conn.close()
        return 0

    backup = config.DB_PATH + ".backup-sync-" + datetime.now().strftime("%Y%m%d-%H%M%S")
    shutil.copy2(config.DB_PATH, backup)
    print(f"\nРезервная копия: {backup}")

    for pid, sn, terminal_id, binding_id, tid_ref, mode in missing:
        if mode == "reactivate":
            conn.execute(
                "UPDATE terminal_id_bindings SET bound_to = NULL WHERE id = ?",
                (binding_id,),
            )
        else:
            conn.execute(
                "INSERT INTO terminal_id_bindings (terminal_id, terminal_id_ref) VALUES (?, ?)",
                (terminal_id, tid_ref),
            )
    print(f"  Восстановлено: {len(missing)}")

    if extra:
        conn.executemany(
            "UPDATE terminal_id_bindings SET bound_to = datetime('now') WHERE id = ?",
            [(bid,) for bid, _, _ in extra],
        )
    print(f"  Закрыто: {len(extra)}")

    for o in orphans_final:
        conn.execute(
            "INSERT INTO terminal_placements (terminal_id, place_type, comment) "
            "VALUES (?, 'warehouse', 'синхронизация: нет активных ID')",
            (o["id"],),
        )
    print(f"  Перемещено на склад: {len(orphans_final)}")

    conn.commit()

    # --- Итог ---
    rows = conn.execute("""
        SELECT m.merchant_type, COUNT(*) IDs, COUNT(DISTINCT b.terminal_id) Terms
        FROM terminal_id_bindings b
        JOIN terminal_ids ti ON ti.id = b.terminal_id_ref
        JOIN merchants m ON m.id = ti.merchant_id
        JOIN terminals t ON t.id = b.terminal_id
        JOIN terminal_current_state s ON s.terminal_id = b.terminal_id
        WHERE b.bound_to IS NULL AND t.is_epos = 0
          AND s.current_place = 'merchant' AND s.condition != 'written_off'
        GROUP BY m.merchant_type
    """).fetchall()
    print("\nИтоговая сводка:")
    tt, ti_sum = 0, 0
    for r in rows:
        print(f"  {r['merchant_type']}: {r['Terms']} терм / {r['IDs']} ID")
        tt += r["Terms"]; ti_sum += r["IDs"]
    print(f"  ИТОГО: {tt} терм / {ti_sum} ID")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())