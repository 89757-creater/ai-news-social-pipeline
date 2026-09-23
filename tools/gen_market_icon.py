#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成技能市场用图标（512×512 PNG）。

官方要求：512×512 像素的 PNG。
设计取向：极简 + 古典（用户 2026-09-16 明确的审美偏好）——
深色底、单一强调色、无渐变堆砌、无品牌 Logo、无真人肖像。

图形语义：一个源头（AI）分流向两个平台（公众号 / 抖音）。

用法：
    python gen_market_icon.py                      # 输出到工作区根
    python gen_market_icon.py -o D:/icon.png       # 指定路径
    python gen_market_icon.py --palette light      # 浅色底版本
"""
import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

SIZE = 512

PALETTES = {
    # 与流水线出图色板同源（lagoon）
    "dark": {"bg": "#0C202E", "main": "#F2F7F9", "accent": "#41D1D9"},
    "light": {"bg": "#F4F7F9", "main": "#12303D", "accent": "#1C8F99"},
}

FONT_CANDIDATES = [
    r"C:/Windows/Fonts/msyhbd.ttc",
    r"C:/Windows/Fonts/msyh.ttc",
    r"C:/Windows/Fonts/simhei.ttf",
    r"C:/Windows/Fonts/arialbd.ttf",
]


def load_font(size):
    for p in FONT_CANDIDATES:
        if Path(p).is_file():
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                continue
    return ImageFont.load_default()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-o", "--out", default=None)
    ap.add_argument("--palette", choices=list(PALETTES), default="dark")
    a = ap.parse_args()

    c = PALETTES[a.palette]
    img = Image.new("RGB", (SIZE, SIZE), c["bg"])
    d = ImageDraw.Draw(img)

    # 1) 中央主字「AI」
    f = load_font(210)
    text = "AI"
    box = d.textbbox((0, 0), text, font=f)
    tw, th = box[2] - box[0], box[3] - box[1]
    tx, ty = (SIZE - tw) // 2 - box[0], 168 - th // 2 - box[1]
    d.text((tx, ty), text, font=f, fill=c["main"])

    # 2) 分流：一竖 + 两斜 + 两圆点（一源两平台）
    w = 12
    y0, y1 = 300, 358          # 主干
    y2 = 412                   # 分叉末端
    left_x, right_x = 152, 360
    mid_x = SIZE // 2
    d.line([(mid_x, y0), (mid_x, y1)], fill=c["accent"], width=w)
    d.line([(mid_x, y1), (left_x, y2)], fill=c["accent"], width=w)
    d.line([(mid_x, y1), (right_x, y2)], fill=c["accent"], width=w)
    r = 15
    for x in (left_x, right_x):
        d.ellipse([x - r, y2 - r, x + r, y2 + r], fill=c["main"])

    out = Path(a.out) if a.out else Path.cwd() / "ai-news-social-pipeline-icon.png"
    img.save(out, "PNG")

    # 自检：尺寸 + 底色 + 是否用了强调色
    with Image.open(out) as chk:
        px = list(chk.getdata())
        used = {p for p in px}
        print(f"✅ 图标已生成：{out}")
        print(f"   尺寸 {chk.size[0]}×{chk.size[1]}（要求 512×512）")
        print(f"   颜色数 {len(used)}（越少越干净）")
        print(f"   底色 {c['bg']} 是否出现：{tuple(int(c['bg'][i:i+2], 16) for i in (1, 3, 5)) in used}")
        ok = chk.size == (SIZE, SIZE)
        print("   结论：" + ("符合 512×512 要求" if ok else "✗ 尺寸不符"))
        return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
