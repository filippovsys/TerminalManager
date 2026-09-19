# -*- coding: utf-8 -*-
"""Показывает все edara-терминалы с их активными ID."""

import sqlite3
import config


def main():
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row

    rows = conn.execute("""
        SELECT t.id AS terminal_id, t.serial_number, t.model,
               m.m_id, m.merchant_type,
               ti.payment_id, ti.owner_label, ti.point_label,
               ti.address
        FROM terminal_id_bindings b
        JOIN terminal_ids ti ON ti.id = b.terminal_id_ref
        JOIN merchants m ON m.id = ti.merchant_id
        JOIN terminals t ON t.id = b.terminal_id
        JOIN terminal_current_state s ON s.terminal_id = t.id
        WHERE b.bound_to IS NULL AND t.is_epos = 0
          AND s.current_place = 'merchant' AND s.condition != 'written_off'
          AND m.merchant_type = 'edara'
        ORDER BY t.serial_number, ti.payment_id
    """).fetchall()

    # группируем по терминалу
    by_term = {}
    for r in rows:
        by_term.setdefault(r["terminal_id"], []).append(r)

    print(f"Всего терминалов edara: {len(by_term)}")
    print(f"Всего ID edara:          {len(rows)}")
    print()
    print("=" * 70)
    for tid, items in by_term.items():
        t = items[0]
        print(f"\nTerminal id={tid}  S/N={t['serial_number'] or '(без)'}  "
              f"model={t['model'] or '—'}  ID count={len(items)}")
        for x in items:
            print(f"    {x['payment_id']}  {x['owner_label'] or ''}  "
                  f"[{x['point_label'] or ''}]  m_id={x['m_id']}")

    # отдельно — терминалы edara БЕЗ активных ID (не должны попадать)
    print()
    print("=" * 70)
    print("Терминалы edara БЕЗ активных ID (если есть):")
    rows2 = conn.execute("""
        SELECT t.id, t.serial_number, t.model
        FROM terminals t
        JOIN terminal_current_state s ON s.terminal_id = t.id
        WHERE t.is_epos = 0 AND s.current_place = 'merchant'
          AND t.id NOT IN (
            SELECT terminal_id FROM terminal_id_bindings WHERE bound_to IS NULL
          )
    """).fetchall()
    for r in rows2:
        # посмотрим на последнего мерчанта
        m = conn.execute("""
            SELECT m.m_id, m.merchant_type
            FROM terminal_placements p
            JOIN merchants m ON m.id = p.merchant_id
            WHERE p.terminal_id = ?
            ORDER BY p.id DESC LIMIT 1
        """, (r["id"],)).fetchone()
        if m and m["merchant_type"] == "edara":
            print(f"  id={r['id']}  S/N={r['serial_number'] or '(без)'}  "
                  f"model={r['model']}  m_id={m['m_id']}")

    conn.close()


if __name__ == "__main__":
    main()