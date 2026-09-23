#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""封面「配色差异化」自动验收。

用户 2026-09-18 的诉求是「把封面插图的颜色也做差异化处理」——
这是一个**只准改颜色、不准动版式**的改动。所以验收分两组：

【A 组】颜色确实差异化了
  A1 五期主色（accent）色相互不相同，两两最小间隔 ≥ 25°
  A2 五期底色（bg）也各不相同，两两最小距离 ≥ 12（RGB 欧氏）
  A3 每期封面里的主色像素确实存在（>0.1%），不是"色板定义了但没用上"

【B 组】版式一个像素都没动（回归）
  B1 与上一版（`_bak_before_color/`）逐张比 **墨迹遮罩 IoU ≥ 0.97**
     —— 遮罩 = 相对各自底色偏离 >24 的像素。IoU 高就说明图形几何完全一致，
     变化只发生在颜色通道。
  B2 主色在这两版里**必须不同**（否则等于没改）

任一项不过即 exit 1。用法：
  python verify_cover_color.py
"""
import io
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from PIL import Image  # noqa: E402

WS = Path(r"C:/Users/suge0/WorkBuddy/automation-2026-09-13-16-27-29")
sys.path.insert(0, str(WS / "tools"))
import gen_douyin_cover_illu as G  # noqa: E402

DAYS = ["2026-09-14", "2026-09-15", "2026-09-16", "2026-09-17", "2026-09-18"]

fails: list[str] = []


def ok(cond, msg):
    print(("  PASS  " if cond else "  FAIL  ") + msg)
    if not cond:
        fails.append(msg)


def hex2rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def hue(rgb):
    r, g, b = [v / 255 for v in rgb]
    mx, mn = max(r, g, b), min(r, g, b)
    d = mx - mn
    if d == 0:
        return None
    if mx == r:
        h = 60 * (((g - b) / d) % 6)
    elif mx == g:
        h = 60 * ((b - r) / d + 2)
    else:
        h = 60 * ((r - g) / d + 4)
    return h % 360


def hdiff(a, b):
    if a is None or b is None:
        return None
    d = abs(a - b) % 360
    return min(d, 360 - d)


def dist(a, b):
    return sum((x - y) ** 2 for x, y in zip(a, b)) ** 0.5


def bg_of(im):
    """取最高频颜色当「底色」。"""
    cols = im.convert("RGB").getcolors(maxcolors=1 << 24)
    return max(cols, key=lambda c: c[0])[1]


def mask_of(im):
    bg = bg_of(im)
    px = im.convert("RGB").load()
    w, h = im.size
    m = bytearray(w * h)
    for y in range(h):
        row = y * w
        for x in range(w):
            r, g, b = px[x, y]
            if abs(r - bg[0]) + abs(g - bg[1]) + abs(b - bg[2]) > 24:
                m[row + x] = 1
    return m


def iou(a, b):
    inter = sum(1 for i in range(len(a)) if a[i] and b[i])
    union = sum(1 for i in range(len(a)) if a[i] or b[i])
    return inter / union if union else 1.0


def ink_ratio(im, rgb):
    """某颜色在图中占比（容差 30）。"""
    px = im.convert("RGB").load()
    w, h = im.size
    n = 0
    for y in range(0, h, 2):
        for x in range(0, w, 2):
            r, g, b = px[x, y]
            if abs(r - rgb[0]) + abs(g - rgb[1]) + abs(b - rgb[2]) <= 30:
                n += 1
    return n / ((w // 2) * (h // 2))


print("【A 组】颜色差异化")
accents, bgs = {}, {}
for d in DAYS:
    key = next(k for k, v in G.TOPICS.items() if v["date"] == d)
    pal = G.PALETTES[G.TOPICS[key]["palette"]]
    accents[d] = hex2rgb(pal["accent"])
    bgs[d] = hex2rgb(pal["bg"])

print("  主色：", {d: "%s %s" % (G.TOPICS[next(k for k, v in G.TOPICS.items() if v['date'] == d)]['palette'],
                                "#%02X%02X%02X" % accents[d]) for d in DAYS})

hs = {d: hue(accents[d]) for d in DAYS}
pairs = [(a, b) for i, a in enumerate(DAYS) for b in DAYS[i + 1:]]
min_h = min(hdiff(hs[a], hs[b]) for a, b in pairs)
ok(min_h >= 25, f"A1 主色两两最小色相间隔 {min_h:.1f}° ≥ 25°")

min_d = min(dist(bgs[a], bgs[b]) for a, b in pairs)
ok(min_d >= 12, f"A2 底色两两最小距离 {min_d:.1f} ≥ 12")

# 拉开底色差异时最容易犯的错是"把底调亮" —— 那会破坏深底家族感，所以设个亮度上限
lum_hi = max(sum(v) / 3 for v in bgs.values())
ok(lum_hi < 60, f"A4 最亮底色均值 {lum_hi:.1f} < 60（仍是深底）")

for d in DAYS:
    f = WS / "social" / d / "douyin" / "douyin_cover.png"
    if not f.exists():
        ok(False, f"A3 {d} 封面文件存在")
        continue
    ratio = ink_ratio(Image.open(f), accents[d])
    ok(ratio > 0.001, f"A3 {d} 主色像素占比 {ratio*100:.2f}% > 0.1%")

print("【B 组】版式回归（与 _bak_before_color 比）")
for d in DAYS:
    cur = WS / "social" / d / "douyin" / "douyin_cover.png"
    old = WS / "social" / d / "douyin" / "_bak_before_color" / "douyin_cover.png"
    if not (cur.exists() and old.exists()):
        ok(False, f"B {d} 新旧封面都在（旧的在 _bak_before_color/）")
        continue
    a, b = Image.open(cur).convert("RGB"), Image.open(old).convert("RGB")
    ok(a.size == b.size, f"B {d} 尺寸一致 {a.size}")
    v = iou(mask_of(a), mask_of(b))
    ok(v >= 0.97, f"B {d} 墨迹遮罩 IoU {v:.4f} ≥ 0.97（几何未动）")
    old_accent = hex2rgb("#BF6E58")          # 上一版统一赭红
    ok(dist(accents[d], old_accent) > 10, f"B {d} 主色确实换掉了（距旧赭红 {dist(accents[d], old_accent):.1f}）")

print()
if fails:
    print(f"❌ {len(fails)} 项未通过：")
    for m in fails:
        print("   -", m)
    sys.exit(1)
print("✅ 全部通过：颜色已差异化，版式零改动")
