# -*- coding: utf-8 -*-
"""Диагностика: где расхождение 289 vs 287. Показывает дубликаты ID и S/N."""

import sqlite3
import config


def main():
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row

    print("=" * 62)
    print("1. Дубликаты payment_id в terminal_ids")
    print("=" * 62)
    n = 0
    for r in conn.execute("""
        SELECT payment_id, COUNT(*) c
        FROM terminal_ids GROUP BY payment_id HAVING c > 1
        ORDER BY c DESC
    """):
        n += 1
        print(f"\npayment_id = {r['payment_id']}  ({r['c']} записей):")
        for x in conn.execute("""
            SELECT ti.id, ti.merchant_id, ti.owner_label, m.merchant_type, m.m_id
            FROM terminal_ids ti
            LEFT JOIN merchants m ON m.id = ti.merchant_id
            WHERE ti.payment_id = ?
            ORDER BY ti.id
        """, (r['payment_id'],)):
            b = conn.execute("""
                SELECT b.id, b.terminal_id, b.bound_to, t.serial_number
                FROM terminal_id_bindings b
                JOIN terminals t ON t.id = b.terminal_id
                WHERE b.terminal_id_ref = ?
                ORDER BY b.id DESC
            """, (x['id'],)).fetchall()
            print(f"  terminal_ids.id={x['id']}  m_id={x['m_id']}  "
                  f"type={x['merchant_type']}  owner={x['owner_label']}")
            for bb in b:
                st = "активна" if bb['bound_to'] is None else f"закрыта {bb['bound_to']}"
                print(f"    binding id={bb['id']} -> terminal_id={bb['terminal_id']} "
                      f"({bb['serial_number']})  {st}")
    print(f"\nВсего payment_id с дубликатами: {n}")

    print()
    print("=" * 62)
    print("2. Дубликаты serial_number в terminals")
    print("=" * 62)
    n = 0
    for r in conn.execute("""
        SELECT serial_number, COUNT(*) c
        FROM terminals WHERE serial_number IS NOT NULL
        GROUP BY serial_number HAVING c > 1
        ORDER BY c DESC
    """):
        n += 1
        print(f"\nS/N = {r['serial_number']}  ({r['c']} записей):")
        for x in conn.execute(
            "SELECT id, model, is_epos FROM terminals WHERE serial_number = ?",
            (r['serial_number'],),
        ):
            print(f"  id={x['id']}  model={x['model']}  is_epos={x['is_epos']}")
    print(f"\nВсего S/N с дубликатами: {n}")

    print()
    print("=" * 62)
    print("3. Пары (payment_id, S/N) с несколькими АКТИВНЫМИ привязками")
    print("=" * 62)
    n = 0
    for r in conn.execute("""
        SELECT ti.payment_id, t.serial_number, COUNT(*) c
        FROM terminal_id_bindings b
        JOIN terminal_ids ti ON ti.id = b.terminal_id_ref
        JOIN terminals t ON t.id = b.terminal_id
        WHERE b.bound_to IS NULL
        GROUP BY ti.payment_id, t.serial_number
        HAVING c > 1
    """):
        n += 1
        print(f"  ({r['payment_id']}, {r['serial_number']})  x{r['c']}")
    print(f"\nВсего таких пар: {n}")

    conn.close()


if __name__ == "__main__":
    main()