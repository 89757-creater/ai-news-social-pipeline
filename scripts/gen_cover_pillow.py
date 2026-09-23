# -*- coding: utf-8 -*-
"""纯 Pillow 版公众号封面生成器（cairosvg 不可用时的替代方案）

用法:
    python gen_cover_pillow.py --out cover.png \
        --eyebrow "深度观察 · AI 工程" \
        --title "AI 写的代码，" "人类已经看不懂了" \
        --subtitle "35 小时，7.5 万行，1200 美元" \
        --pills "没人看时换写法,35小时实验,自述没创造价值"

输出: 900x383 横版 PNG，浅色系，无作者署名。
"""
import argparse
import os

from PIL import Image, ImageDraw, ImageFont

W, H = 900, 383
BG = (246, 248, 252)
INK = (42, 47, 54)
SUB = (92, 102, 117)
BAR = (143, 169, 214)
CHIP_BG = (221, 230, 245)
CHIP_TX = (58, 85, 128)

FONT_DIR = os.environ.get("WINDIR", r"C:\Windows") + r"\Fonts"
BOLD_CANDIDATES = ["msyhbd.ttc", "msyh.ttc", "simhei.ttf"]
REG_CANDIDATES = ["msyh.ttc", "msyhbd.ttc", "simsun.ttc"]


def load_font(size, bold=False):
    names = BOLD_CANDIDATES if bold else REG_CANDIDATES
    for n in names:
        p = os.path.join(FONT_DIR, n)
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                continue
    return ImageFont.load_default()


def draw_chip(d, x, y, text, f, pad_x=13, pad_y=7, bg=CHIP_BG, fg=CHIP_TX, radius=5):
    l, t, r, b = d.textbbox((0, 0), text, font=f)
    w, h = r - l, b - t
    box = [x, y, x + w + pad_x * 2, y + h + pad_y * 2]
    d.rounded_rectangle(box, radius=radius, fill=bg)
    d.text((x + pad_x - l, y + pad_y - t), text, font=f, fill=fg)
    return box[2]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--eyebrow", default="")
    ap.add_argument("--title", nargs="+", required=True)
    ap.add_argument("--subtitle", default="")
    ap.add_argument("--pills", default="")
    a = ap.parse_args()

    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    f_eyebrow = load_font(19)
    f_title = load_font(46, bold=True)
    f_sub = load_font(21)
    f_pill = load_font(17)

    left = 54
    y = 62

    if a.eyebrow:
        draw_chip(d, left, y, a.eyebrow, f_eyebrow)
    y += 54

    bar_top = y + 4
    for line in a.title:
        d.text((left, y), line, font=f_title, fill=INK)
        y += 60
    bar_bottom = y - 12
    d.rectangle([left - 18, bar_top, left - 14, bar_bottom], fill=BAR)

    y += 6
    if a.subtitle:
        d.text((left, y), a.subtitle, font=f_sub, fill=SUB)
        y += 40

    if a.pills:
        px = left
        py = H - 66
        for item in [s.strip() for s in a.pills.split(",") if s.strip()]:
            px = draw_chip(d, px, py, item, f_pill) + 10

    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    img.save(a.out, "PNG")
    print("saved:", a.out, img.size)


if __name__ == "__main__":
    main()
