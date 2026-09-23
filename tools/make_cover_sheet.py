#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把各篇抖音竖版封面拼成一张对比图（便于一眼验收差异化）。

用法：
  python make_cover_sheet.py                     # 扫 social/*/douyin/douyin_cover.png
  python make_cover_sheet.py --out sheet.png --width 300
"""
import argparse
from pathlib import Path

from PIL import Image, ImageDraw

WS = Path(r"C:/Users/suge0/WorkBuddy/automation-2026-09-13-16-27-29")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(WS / "social"))
    ap.add_argument("--out", default=str(WS / "douyin_covers_sheet.png"))
    ap.add_argument("--width", type=int, default=300, help="单张缩略图宽度")
    ap.add_argument("--gap", type=int, default=18)
    a = ap.parse_args()

    root = Path(a.root)
    items = []
    for d in sorted(root.iterdir()):
        f = d / "douyin" / "douyin_cover.png"
        if f.exists():
            items.append((d.name, f))
    if not items:
        print("没找到封面：", root)
        return 1

    thumbs = []
    for name, f in items:
        im = Image.open(f).convert("RGB")
        w = a.width
        h = round(im.height * w / im.width)
        thumbs.append((name, im.resize((w, h), Image.LANCZOS)))

    tw, th = thumbs[0][1].size
    cap = 34
    W = a.gap + len(thumbs) * (tw + a.gap)
    H = a.gap + cap + th + a.gap
    sheet = Image.new("RGB", (W, H), (14, 17, 22))
    dr = ImageDraw.Draw(sheet)

    for i, (name, im) in enumerate(thumbs):
        x = a.gap + i * (tw + a.gap)
        sheet.paste(im, (x, a.gap + cap))
        dr.text((x + 2, a.gap + 8), name, fill=(200, 205, 212))
        dr.rectangle([x, a.gap + cap, x + tw - 1, a.gap + cap + th - 1], outline=(60, 66, 76))

    sheet.save(a.out)
    print("已生成:", a.out, sheet.size, "共", len(thumbs), "篇")
    for name, _ in thumbs:
        print("  -", name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
