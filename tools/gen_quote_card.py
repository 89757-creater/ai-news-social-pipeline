#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成「原话卡片」——把当事人公开说过的原话排成竖版图，供文章配图使用。

设计原则：只做**引语卡**，不伪造 X/微博等平台 UI 截图。
署名与出处必须真实可查，避免"看起来像截图但其实是编的"。

用法：python gen_quote_card.py --outdir ./out
"""
import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W, H = 1080, 1350
PAD = 88
BG = (14, 17, 22)
WHITE = (245, 246, 248)
RED = (229, 72, 77)
GRAY = (150, 156, 165)
DIM = (92, 100, 112)
QUOTE_BG = (28, 33, 41)

BOLD = "C:/Windows/Fonts/msyhbd.ttc"
REG = "C:/Windows/Fonts/msyh.ttc"


def f(path, size):
    return ImageFont.truetype(path, size)


def quote_card(lines, author, role, source, out):
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    # 装饰性大引号
    d.text((PAD - 10, 96), "\u201c", font=f("C:/Windows/Fonts/times.ttf", 260), fill=(58, 66, 78))

    y = 400
    fq = f(BOLD, 58)
    for line in lines:
        d.text((PAD, y), line, font=fq, fill=WHITE)
        y += 96

    y += 40
    d.rectangle([PAD, y, PAD + 96, y + 7], fill=RED)

    d.text((PAD, y + 52), author, font=f(BOLD, 42), fill=RED)
    d.text((PAD, y + 116), role, font=f(REG, 33), fill=GRAY)
    d.text((PAD, y + 170), source, font=f(REG, 28), fill=DIM)

    img.save(out, "PNG")
    return out


def term_card(term_en, term_cn, desc, out):
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    d.rectangle([PAD, 120, PAD + 74, 128], fill=RED)
    d.text((PAD, 158), "一个被造出来的词", font=f(BOLD, 40), fill=RED)

    d.text((PAD, 470), term_en, font=f(BOLD, 108), fill=WHITE)
    d.text((PAD, 610), term_cn, font=f(BOLD, 66), fill=RED)

    d.rectangle([PAD, 760, PAD + 96, 767], fill=(58, 66, 78))
    y = 820
    for line in desc:
        d.text((PAD, y), line, font=f(REG, 40), fill=GRAY)
        y += 68

    img.save(out, "PNG")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--outdir", default=".")
    args = ap.parse_args()
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    a = quote_card(
        ["这是一台非常努力的机器，", "但我不确定它在", "创造任何东西。"],
        "ARMIN RONACHER",
        "Flask 框架作者",
        "2026-09-07 博客复盘 · 35 小时自主编码实验",
        outdir / "quote_ronacher.png",
    )
    b = term_card(
        "reward hacking",
        "奖励劫持",
        ["模型发现：把代码写得让人看懂，", "这件事本身不加分。"],
        outdir / "term_reward_hacking.png",
    )
    print("已生成:", a)
    print("已生成:", b)


if __name__ == "__main__":
    main()
