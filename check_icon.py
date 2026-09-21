# -*- coding: utf-8 -*-
"""Проверка состояния иконки: файл, размеры, где ищется, что с exe."""

import os
import sys

print("=" * 60)
print("ДИАГНОСТИКА ИКОНКИ")
print("=" * 60)

# 1. Файлы в корне проекта
print("\n1. Файлы в корне проекта:")
for name in ("icon.ico", "icon_source.png"):
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), name)
    if os.path.exists(p):
        size = os.path.getsize(p)
        print(f"   [OK] {name}  ({size:,} байт)")
    else:
        print(f"   [!!] {name}  -- НЕТ")

# 2. Что внутри icon.ico
print("\n2. Содержимое icon.ico:")
try:
    from PIL import Image
    ico_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.ico")
    if os.path.exists(ico_path):
        img = Image.open(ico_path)
        print(f"   Формат: {img.format}")
        sizes = getattr(img, "info", {}).get("sizes", set())
        print(f"   Размеры внутри: {sorted(sizes)}")
        has_256 = (256, 256) in sizes
        print(f"   Есть 256x256: {'ДА' if has_256 else 'НЕТ (это плохо для Windows!)'}")
    else:
        print("   icon.ico не найден")
except ImportError:
    print("   [skip] Pillow не установлен")
except Exception as e:
    print(f"   Ошибка чтения: {e}")

# 3. gui/icons.py существует?
print("\n3. gui/icons.py:")
p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gui", "icons.py")
if os.path.exists(p):
    print(f"   [OK] существует")
    # Что в нём ищется
    with open(p, encoding="utf-8") as f:
        content = f.read()
    if "icon.ico" in content:
        print(f"   [OK] ссылается на icon.ico")
    else:
        print(f"   [!!] НЕ ссылается на icon.ico")
else:
    print(f"   [!!] НЕ найден -- нужно создать")

# 4. Подключена ли иконка в окнах
print("\n4. Подключение set_window_icon:")
for fname in ("login_window.py", "main_window.py", "terminal_card.py", "merchant_card.py"):
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gui", fname)
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            content = f.read()
        if "set_window_icon" in content:
            print(f"   [OK] {fname}")
        else:
            print(f"   [!!] {fname} -- НЕ подключена")

# 5. Собранный exe
print("\n5. Собранный exe:")
base = os.path.dirname(os.path.abspath(__file__))
exe_path = os.path.join(base, "dist", "TerminalManager", "TerminalManager.exe")
if os.path.exists(exe_path):
    size = os.path.getsize(exe_path)
    mtime = os.path.getmtime(exe_path)
    from datetime import datetime
    print(f"   [OK] {exe_path}")
    print(f"        размер: {size:,} байт")
    print(f"        собран: {datetime.fromtimestamp(mtime)}")
else:
    print(f"   [!!] exe не найден по пути:")
    print(f"        {exe_path}")

# 6. Внутри dist рядом с exe есть icon.ico?
print("\n6. Файлы в dist\\TerminalManager\\:")
dist_dir = os.path.join(base, "dist", "TerminalManager")
if os.path.exists(dist_dir):
    for name in sorted(os.listdir(dist_dir)):
        if name.endswith(".ico") or name.endswith(".exe"):
            p = os.path.join(dist_dir, name)
            print(f"   {name}  ({os.path.getsize(p):,} байт)")
    # И внутри _internal
    internal = os.path.join(dist_dir, "_internal")
    if os.path.exists(internal):
        for name in sorted(os.listdir(internal)):
            if name.endswith(".ico"):
                print(f"   _internal\\{name}")
else:
    print("   папки dist\\TerminalManager нет")

print()
print("=" * 60)