# -*- coding: utf-8 -*-
"""
Готовит маленький logo.png из icon_source.png для окна логина.
Запускать один раз (и потом при смене картинки).

Использование:
    python make_logo.py
"""

import os
import sys

try:
    from PIL import Image
except ImportError:
    print("Нужна библиотека Pillow:")
    print("    pip install Pillow")
    sys.exit(1)


SRC = "icon_source.png"
DST = "logo.png"
MAX_SIZE = (400, 400)   # максимум по большей стороне


def main():
    if not os.path.exists(SRC):
        print(f"Файл не найден: {SRC}")
        sys.exit(1)

    img = Image.open(SRC).convert("RGBA")

    # Обрезаем прозрачные поля вокруг (если есть)
    bbox = img.getbbox()
    if bbox:
        img = img.crop(bbox)

    # Уменьшаем до нужного размера с сохранением пропорций
    img.thumbnail(MAX_SIZE, Image.LANCZOS)

    img.save(DST, "PNG", optimize=True)
    size_kb = os.path.getsize(DST) / 1024
    print(f"Готово: {DST}  ({img.width}x{img.height}, {size_kb:.1f} КБ)")


if __name__ == "__main__":
    main()