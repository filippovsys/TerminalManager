# -*- coding: utf-8 -*-
"""
Схлопывает дубликаты в terminal_ids (по payment_id).

Логика:
  1. Для каждого payment_id с несколькими записями terminal_ids:
     - выбирает каноничную (у которой больше активных привязок;
       при равенстве -- минимальный id);
     - переводит все привязки на каноничную;
     - удаляет остальные.
  2. Убирает дубли активных привязок к одному терминалу
     (одна пара payment_id + terminal_id = одна активная привязка,
     остальные закрываются).

Запуск:
    python dedup_terminal_ids.py
"""

import os
import shutil
import sqlite3
import sys
from datetime import datetime

import config


def active_count(conn, tid):
    return conn.execute(
        "SELECT COUNT(*) c FROM terminal_id_bindings "
        "WHERE terminal_id_ref = ? AND bound_to IS NULL",
        (tid,),
    ).fetchone()["c"]


def main():
    if not os.path.exists(config.DB_PATH):
        print(f"База не найдена: {config.DB_PATH}")
        return 1

    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row

    dups = conn.execute("""
        SELECT payment_id, COUNT(*) c
        FROM terminal_ids
        GROUP BY payment_id HAVING c > 1
        ORDER BY payment_id
    """).fetchall()
    print(f"Групп дубликатов payment_id: {len(dups)}")

    if not dups:
        print("Нечего схлопывать.")
        conn.close()
        return 0

    backup = config.DB_PATH + ".backup-dedup-" + datetime.now().strftime("%Y%m%d-%H%M%S")
    shutil.copy2(config.DB_PATH, backup)
    print(f"Резервная копия: {backup}")
    print()

    total_merged = 0
    total_closed = 0

    for d in dups:
        pid = d["payment_id"]
        ids = [r["id"] for r in conn.execute(
            "SELECT id FROM terminal_ids WHERE payment_id = ? ORDER BY id", (pid,)
        ).fetchall()]
        canonical = sorted(ids, key=lambda i: (-active_count(conn, i), i))[0]
        others = [i for i in ids if i != canonical]

        for o in others:
            conn.execute(
                "UPDATE terminal_id_bindings SET terminal_id_ref = ? "
                "WHERE terminal_id_ref = ?",
                (canonical, o),
            )
            conn.execute("DELETE FROM terminal_ids WHERE id = ?", (o,))
            total_merged += 1

        # теперь у canonical может быть >1 активная привязка к одному terminal_id
        rows = conn.execute("""
            SELECT id, terminal_id FROM terminal_id_bindings
            WHERE terminal_id_ref = ? AND bound_to IS NULL
            ORDER BY id
        """, (canonical,)).fetchall()
        seen = set()
        for r in rows:
            key = r["terminal_id"]
            if key in seen:
                conn.execute(
                    "UPDATE terminal_id_bindings SET bound_to = datetime('now') "
                    "WHERE id = ?",
                    (r["id"],),
                )
                total_closed += 1
            else:
                seen.add(key)

    conn.commit()
    print(f"Удалено дубликатов terminal_ids:  {total_merged}")
    print(f"Закрыто дублей активных привязок: {total_closed}")
    print()

    # Финальная сводка
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
    print("Сводка:")
    tt, ti_sum = 0, 0
    for r in rows:
        print(f"  {r['merchant_type']}: {r['Terms']} терм / {r['IDs']} ID")
        tt += r["Terms"]; ti_sum += r["IDs"]
    print(f"  ИТОГО: {tt} терм / {ti_sum} ID")

    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())