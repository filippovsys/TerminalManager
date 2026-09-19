# -*- coding: utf-8 -*-
"""
Схлопывает дубликаты мерчантов из-за разных форматов m_id
("82" vs "82.0", "007831" vs "7831").

Алгоритм:
  1. Находит группы, где m_id нормализуется в одно значение.
  2. В группе выбирает «каноничный» merchants.id -- тот, у которого
     больше всего terminal_ids (при равенстве -- минимальный id).
  3. Все terminal_ids и другие ссылки переводит на каноничный.
  4. Удаляет остальные записи.

Запуск:
    python clean_dup_merchants.py
"""

import os
import shutil
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime

import config


def normalize_m_id(s):
    if s is None:
        return None
    s = str(s).strip()
    if s.endswith(".0"):
        s = s[:-2]
    if s.isdigit():
        t = s.lstrip("0")
        return t if t else "0"
    return s


def main():
    if not os.path.exists(config.DB_PATH):
        print(f"База не найдена: {config.DB_PATH}")
        return 1

    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row

    rows = conn.execute("SELECT id, m_id FROM merchants ORDER BY id").fetchall()
    groups = defaultdict(list)
    for r in rows:
        groups[normalize_m_id(r["m_id"])].append(r["id"])

    dup_groups = {k: ids for k, ids in groups.items() if len(ids) > 1}
    if not dup_groups:
        print("Дубликатов не найдено.")
        conn.close()
        return 0

    print(f"Найдено групп дубликатов: {len(dup_groups)}")
    print()

    backup = config.DB_PATH + ".backup-dupclean-" + datetime.now().strftime("%Y%m%d-%H%M%S")
    shutil.copy2(config.DB_PATH, backup)
    print(f"Резервная копия: {backup}")
    print()

    merge_map = {}

    for norm, ids in sorted(dup_groups.items()):
        counts = {}
        for mid in ids:
            cnt = conn.execute(
                "SELECT COUNT(*) c FROM terminal_ids WHERE merchant_id = ?", (mid,)
            ).fetchone()["c"]
            counts[mid] = cnt
        canonical = sorted(ids, key=lambda i: (-counts[i], i))[0]
        others = [i for i in ids if i != canonical]
        print(f"  m_id нормализованный = '{norm}':")
        for mid in ids:
            m = conn.execute("SELECT m_id FROM merchants WHERE id = ?", (mid,)).fetchone()
            mark = " <- оставить" if mid == canonical else ""
            print(f"    id={mid:<5} m_id='{m['m_id']}' терминалов={counts[mid]}{mark}")
        for other in others:
            merge_map[other] = canonical

    print()
    print(f"Будет схлопнуто мерчантов: {len(merge_map)}")
    ans = input("Продолжить? (y/n): ").strip().lower()
    if ans != "y":
        print("Отменено.")
        conn.close()
        return 0

    for old, new in merge_map.items():
        conn.execute("UPDATE terminal_ids SET merchant_id = ? WHERE merchant_id = ?", (new, old))
        conn.execute("UPDATE merchant_status_history SET merchant_id = ? WHERE merchant_id = ?", (new, old))
        conn.execute("UPDATE merchant_contact_history SET merchant_id = ? WHERE merchant_id = ?", (new, old))
        conn.execute("UPDATE terminal_placements SET merchant_id = ? WHERE merchant_id = ?", (new, old))
        conn.execute("DELETE FROM merchants WHERE id = ?", (old,))

    conn.commit()
    print(f"Схлопнуто мерчантов: {len(merge_map)}")

    # Итог
    rows2 = conn.execute("""
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
    print()
    print("Сводка после схлопывания:")
    tt, ti_sum = 0, 0
    for r in rows2:
        print(f"  {r['merchant_type']}: {r['Terms']} терм / {r['IDs']} ID")
        tt += r["Terms"]; ti_sum += r["IDs"]
    print(f"  ИТОГО: {tt} терм / {ti_sum} ID")

    conn.close()
    print("\nГотово.")
    return 0


if __name__ == "__main__":
    sys.exit(main())