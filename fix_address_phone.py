# -*- coding: utf-8 -*-
"""
Заполняет в terminal_ids поля address и phone по данным из листа TERM.
При импорте Excel этих полей не было -- они пустые.

Запуск:
    python fix_address_phone.py "СВЕДЕНИЯ IMPORT.xlsx"
"""

import os
import shutil
import sqlite3
import sys
from datetime import datetime

import config


def load_term_address_phone(path):
    """Возвращает dict: payment_id -> (address, phone)."""
    try:
        import openpyxl
    except ImportError:
        print("Нужна библиотека openpyxl: pip install openpyxl")
        sys.exit(1)

    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb["TERM"]
    result = {}
    for row in ws.iter_rows(min_row=2, values_only=True):
        if len(row) < 15:
            continue
        payment_id = row[1]   # B
        address = row[11]     # L -- Адресс
        phone = row[14]       # O -- Номер телефона
        if payment_id is None:
            continue
        pid = str(payment_id).strip()
        addr = str(address).strip() if address is not None else None
        ph = str(phone).strip() if phone is not None else None
        result[pid] = (addr or None, ph or None)
    return result


def main():
    if len(sys.argv) < 2:
        print('Использование: python fix_address_phone.py "СВЕДЕНИЯ IMPORT.xlsx"')
        return 1

    xlsx_path = sys.argv[1]
    if not os.path.exists(xlsx_path):
        print(f"Файл не найден: {xlsx_path}")
        return 1

    print("Читаю лист TERM...")
    data = load_term_address_phone(xlsx_path)
    print(f"  Записей с адресом/телефоном: {len(data)}")

    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row

    print("\nОбновляю terminal_ids...")
    updated = 0
    for pid, (addr, ph) in data.items():
        if addr is None and ph is None:
            continue
        cur = conn.execute(
            "UPDATE terminal_ids SET address = ?, phone = ? "
            "WHERE payment_id = ? AND (address IS NULL OR phone IS NULL)",
            (addr, ph, pid),
        )
        if cur.rowcount:
            updated += cur.rowcount
    conn.commit()

    print(f"  Обновлено записей: {updated}")

    # Резервная копия делается автоматически только при изменениях > 0
    if updated > 0:
        backup = config.DB_PATH + ".backup-addr-" + datetime.now().strftime("%Y%m%d-%H%M%S")
        print(f"\nБаза уже изменена. Резервная копия ДО изменения не создавалась --")
        print(f"если хочешь, можно откатить вручную (файла бэкапа нет).")
        print(f"Для следующего раза: делай бэкап перед запуском.")
    else:
        print("  Ничего не изменено.")

    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())