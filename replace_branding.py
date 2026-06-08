#!/usr/bin/env python3
"""
Берёт PDF Артикона как основу.
Заменяет ТОЛЬКО брендинг — всё остальное без изменений.
"""

import fitz

SRC = "/Users/khadzhimuradmagomedov/Downloads/Артикон НЗ.pdf"
DST = "/Users/khadzhimuradmagomedov/Documents/dental-lab-automation/ArtSmile_НЗ_Артикон.pdf"

ARIAL        = "/System/Library/Fonts/Supplemental/Arial.ttf"
ARIAL_BOLD   = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
ARIAL_NARROW = "/System/Library/Fonts/Supplemental/Arial Narrow.ttf"

LOGO_GRAY = (0.31, 0.31, 0.31)
BLACK     = (0, 0, 0)
RIGHT_EDGE = 403.0


# ── Геометрический зуб (чёрно-белый) ────────────────────────────────────────

def draw_tooth(page, x0, y0, w, h):
    """Рисует геометрический зуб в оттенках серого, как в логотипе Art Smile."""

    def P(nx, ny):
        return (x0 + nx * w, y0 + ny * h)

    # Ключевые точки (нормализованные 0–1)
    top_L   = P(0.05, 0.18)
    cusp_L  = P(0.23, 0.00)
    valley  = P(0.47, 0.22)
    cusp_R  = P(0.73, 0.00)
    top_R   = P(0.92, 0.16)
    mid_R   = P(0.97, 0.52)
    bot_R   = P(0.78, 0.88)
    bot_C   = P(0.50, 1.00)
    bot_L   = P(0.22, 0.88)
    mid_L   = P(0.03, 0.52)
    center  = P(0.50, 0.58)
    mid_top = P(0.50, 0.30)

    # Цвета граней (от светлого к тёмному — объём)
    C1 = (0.90, 0.90, 0.90)   # почти белый
    C2 = (0.75, 0.75, 0.75)   # светло-серый
    C3 = (0.58, 0.58, 0.58)   # средний серый
    C4 = (0.40, 0.40, 0.40)   # тёмный серый
    WH = (1.00, 1.00, 1.00)   # белые линии между гранями

    def face(pts, fill):
        shape = page.new_shape()
        shape.draw_polyline(pts + [pts[0]])
        shape.finish(fill=fill, color=WH, width=0.6, closePath=True)
        shape.commit()

    # Грани: верхние светлее, боковые темнее — создают объём
    face([cusp_L, valley,  mid_top, top_L],  C1)   # верх левый
    face([valley,  cusp_R, top_R,  mid_top], C1)   # верх правый
    face([top_L,   mid_top, center, mid_L],  C2)   # левый бок
    face([mid_top, top_R,   mid_R,  center], C3)   # правый бок
    face([valley,  mid_top, center, bot_C],  C2)   # центр низ
    face([mid_L,   center,  bot_L],          C3)   # нижний левый
    face([mid_R,   bot_R,   center],         C4)   # нижний правый (самый тёмный)
    face([center,  bot_R,   bot_C],          C3)   # низ право-центр
    face([center,  bot_C,   bot_L],          C2)   # низ лево-центр

    # Контур зуба целиком
    outline = [cusp_L, valley, cusp_R, top_R, mid_R, bot_R, bot_C, bot_L, mid_L, top_L]
    shape = page.new_shape()
    shape.draw_polyline(outline + [outline[0]])
    shape.finish(fill=None, color=(0.25, 0.25, 0.25), width=0.8, closePath=True)
    shape.commit()


# ── Правовыровненный текст ───────────────────────────────────────────────────

def insert_right(page, text, y, font_obj, fontfile, fontname, size, color):
    w = font_obj.text_length(text, fontsize=size)
    page.insert_text(
        fitz.Point(RIGHT_EDGE - w, y),
        text, fontfile=fontfile, fontname=fontname,
        fontsize=size, color=color,
    )


# ── Основная функция ─────────────────────────────────────────────────────────

def build():
    doc  = fitz.open(SRC)
    page = doc[0]

    # 1. Закрасить белым логотип Артикона и старые контакты
    for r in (
        fitz.Rect(182,  0, 420,  80),
        fitz.Rect(293, 76, 420, 128),
    ):
        page.add_redact_annot(r, fill=(1, 1, 1), text="")
    page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE)

    # 2. "ArtSmile" — на месте ARTICON, 40pt жирный серый
    page.insert_text(
        fitz.Point(183, 52),
        "ArtSmile",
        fontfile=ARIAL_BOLD, fontname="artb",
        fontsize=40, color=LOGO_GRAY,
    )

    # 3. "digital dental laboratory" — тонкий, под ArtSmile
    page.insert_text(
        fitz.Point(183, 70),
        "digital dental  laboratory",
        fontfile=ARIAL_NARROW, fontname="artn",
        fontsize=12, color=LOGO_GRAY,
    )

    # 5. Контакты — правое выравнивание, как у Артикона
    fb = fitz.Font(fontfile=ARIAL_BOLD)
    for y, text in [
        (90,  "тел.:  +7 (965) 243-44-44"),
        (103, "e-mail:  info@artsmile-lab.ru"),
    ]:
        insert_right(page, text, y, fb, ARIAL_BOLD, "artb", 8.5, BLACK)

    # 6. Сохранить
    doc.save(DST, garbage=4, deflate=True)
    print(f"✓  Готово: {DST}")


if __name__ == "__main__":
    build()
