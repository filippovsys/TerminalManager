# -*- coding: utf-8 -*-
"""
Объединяет терминал S/N=WL12345681 в S/N=WL12345680.
Переносит все привязки и отправляет "пустой" терминал на склад.

Это нужно, чтобы цифры совпали с Excel, где SAN 184 = один физический
терминал (см. ручной подсчёт -- 57 в edara).
"""

import os
import shutil
import sqlite3
import sys
from datetime import datetime

import config


def main():
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row

    src = conn.execute("SELECT id FROM terminals WHERE serial_number = ?", ("WL12345681",)).fetchone()
    dst = conn.execute("SELECT id FROM terminals WHERE serial_number = ?", ("WL12345680",)).fetchone()
    if src is None or dst is None:
        print("Один из терминалов не найден. Возможно, уже объединены.")
        conn.close()
        return 0

    src_id, dst_id = src["id"], dst["id"]

    # Проверяем активные привязки на src
    rows = conn.execute("""
        SELECT b.id, ti.payment_id
        FROM terminal_id_bindings b
        JOIN terminal_ids ti ON ti.id = b.terminal_id_ref
        WHERE b.terminal_id = ? AND b.bound_to IS NULL
    """, (src_id,)).fetchall()
    print(f"Терминал src (WL12345681, id={src_id}): {len(rows)} активных привязок")
    for r in rows:
        print(f"    payment_id = {r['payment_id']}")
    print(f"Терминал dst (WL12345680, id={dst_id}) -- цель переноса.")

    if not rows:
        print("Нечего переносить. Возможно, уже объединены.")
        conn.close()
        return 0

    backup = config.DB_PATH + ".backup-merge-" + datetime.now().strftime("%Y%m%d-%H%M%S")
    shutil.copy2(config.DB_PATH, backup)
    print(f"\nРезервная копия: {backup}")

    ans = input("\nПродолжить? (y/n): ").strip().lower()
    if ans != "y":
        print("Отменено.")
        conn.close()
        return 0

    # Перенос привязок: обновляем terminal_id на dst
    conn.execute("""
        UPDATE terminal_id_bindings SET terminal_id = ?
        WHERE terminal_id = ? AND bound_to IS NULL
    """, (dst_id, src_id))
    print(f"Перенесено привязок: {conn.total_changes}")

    # Src-терминал -> на склад
    conn.execute("""
        INSERT INTO terminal_placements (terminal_id, place_type, comment)
        VALUES (?, 'warehouse', 'объединён с WL12345680 (см. SAN 184 в Excel)')
    """, (src_id,))
    conn.commit()

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
    print("\nСводка:")
    tt, ti_sum = 0, 0
    for r in rows2:
        print(f"  {r['merchant_type']}: {r['Terms']} терм / {r['IDs']} ID")
        tt += r["Terms"]; ti_sum += r["IDs"]
    print(f"  ИТОГО: {tt} терм / {ti_sum} ID")

    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())