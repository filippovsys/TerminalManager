# -*- coding: utf-8 -*-
"""Диагностика: показывает состояние активных привязок и терминалов."""

import sqlite3
import config


def main():
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row

    print("=" * 62)
    print("ДИАГНОСТИКА БАЗЫ")
    print("=" * 62)

    n_terms = conn.execute("SELECT COUNT(*) c FROM terminals").fetchone()["c"]
    n_epos = conn.execute("SELECT COUNT(*) c FROM terminals WHERE is_epos = 1").fetchone()["c"]
    print(f"Всего терминалов:        {n_terms}")
    print(f"  из них E-POS:          {n_epos}")
    print(f"  обычных:               {n_terms - n_epos}")

    n_active_bind = conn.execute(
        "SELECT COUNT(*) c FROM terminal_id_bindings WHERE bound_to IS NULL"
    ).fetchone()["c"]
    n_with_active = conn.execute(
        "SELECT COUNT(DISTINCT terminal_id) c FROM terminal_id_bindings WHERE bound_to IS NULL"
    ).fetchone()["c"]
    print(f"Активных привязок:       {n_active_bind}")
    print(f"Терминалов с активом:    {n_with_active}")
    print(f"Терминалов БЕЗ активных: {n_terms - n_with_active}")

    print()
    print("--- По типу клиента (то, что видно во вкладке «Активные») ---")
    rows = conn.execute("""
        SELECT m.merchant_type,
               COUNT(*) IDs,
               COUNT(DISTINCT b.terminal_id) Terms
        FROM terminal_id_bindings b
        JOIN terminal_ids ti ON ti.id = b.terminal_id_ref
        JOIN merchants m ON m.id = ti.merchant_id
        JOIN terminals t ON t.id = b.terminal_id
        JOIN terminal_current_state s ON s.terminal_id = b.terminal_id
        WHERE b.bound_to IS NULL AND t.is_epos = 0
          AND s.current_place = 'merchant' AND s.condition != 'written_off'
        GROUP BY m.merchant_type
    """).fetchall()
    for r in rows:
        print(f"  {r['merchant_type']}: {r['Terms']} терм / {r['IDs']} ID")

    print()
    print("--- Терминалы БЕЗ активных привязок (первые 20) ---")
    rows = conn.execute("""
        SELECT t.id, t.serial_number, t.model, t.is_epos,
               s.current_place, s.condition
        FROM terminals t
        JOIN terminal_current_state s ON s.terminal_id = t.id
        WHERE t.id NOT IN (SELECT terminal_id FROM terminal_id_bindings WHERE bound_to IS NULL)
        ORDER BY t.serial_number
    """).fetchall()
    print(f"  Всего: {len(rows)}")
    for r in rows[:20]:
        print(f"    ID={r['id']} S/N={r['serial_number'] or '(без)'} "
              f"model={r['model'] or '—'} epos={r['is_epos']} "
              f"place={r['current_place']} cond={r['condition']}")

    print()
    print("--- Терминалы с активными привязками, но НЕ у клиента ---")
    rows = conn.execute("""
        SELECT t.serial_number, s.current_place, s.condition, COUNT(*) c
        FROM terminal_id_bindings b
        JOIN terminals t ON t.id = b.terminal_id
        JOIN terminal_current_state s ON s.terminal_id = t.id
        WHERE b.bound_to IS NULL
          AND (s.current_place != 'merchant' OR s.condition = 'written_off')
        GROUP BY t.id
        ORDER BY c DESC
    """).fetchall()
    print(f"  Всего терминалов: {len(rows)}")
    for r in rows[:20]:
        print(f"    S/N={r['serial_number'] or '(без)'} place={r['current_place']} "
              f"cond={r['condition']} ({r['c']} ID)")
    if len(rows) > 20:
        print(f"    ... ещё {len(rows) - 20}")

    conn.close()


if __name__ == "__main__":
    main()