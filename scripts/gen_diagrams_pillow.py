# -*- coding: utf-8 -*-
"""纯 Pillow 版公众号正文配图生成器（cairosvg 不可用时的替代方案）

用法:
    python gen_diagrams_pillow.py --outdir ./assets

生成两张 1200x620 白底配图：
    fig_a_compare.png  —— 有人看的写法 vs 没人看的写法
    fig_b_two_states.png —— 被看着时 vs 没人看时
"""
import argparse
import os
import random

from PIL import Image, ImageDraw, ImageFont, ImageFilter

W, H = 1200, 620
BG = (255, 255, 255)
INK = (42, 47, 54)
MUTED = (118, 126, 136)
BAR = (143, 169, 214)
LOOSE = (176, 189, 208)
DENSE = (196, 205, 218)
LIGHT = (232, 237, 244)

FONT_DIR = os.environ.get("WINDIR", r"C:\Windows") + r"\Fonts"


def load_font(size, bold=False):
    names = ["msyhbd.ttc", "msyh.ttc", "simhei.ttf"] if bold else ["msyh.ttc", "msyhbd.ttc", "simsun.ttc"]
    for n in names:
        p = os.path.join(FONT_DIR, n)
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                continue
    return ImageFont.load_default()


def centered(d, cx, y, text, f, fill):
    l, t, r, b = d.textbbox((0, 0), text, font=f)
    d.text((cx - (r - l) / 2 - l, y), text, font=f, fill=fill)


def fig_a(path, f_label, f_caption):
    """两段代码排版对比：左舒展，右压缩。"""
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    random.seed(7)

    left_cx, right_cx = W // 4, W * 3 // 4

    # 左侧：间距舒展
    y = 150
    for _ in range(9):
        x = left_cx - 190
        for _ in range(random.randint(1, 3)):
            ln = random.randint(48, 150)
            d.rounded_rectangle([x, y, x + ln, y + 11], radius=5, fill=LOOSE)
            x += ln + 14
        y += 34

    # 右侧：密集压缩
    y = 150
    for _ in range(13):
        x = right_cx - 190
        for _ in range(random.randint(3, 5)):
            ln = random.randint(22, 62)
            d.rounded_rectangle([x, y, x + ln, y + 8], radius=4, fill=DENSE)
            x += ln + 5
        y += 24

    # 中分隔线
    d.rectangle([W // 2 - 1, 120, W // 2 + 1, 460], fill=LIGHT)

    # 标签
    centered(d, left_cx, 92, "有人看的写法", f_label, INK)
    centered(d, right_cx, 92, "没人看的写法", f_label, MUTED)
    centered(d, left_cx, 500, "留白、命名清楚、能维护", f_caption, MUTED)
    centered(d, right_cx, 500, "省 token、变量名极短、挤成一片", f_caption, MUTED)

    img.save(path, "PNG")
    return path


def fig_b(path, f_label, f_caption):
    """同一形状的两种状态：清晰 vs 模糊。"""
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    left_cx, right_cx = W // 4, W * 3 // 4
    size = 150
    cy = 290

    # 左侧：清晰立方体（用多边形模拟）
    box = [left_cx - size // 2, cy - size // 2, left_cx + size // 2, cy + size // 2]
    d.rounded_rectangle(box, radius=10, outline=INK, width=4)
    d.line([left_cx, cy - size // 2, left_cx, cy + size // 2], fill=INK, width=4)
    d.line([left_cx - size // 2, cy, left_cx + size // 2, cy], fill=INK, width=4)

    # 右侧：模糊版本
    tmp = Image.new("RGB", (W, H), BG)
    td = ImageDraw.Draw(tmp)
    box2 = [right_cx - size // 2, cy - size // 2, right_cx + size // 2, cy + size // 2]
    td.rounded_rectangle(box2, radius=10, outline=MUTED, width=4)
    td.line([right_cx, cy - size // 2, right_cx, cy + size // 2], fill=MUTED, width=4)
    td.line([right_cx - size // 2, cy, right_cx + size // 2, cy], fill=MUTED, width=4)
    tmp = tmp.filter(ImageFilter.GaussianBlur(6))
    mask = Image.new("L", (W, H), 0)
    md = ImageDraw.Draw(mask)
    md.rectangle([right_cx - 140, cy - 140, right_cx + 140, cy + 140], fill=255)
    img.paste(tmp, (0, 0), mask)

    d.rectangle([W // 2 - 1, 160, W // 2 + 1, 420], fill=LIGHT)

    centered(d, left_cx, 122, "被看着时", f_label, INK)
    centered(d, right_cx, 122, "没人看时", f_label, MUTED)
    centered(d, left_cx, 470, "结构清晰，边界分明", f_caption, MUTED)
    centered(d, right_cx, 470, "逐渐失焦，和背景融在一起", f_caption, MUTED)

    img.save(path, "PNG")
    return path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--outdir", default="./assets")
    a = ap.parse_args()
    os.makedirs(a.outdir, exist_ok=True)

    f_label = load_font(30, bold=True)
    f_caption = load_font(22)

    p1 = fig_a(os.path.join(a.outdir, "fig_a_compare.png"), f_label, f_caption)
    p2 = fig_b(os.path.join(a.outdir, "fig_b_two_states.png"), f_label, f_caption)
    print("saved:", p1)
    print("saved:", p2)


if __name__ == "__main__":
    main()
