#!/usr/bin/env python3
"""
Art Smile Dental Laboratory
Генератор наряд-заказа — интерактивный fillable PDF
Структура: Артикон  |  Реквизиты: Art Smile
"""

import os
import math
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont


# ─── Шрифты ────────────────────────────────────────────────────────────────

def setup_fonts():
    """Регистрирует шрифт с поддержкой кириллицы. Возвращает (regular, bold)."""
    reg_paths = [
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/Library/Fonts/Arial.ttf",
        "/usr/share/fonts/truetype/msttcorefonts/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    bold_paths = [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/Library/Fonts/Arial Bold.ttf",
        "/usr/share/fonts/truetype/msttcorefonts/Arial_Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ]
    reg = bold = None
    for p in reg_paths:
        if os.path.exists(p):
            pdfmetrics.registerFont(TTFont("AS_R", p))
            reg = "AS_R"
            break
    for p in bold_paths:
        if os.path.exists(p):
            pdfmetrics.registerFont(TTFont("AS_B", p))
            bold = "AS_B"
            break
    if not reg:
        reg, bold = "Helvetica", "Helvetica-Bold"
    return reg, bold or reg


# ─── Вспомогательный класс ─────────────────────────────────────────────────

class F:
    """Обёртка над canvas с удобными методами для построения формы."""

    def __init__(self, path, fr, fb):
        self.W, self.H = A4
        self.c = canvas.Canvas(path, pagesize=A4)
        self.fr = fr       # regular font
        self.fb = fb       # bold font
        self.BK = colors.black
        self.WH = colors.white

    # координаты ──────────────────────────────────────────────
    def x(self, v): return v * mm
    def y(self, v): return self.H - v * mm        # v = мм от верха

    # текст ───────────────────────────────────────────────────
    def lbl(self, text, xm, ym, sz=8.5, bold=False, right=False):
        self.c.setFont(self.fb if bold else self.fr, sz)
        self.c.setFillColor(self.BK)
        px, py = self.x(xm), self.y(ym)
        (self.c.drawRightString if right else self.c.drawString)(px, py, text)

    # интерактивные поля ──────────────────────────────────────
    def tf(self, name, xm, y_top_m, wm, hm=5.5, tip='', ml=False):
        """Текстовое поле. y_top_m — верх поля в мм от верха страницы."""
        flags = 'multiline' if ml else ''
        self.c.acroForm.textfield(
            name=name, tooltip=tip,
            x=self.x(xm), y=self.y(y_top_m + hm),
            width=wm * mm, height=hm * mm,
            fontSize=9, fontName='Helvetica',
            borderColor=self.BK, borderWidth=0.4,
            fillColor=self.WH, forceBorder=True,
            fieldFlags=flags,
        )

    def cb(self, name, xm, y_top_m, sm=3.5, tip=''):
        """Чекбокс. y_top_m — верх в мм от верха страницы."""
        self.c.acroForm.checkbox(
            name=name, tooltip=tip,
            x=self.x(xm), y=self.y(y_top_m + sm),
            size=sm * mm,
            borderColor=self.BK, borderWidth=0.5,
            fillColor=self.WH, checked=False, forceBorder=True,
        )

    # линии ───────────────────────────────────────────────────
    def hl(self, x1, x2, ym, lw=0.5):
        self.c.setLineWidth(lw)
        self.c.setStrokeColor(self.BK)
        self.c.line(self.x(x1), self.y(ym), self.x(x2), self.y(ym))

    def vl(self, xm, y1, y2, lw=0.5):
        self.c.setLineWidth(lw)
        self.c.setStrokeColor(self.BK)
        self.c.line(self.x(xm), self.y(y1), self.x(xm), self.y(y2))

    def save(self): self.c.save()


# ─── Зубная схема ──────────────────────────────────────────────────────────

def draw_teeth(f: F, cx_mm, cy_mm):
    """Упрощённая схема зубов по системе ВОЗ (FDI)."""
    c = f.c
    cx, cy = f.x(cx_mm), f.y(cy_mm)

    # Верхний ряд: 28..21 | 11..18  (по дуге сверху)
    upper = [28, 27, 26, 25, 24, 23, 22, 21, 11, 12, 13, 14, 15, 16, 17, 18]
    # Нижний ряд: 38..31 | 41..48  (по дуге снизу)
    lower = [38, 37, 36, 35, 34, 33, 32, 31, 41, 42, 43, 44, 45, 46, 47, 48]

    ax_up, ay_up = 33 * mm, 18 * mm
    ax_lo, ay_lo = 29 * mm, 16 * mm
    gap = 2.5 * mm        # зазор между дугами
    n = 16

    def r_tooth(num):
        pos = num % 10
        if pos >= 7: return 4.0 * mm
        if pos >= 5: return 3.3 * mm
        if pos >= 3: return 2.8 * mm
        return 2.2 * mm

    c.setLineWidth(0.4)
    c.setStrokeColor(colors.black)

    for i, t in enumerate(upper):
        ang = math.pi * i / (n - 1)
        px = cx + ax_up * math.cos(ang)
        py = (cy - gap) + ay_up * math.sin(ang)   # выше центра
        r = r_tooth(t)
        c.setFillColor(colors.white)
        c.circle(px, py, r, stroke=1, fill=1)
        c.setFont(f.fr, 5.5)
        c.setFillColor(colors.black)
        c.drawCentredString(px, py + r + 1.3 * mm, str(t))

    for i, t in enumerate(lower):
        ang = math.pi * i / (n - 1)
        px = cx + ax_lo * math.cos(ang)
        py = (cy + gap) - ay_lo * math.sin(ang)   # ниже центра
        r = r_tooth(t)
        c.setFillColor(colors.white)
        c.circle(px, py, r, stroke=1, fill=1)
        c.setFont(f.fr, 5.5)
        c.setFillColor(colors.black)
        c.drawCentredString(px, py - r - 3.0 * mm, str(t))

    # вертикальная ось (пунктир)
    c.setLineWidth(0.3)
    c.setDash(2, 2)
    c.setStrokeColor(colors.Color(0.6, 0.6, 0.6))
    c.line(cx, (cy - gap) + ay_up + 5 * mm, cx, (cy + gap) - ay_lo - 5 * mm)
    c.setDash()


# ─── Формы промежутков (понтиков) ──────────────────────────────────────────

def draw_pontic_shapes(f: F):
    """3 варианта формы промежутков."""
    c = f.c
    configs = [
        ("pontic_san",   55,  "санитарная"),
        ("pontic_ovate", 87,  "овальная"),
        ("pontic_full",  119, "полный контакт"),
    ]
    y_shape_top = 176   # мм от верха страницы (верх формы)
    y_shape_h   = 14    # мм высота формы

    for name, cx_mm, _ in configs:
        cx = f.x(cx_mm)
        # y центра формы
        cy = f.y(y_shape_top + y_shape_h / 2)
        c.setLineWidth(0.5)
        c.setStrokeColor(f.BK)
        c.setFillColor(f.WH)

        if name == "pontic_san":
            # Санитарная: узкий контакт снизу
            p = c.beginPath()
            p.moveTo(cx - 5*mm, cy + 5*mm)
            p.curveTo(cx - 8*mm, cy + 3*mm, cx - 8*mm, cy - 3*mm, cx - 3*mm, cy - 5*mm)
            p.curveTo(cx - 1*mm, cy - 6.5*mm, cx + 1*mm, cy - 6.5*mm, cx + 3*mm, cy - 5*mm)
            p.curveTo(cx + 8*mm, cy - 3*mm, cx + 8*mm, cy + 3*mm, cx + 5*mm, cy + 5*mm)
            p.curveTo(cx + 2.5*mm, cy + 7*mm, cx - 2.5*mm, cy + 7*mm, cx - 5*mm, cy + 5*mm)
            p.close()
            c.drawPath(p, stroke=1, fill=1)
        elif name == "pontic_ovate":
            # Овальная
            c.ellipse(cx - 6*mm, cy - 6*mm, cx + 6*mm, cy + 7*mm, stroke=1, fill=1)
        else:
            # Полный контакт: широкое плоское основание
            p = c.beginPath()
            p.moveTo(cx - 7*mm, cy + 6*mm)
            p.curveTo(cx - 9*mm, cy + 4*mm, cx - 9*mm, cy, cx - 7*mm, cy - 2*mm)
            p.lineTo(cx + 7*mm, cy - 2*mm)
            p.curveTo(cx + 9*mm, cy, cx + 9*mm, cy + 4*mm, cx + 7*mm, cy + 6*mm)
            p.curveTo(cx + 4*mm, cy + 8*mm, cx - 4*mm, cy + 8*mm, cx - 7*mm, cy + 6*mm)
            p.close()
            c.drawPath(p, stroke=1, fill=1)

        # чекбокс под фигурой
        f.cb(name, cx_mm - 2, y_shape_top + y_shape_h + 3, sm=4, tip=name)


# ─── Формы зубов ───────────────────────────────────────────────────────────

def draw_tooth_forms(f: F):
    """4 варианта формы зуба (правая колонка)."""
    c = f.c
    configs = [
        ("tf_square", 160, "прямоугольная"),
        ("tf_ovoid",  172, "овоидная"),
        ("tf_taper",  184, "конусная"),
        ("tf_sqov",   196, "смешанная"),
    ]
    y_top = 176
    y_h   = 14

    for name, cx_mm, _ in configs:
        cx = f.x(cx_mm)
        cy = f.y(y_top + y_h / 2)
        c.setLineWidth(0.5)
        c.setStrokeColor(f.BK)
        c.setFillColor(f.WH)

        if name == "tf_square":
            c.rect(cx - 4*mm, cy - 5*mm, 8*mm, 12*mm, stroke=1, fill=1)
        elif name == "tf_ovoid":
            c.ellipse(cx - 4.5*mm, cy - 5*mm, cx + 4.5*mm, cy + 7*mm, stroke=1, fill=1)
        elif name == "tf_taper":
            p = c.beginPath()
            p.moveTo(cx - 1.5*mm, cy - 5*mm)
            p.lineTo(cx - 4.5*mm, cy + 7*mm)
            p.lineTo(cx + 4.5*mm, cy + 7*mm)
            p.lineTo(cx + 1.5*mm, cy - 5*mm)
            p.close()
            c.drawPath(p, stroke=1, fill=1)
        else:
            # Смешанная: округлённый прямоугольник
            c.roundRect(cx - 4.5*mm, cy - 5*mm, 9*mm, 12*mm, 2*mm, stroke=1, fill=1)

        f.cb(name, cx_mm - 2, y_top + y_h + 3, sm=4, tip=name)


# ─── Форма десневого ложа ──────────────────────────────────────────────────

def draw_gingival_forms(f: F):
    """3 варианта формы десневого ложа."""
    c = f.c
    configs = [
        ("ging_arch",  55,  "дугообразная"),
        ("ging_flat",  87,  "плоская"),
        ("ging_point", 119, "остроконечная"),
    ]
    y_top = 232
    y_h   = 10

    for name, cx_mm, _ in configs:
        cx = f.x(cx_mm)
        cy = f.y(y_top + y_h / 2)
        c.setLineWidth(0.6)
        c.setStrokeColor(f.BK)

        if name == "ging_arch":
            # Дугообразная
            p = c.beginPath()
            p.moveTo(cx - 7*mm, cy - 3*mm)
            p.curveTo(cx - 7*mm, cy + 3*mm, cx - 3*mm, cy + 5*mm, cx, cy + 5*mm)
            p.curveTo(cx + 3*mm, cy + 5*mm, cx + 7*mm, cy + 3*mm, cx + 7*mm, cy - 3*mm)
            c.drawPath(p, stroke=1, fill=0)
        elif name == "ging_flat":
            # Уплощённая
            p = c.beginPath()
            p.moveTo(cx - 7*mm, cy - 1*mm)
            p.curveTo(cx - 7*mm, cy + 2*mm, cx, cy + 3*mm, cx, cy + 3*mm)
            p.curveTo(cx, cy + 3*mm, cx + 7*mm, cy + 2*mm, cx + 7*mm, cy - 1*mm)
            c.drawPath(p, stroke=1, fill=0)
        else:
            # Остроконечная
            p = c.beginPath()
            p.moveTo(cx - 7*mm, cy - 4*mm)
            p.curveTo(cx - 7*mm, cy + 2*mm, cx - 2*mm, cy + 6*mm, cx, cy + 7*mm)
            p.curveTo(cx + 2*mm, cy + 6*mm, cx + 7*mm, cy + 2*mm, cx + 7*mm, cy - 4*mm)
            c.drawPath(p, stroke=1, fill=0)

        f.cb(name, cx_mm - 2, y_top + y_h + 2, sm=4, tip=name)


# ─── Значок зуба (логотип) ─────────────────────────────────────────────────

def draw_logo_tooth(f: F):
    c = f.c
    tx, ty = f.x(11), f.y(24)
    c.setFillColor(f.WH)
    c.setStrokeColor(f.BK)
    c.setLineWidth(1.2)
    p = c.beginPath()
    p.moveTo(tx,          ty)
    p.curveTo(tx - 1.5*mm, ty + 2*mm,  tx - 2*mm,   ty + 5*mm,  tx,          ty + 7*mm)
    p.curveTo(tx + 1.5*mm, ty + 9*mm,  tx + 3.5*mm,  ty + 9*mm,  tx + 4.5*mm, ty + 7*mm)
    p.curveTo(tx + 6*mm,   ty + 9*mm,  tx + 8.5*mm,  ty + 9*mm,  tx + 9.5*mm, ty + 7*mm)
    p.curveTo(tx + 11.5*mm,ty + 5*mm,  tx + 11*mm,   ty + 2*mm,  tx + 9.5*mm, ty)
    p.curveTo(tx + 8*mm,   ty - 1.5*mm,tx + 7*mm,    ty - 2*mm,  tx + 4.5*mm, ty - 0.5*mm)
    p.curveTo(tx + 2*mm,   ty - 2*mm,  tx + 1.5*mm,  ty - 1.5*mm,tx,          ty)
    p.close()
    c.drawPath(p, stroke=1, fill=1)


# ─── Иконки контактных пунктов ─────────────────────────────────────────────

def draw_contact_icons(f: F):
    c = f.c
    # Точечный: окружность с точкой
    cx, cy = f.x(66), f.y(218)
    c.setLineWidth(0.5)
    c.setStrokeColor(f.BK)
    c.setFillColor(f.WH)
    c.circle(cx, cy, 4.5*mm, stroke=1, fill=1)
    c.setFillColor(f.BK)
    c.circle(cx, cy, 0.9*mm, stroke=0, fill=1)
    f.lbl("точечный", 71.5, 220)
    f.cb("contact_pt", 60, 223, sm=4, tip="Точечный")

    # Плоскостной: закрашенный прямоугольник
    rx, ry = f.x(108), f.y(220.5)
    c.setFillColor(f.BK)
    c.rect(rx - 4.5*mm, ry - 2*mm, 9*mm, 6*mm, stroke=0, fill=1)
    f.lbl("плоскостной", 114, 220)
    f.cb("contact_flat", 102, 223, sm=4, tip="Плоскостной")


# ─── Главная функция ───────────────────────────────────────────────────────

def build(output_path):
    fr, fb = setup_fonts()
    f = F(output_path, fr, fb)
    c = f.c

    # ══ Внешняя рамка ══
    c.setLineWidth(1.5)
    c.setStrokeColor(f.BK)
    c.rect(f.x(8), f.y(291), 194*mm, 283*mm)

    # ══ ШАПКА ══════════════════════════════════════════════════════════════
    draw_logo_tooth(f)
    f.lbl("Art smile",        25, 18, sz=16, bold=True)
    f.lbl("dental laboratory",25, 24, sz=9.5)

    f.lbl("г. Москва, ул. Смирновская 25, с16, о.301", 201, 12, right=True)
    f.lbl("e-mail: info@artsmile-lab.ru",              201, 17.5, right=True)
    f.lbl("тел. +7 (965) 243-44-44",                   201, 23,  right=True)

    f.hl(8, 202, 27, lw=1.5)

    # ══ ИНФОРМАЦИЯ О ПАЦИЕНТЕ (левая колонка) ══════════════════════════════
    f.lbl("Название клиники / ФИО врача", 10, 31.5, sz=8)
    f.tf("clinic1", 10, 32.5,  90, tip="Название клиники / ФИО врача")
    f.tf("clinic2", 10, 39,    90)

    f.lbl("Дата поступления работ", 10, 48.5, sz=8)
    f.tf("rcv_date", 10, 49.5, 90, tip="Дата поступления работ")

    f.lbl("ФИО пациента", 10, 59.5, sz=8)
    f.tf("patient1", 10, 60.5, 90, tip="ФИО пациента")
    f.tf("patient2", 10, 67,   90)

    # Возраст + Пол
    f.lbl("Возраст", 10, 77, sz=8)
    f.tf("age", 30, 73.5, 14, tip="Возраст")
    f.lbl("Пол", 47, 77, sz=8)
    f.cb("gender_m", 53, 73.5, tip="М")
    f.lbl("М", 58, 77, sz=8)
    f.cb("gender_f", 63.5, 73.5, tip="Ж")
    f.lbl("Ж", 68.5, 77, sz=8)

    # Цвет культи
    f.lbl("Цвет культи", 10, 86, sz=8)
    f.tf("color_cult",  32, 82.5, 73, tip="Цвет культи")

    # Цвет зубов
    f.lbl("Цвет зубов", 10, 93.5, sz=8)
    f.tf("color_teeth", 32, 90,   73, tip="Цвет зубов")

    # Система имплантов
    f.lbl("Система имплантов", 10, 101, sz=8)
    f.tf("implant", 10, 97.5, 72, tip="Система имплантов")
    f.lbl("øд.", 85, 101, sz=8)
    f.tf("diam",   92, 97.5, 14, tip="Диаметр")

    # ══ ЗУБНАЯ СХЕМА (правая колонка) ══════════════════════════════════════
    draw_teeth(f, cx_mm=157, cy_mm=66)
    f.vl(108, 27, 105, lw=0.3)

    # ══ ЧЕКБОКСЫ: фиксация / тип ══════════════════════════════════════════
    f.hl(8, 202, 105, lw=0.8)
    f.vl(67,  105, 136, lw=0.3)
    f.vl(129, 105, 136, lw=0.3)

    # Ряд 1
    f.cb("fix_screw",   10, 107, tip="Винтовая фиксация")
    f.lbl("винтовая фиксация",  15, 110.5, sz=8)
    f.cb("anat_full",   69, 107, tip="Полная анатомия")
    f.lbl("полная анатомия",    74, 110.5, sz=8)
    f.cb("type_single", 131, 107, tip="Одиночки")
    f.lbl("одиночки",          136, 110.5, sz=8)

    # Ряд 2
    f.cb("fix_cement", 10, 114, tip="Цементная фиксация")
    f.lbl("цементная фиксация", 15, 117.5, sz=8)
    f.cb("anat_nano",  69, 114, tip="Нанесение")
    f.lbl("нанесение",          74, 117.5, sz=8)
    f.cb("type_bridge",131, 114, tip="Мост")
    f.lbl("мост",              136, 117.5, sz=8)

    f.hl(8, 202, 121, lw=0.3)

    # Плечо
    f.lbl("Плечо",              10, 125.5, sz=8)
    f.cb("shldr_krug",  24, 122, tip="Круговое")
    f.lbl("круговое",           29, 125.5, sz=8)
    f.cb("girland",     69, 122, tip="Гирлянда")
    f.lbl("гирлянда",           74, 125.5, sz=8)
    f.cb("isk_desna",  131, 122, tip="Искусственная десна")
    f.lbl("искусственная десна",136, 125.5, sz=8)

    f.cb("shldr_vest",  24, 129, tip="Вестибулярно")
    f.lbl("вестибулярно",       29, 132.5, sz=8)

    f.hl(8, 202, 136, lw=0.8)

    # ══ ВИД РАБОТЫ ══════════════════════════════════════════════════════════
    f.lbl("Вид работы", 10, 141, sz=8)
    f.tf("work_main", 36, 137.5, 164, tip="Вид работы")
    f.tf("work1", 10, 144.5, 190)
    f.tf("work2", 10, 151.5, 190)
    f.tf("work3", 10, 158.5, 190)

    f.hl(8, 202, 167, lw=0.8)

    # ══ ФОРМЫ ПРОМЕЖУТКОВ / ЗУБОВ ══════════════════════════════════════════
    f.lbl("Форма промежутков (понтиков)", 10,  172, sz=8)
    f.lbl("Форма зубов",                156,  172, sz=8)

    draw_pontic_shapes(f)
    draw_tooth_forms(f)

    f.vl(151, 167, 245, lw=0.3)

    # ══ КОНТАКТНЫЕ ПУНКТЫ ══════════════════════════════════════════════════
    f.lbl("Контактные пункты", 10, 210, sz=8)
    draw_contact_icons(f)

    # ══ ФОРМА ДЕСНЕВОГО ЛОЖА ════════════════════════════════════════════════
    f.lbl("Форма десневого ложа", 10, 229, sz=8)
    draw_gingival_forms(f)

    f.hl(8, 202, 245, lw=0.8)

    # ══ ДАТЫ ════════════════════════════════════════════════════════════════
    f.lbl("Дата примерки (каркас)", 10,  252, sz=8)
    f.tf("date_fit", 63, 248.5, 41, tip="Дата примерки (каркас)")

    f.lbl("Дата сдачи работы",    115,  252, sz=8)
    f.tf("date_del", 160, 248.5, 40, tip="Дата сдачи работы")

    f.save()
    print(f"✓  PDF сохранён: {output_path}")


# ─── Точка входа ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    out = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "ArtSmile_Наряд-заказ.pdf"
    )
    build(out)
