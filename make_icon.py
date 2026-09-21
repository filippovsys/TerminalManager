# -*- coding: utf-8 -*-
"""
Конвертирует PNG-картинку в .ico со всеми стандартными размерами
Windows (16, 24, 32, 48, 64, 128, 256).

Запуск:
    python make_icon.py исходник.png icon.ico

Понадобится Pillow:
    pip install Pillow
"""

import sys
import os

try:
    from PIL import Image
except ImportError:
    print("Нужна библиотека Pillow. Установи:")
    print("    pip install Pillow")
    sys.exit(1)


SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]


def main():
    if len(sys.argv) < 3:
        print("Использование: python make_icon.py исходник.png icon.ico")
        sys.exit(1)

    src = sys.argv[1]
    dst = sys.argv[2]

    if not os.path.exists(src):
        print(f"Файл не найден: {src}")
        sys.exit(1)

    img = Image.open(src).convert("RGBA")

    # Приводим к квадрату, если картинка не квадратная
    w, h = img.size
    if w != h:
        side = max(w, h)
        canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
        canvas.paste(img, ((side - w) // 2, (side - h) // 2), img)
        img = canvas

    # Немного сжимаем, чтобы края не обрезались в круглых иконках Windows
    # (по желанию -- можно убрать этот блок)
    # img = img.resize((int(img.width * 0.9), int(img.height * 0.9)))

    # Сохраняем как .ico со всеми размерами
    img.save(dst, format="ICO", sizes=SIZES)
    print(f"Готово: {dst}")
    print(f"Размеры в иконке: {', '.join(f'{w}x{h}' for w, h in SIZES)}")


if __name__ == "__main__":
    main()