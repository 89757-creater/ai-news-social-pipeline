#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成抖音竖版封面/头图（1080×1440，3:4）。

抖音文章需要「文章头图」与「封面设置」两张图，本脚本一次产出两张同风格图。
深色底 + 大字 + 红色数字强调 —— 刷流里对比度更高。

用法：
  python gen_douyin_cover.py --outdir ./out
"""
import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W, H = 1080, 1440
PAD = 96

BG = (14, 17, 22)
WHITE = (255, 255, 255)
RED = (229, 72, 77)
GRAY = (150, 156, 165)
DIM = (96, 104, 115)

BOLD = "C:/Windows/Fonts/msyhbd.ttc"
REG = "C:/Windows/Fonts/msyh.ttc"


def font(path, size):
    return ImageFont.truetype(path, size)


def draw_left(d, xy, text, f, fill):
    d.text(xy, text, font=f, fill=fill)
    return f.getbbox(text)


def build(headline, eyebrow, subtitle, stats, out_path):
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    # 顶部品牌条
    d.rectangle([PAD, 118, PAD + 74, 126], fill=RED)
    d.text((PAD, 152), eyebrow, font=font(BOLD, 40), fill=RED)

    # 主标题：逐行，第二行用红色强调
    y = 400
    fh = font(BOLD, 96)
    for i, line in enumerate(headline):
        color = RED if line.startswith("*") else WHITE
        text = line.lstrip("*")
        d.text((PAD, y), text, font=fh, fill=color)
        y += 132

    # 副标题
    d.text((PAD, 1060), subtitle, font=font(REG, 46), fill=GRAY)

    # 数据条
    d.line([PAD, 1150, W - PAD, 1150], fill=DIM, width=2)
    d.text((PAD, 1190), stats, font=font(REG, 37), fill=GRAY)

    # 底部留白保护（抖音 UI 可能遮挡）
    img.save(out_path, "PNG")
    return out_path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--outdir", default=".")
    args = ap.parse_args()
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    headline = ["AI 狂写", "*7.5 万行代码", "却说它", "没创造任何东西"]
    eyebrow = "AI 编程 · 现象观察"
    subtitle = "没人盯着的时候，它换了一副面孔"
    stats = "35 小时 · 79 次提交 · 10 亿 token · $1200"

    a = build(headline, eyebrow, subtitle, stats, outdir / "douyin_head.png")
    b = build(headline, eyebrow, subtitle, stats, outdir / "douyin_cover.png")
    print("已生成:", a)
    print("已生成:", b)


if __name__ == "__main__":
    main()
