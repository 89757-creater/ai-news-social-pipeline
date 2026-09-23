# -*- coding: utf-8 -*-
"""2026-09-23 选题配图生成（纯 Pillow，无 cairosvg 依赖）。

选题：你点的是 Opus 5.5，跑的可能不是它
      —— Anthropic 把「安全」做成了一次透明的模型路由

产出：
  cover.png                 900x383   公众号封面（浅色系，底色与正文顶部横幅同源 #F2F5FA）
  assets/fig_a_routes.png   1200x620  一道请求，三道关卡，两个出口
  assets/fig_b_three.png    1200x620  同一套机制，三种行为（官方应用 / API 未开启 / API 已开启）
  douyin/douyin_cover.png   1080x1440 抖音竖版封面（深色底 + 本期主色）
  douyin/douyin_head.png    1080x1440 抖音文章头图（同版式）

公众号色板（与稿件主题色同源，banner #F2F5FA / accent #34527A）：
  BG #F2F5FA / INK #2A2F36 / BODY #3D444D / BAR #34527A / DEEP #2A4462
  CHIP #E7ECF4 / MUTED #8B95A3 / LIGHT #DCE5ED / LINE #CFDBE5 / WARN #B4533F

抖音侧本期色板 "lagoon"（第十套，主色取 183°）：
  bg #0C202E / accent #41D1D9
  底色三通道均值 (12+32+46)/3 = 30.0 < 60（深色护栏）
  与已用九套底色的最小 RGB 距离 = 14.1（vs slate #1A222E）
  主色最小色相间隔 = 25.6°（vs indigo #5E93C4, 208.8°）

  选色过程留痕：首版取 102° 的青柠绿（#78D750），自检报与 fern #6ECD60 仅差 10.1° 而 FAIL
  —— 原因是先前手算把 fern 的色相记成 127.7°，实为 112.3°。改用脚本实测后，
  已用九套的最大色相空档在 157.4°→208.8°（51.4°）与 112.3°→157.4°（45.1°），
  取后者偏青端定在 183°。**手算色相不可靠，一律以 self_check 输出为准。**
"""
import argparse
import colorsys
import math
import os

from PIL import Image, ImageDraw, ImageFont

FONT_DIR = os.environ.get("WINDIR", r"C:\Windows") + r"\Fonts"

BG = (242, 245, 250)
INK = (42, 47, 54)
BODY = (61, 68, 77)
BAR = (52, 82, 122)
DEEP = (42, 68, 98)
CHIP = (231, 236, 244)
MUTED = (139, 149, 163)
LIGHT = (220, 229, 237)
LINE = (207, 219, 229)
WARN = (180, 83, 63)
WHITE = (255, 255, 255)

# 抖音：本期色板 lagoon
DY_BG = (12, 32, 46)
DY_INK = (238, 244, 246)
DY_ACCENT = (65, 209, 217)
DY_SOFT = (150, 215, 220)
DY_GRAY = (148, 166, 176)
DY_DIM = (26, 60, 78)
DY_LINE = (30, 62, 78)

# 已用九套（用于自检）
USED_BG = [(10, 20, 36), (37, 27, 7), (8, 21, 15), (26, 15, 38),
           (24, 11, 9), (26, 34, 46), (54, 31, 56), (16, 32, 28), (36, 20, 24)]
USED_ACCENT = [(94, 147, 196), (217, 162, 39), (78, 163, 131), (142, 123, 212),
               (207, 111, 85), (206, 91, 132), (198, 106, 204), (169, 194, 74),
               (110, 205, 96)]


def hue(rgb):
    r, g, b = [v / 255.0 for v in rgb]
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    return h * 360.0


def dist(a, b):
    return sum((x - y) ** 2 for x, y in zip(a, b)) ** 0.5


def self_check():
    h0 = hue(DY_ACCENT)
    dh = min(min(abs(h0 - hue(c)), 360 - abs(h0 - hue(c))) for c in USED_ACCENT)
    db = min(dist(DY_BG, c) for c in USED_BG)
    mean = sum(DY_BG) / 3.0
    print("[自检] lagoon 主色 hue=%.1f°, 与已用九套最小间隔=%.1f° (≥25 期望)" % (h0, dh))
    print("[自检] lagoon 底色与已用九套最小 RGB 距离=%.1f (≥12 期望)" % db)
    print("[自检] lagoon 底色均值=%.1f (<60 期望)" % mean)
    ok = dh >= 25 and db >= 12 and mean < 60
    print("[自检] 结论：%s" % ("PASS" if ok else "FAIL"))
    return ok


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


def center_text(d, cx, y, text, f, fill):
    l, t, r, b = d.textbbox((0, 0), text, font=f)
    d.text((cx - (r - l) / 2 - l, y), text, font=f, fill=fill)


def label(d, cx, y, text, f, fill, align="center"):
    l, t, r, b = d.textbbox((0, 0), text, font=f)
    if align == "center":
        d.text((cx - (r - l) / 2 - l, y), text, font=f, fill=fill)
    elif align == "right":
        d.text((cx - (r - l) - l, y), text, font=f, fill=fill)
    else:
        d.text((cx - l, y), text, font=f, fill=fill)


def tw(d, text, f):
    l, t, r, b = d.textbbox((0, 0), text, font=f)
    return r - l


def dashed_line(d, x0, y0, x1, y1, fill, width=4, dash=16, gap=12):
    total = math.hypot(x1 - x0, y1 - y0)
    if total == 0:
        return
    ux, uy = (x1 - x0) / total, (y1 - y0) / total
    pos = 0.0
    while pos < total:
        seg = min(dash, total - pos)
        d.line([x0 + ux * pos, y0 + uy * pos, x0 + ux * (pos + seg), y0 + uy * (pos + seg)],
               fill=fill, width=width)
        pos += dash + gap


def arrow(d, x0, y0, x1, y1, fill, width=4, head=12):
    """任意方向的实心箭头（箭头尖端落在 x1,y1）。"""
    total = math.hypot(x1 - x0, y1 - y0)
    if total == 0:
        return
    ux, uy = (x1 - x0) / total, (y1 - y0) / total
    bx, by = x1 - ux * head, y1 - uy * head
    d.line([x0, y0, bx, by], fill=fill, width=width)
    px, py = -uy, ux
    d.polygon([(x1, y1),
               (bx + px * head * 0.62, by + py * head * 0.62),
               (bx - px * head * 0.62, by - py * head * 0.62)], fill=fill)


def chip(d, x, y, text, f, pad_x=13, pad_y=7, fill=CHIP, tcol=DEEP):
    l, t, r, b = d.textbbox((0, 0), text, font=f)
    d.rounded_rectangle([x, y, x + (r - l) + pad_x * 2, y + (b - t) + pad_y * 2], radius=5, fill=fill)
    d.text((x + pad_x - l, y + pad_y - t), text, font=f, fill=tcol)
    return x + (r - l) + pad_x * 2 + 10


# ----------------------------------------------------------------------------
# 公众号封面（900x383，浅色系，底色与正文顶部横幅同源 #F2F5FA）
# ----------------------------------------------------------------------------
def cover(path):
    W, H = 900, 383
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    f_eye = load_font(19)
    f_title = load_font(44, bold=True)
    f_sub = load_font(20)
    f_pill = load_font(16)
    f_mini = load_font(15)

    left, y = 54, 52
    chip(d, left, y, "深度观察 · AI 工程", f_eye)
    y += 52

    bar_top = y + 6
    for line in ["你点的是 Opus 5.5，", "跑的可能不是它"]:
        d.text((left, y), line, font=f_title, fill=INK)
        y += 58
    d.rectangle([left - 18, bar_top, left - 14, y - 14], fill=BAR)

    y += 2
    d.text((left, y), "一条脚注，改写了「你调用的是谁」", font=f_sub, fill=BODY)

    # 右侧迷你路由图：一个入口 → 两个出口（实线大 / 虚线小）
    # 右边界硬约束：exx + 172 ≤ 846（留 54 边距），故 ex 取 520 → exx = 658 → 框止于 830
    ex, ey = 520, 148
    d.rounded_rectangle([ex, ey, ex + 96, ey + 40], radius=6, fill=DEEP)
    d.text((ex + 14, ey + 8), "请求", font=f_mini, fill=WHITE)

    d.line([ex + 96, ey + 20, ex + 138, ey + 20], fill=BAR, width=3)
    exx = 138 + ex
    d.line([exx, ey + 20, exx, ey - 40], fill=BAR, width=3)
    d.line([exx, ey + 20, exx, ey + 80], fill=MUTED, width=3)

    d.line([exx, ey - 40, exx + 30, ey - 40], fill=BAR, width=3)
    d.rounded_rectangle([exx + 30, ey - 58, exx + 172, ey - 22], radius=6, fill=BAR)
    d.text((exx + 42, ey - 54), "Opus 5.5", font=f_mini, fill=WHITE)

    dashed_line(d, exx, ey + 80, exx + 30, ey + 80, fill=MUTED, width=3, dash=10, gap=8)
    d.rounded_rectangle([exx + 30, ey + 62, exx + 172, ey + 98], radius=6,
                        fill=LIGHT, outline=LINE, width=2)
    d.text((exx + 42, ey + 66), "Opus 4.8", font=f_mini, fill=BODY)

    # 说明文字放在两个出口框之间的空隙里（y 124–212 为空），不再压到画布边缘
    label(d, exx + 30, ey + 6, "命中分类器", f_mini, MUTED, align="left")

    px, py = left, H - 60
    for item in ["同一套机制", "API 端可选", "200 也能是拒绝"]:
        px = chip(d, px, py, item, f_pill)

    img.save(path, "PNG")
    return path


# ----------------------------------------------------------------------------
# fig_a：一道请求，三道关卡，两个出口
# ----------------------------------------------------------------------------
def fig_a(path):
    W, H = 1200, 620
    img = Image.new("RGB", (W, H), WHITE)
    d = ImageDraw.Draw(img)

    f_title = load_font(32, bold=True)
    f_step = load_font(21, bold=True)
    f_item = load_font(17)
    f_tag = load_font(16)
    f_note = load_font(17)
    f_small = load_font(16)

    center_text(d, W // 2, 32, "一道请求，三道关卡，两个出口", f_title, INK)
    d.rectangle([W // 2 - 46, 80, W // 2 + 46, 84], fill=BAR)

    # 三道关卡
    gates = [
        ("① 探针", ["读模型的内部激活", "全部流量过一遍", "标出疑似涉网安内容"]),
        ("② 轻量分类器", ["跑在 Opus 5.5 自己身上", "给被标出的内容打分", "判为可能违规即上交"]),
        ("③ 独立分类器", ["换一个模型来复核", "与①的结论合议", "决定放行或转交"]),
    ]
    x0, top, bot = 60, 118, 300
    gw, gap = 340, 30
    for i, (name, items) in enumerate(gates):
        lx = x0 + i * (gw + gap)
        rx = lx + gw
        d.rounded_rectangle([lx, top, rx, bot], radius=12, fill=BG)
        d.rectangle([lx, top, rx, top + 6], fill=BAR)
        d.text((lx + 22, top + 22), name, font=f_step, fill=INK)
        for j, it in enumerate(items):
            d.text((lx + 22, top + 62 + j * 34), "· " + it, font=f_item, fill=BODY)
        if i:
            arrow(d, lx - gap + 4, (top + bot) // 2, lx - 4, (top + bot) // 2, BAR, width=3, head=10)

    # 两个出口
    oy0, oy1 = 336, 452
    ow = 520
    outs = [
        (60, "出口 A · 放行", "留在 Opus 5.5", ["源代码里找漏洞：允许", "所有访问档位一致"], BAR, WHITE, WHITE),
        (620, "出口 B · 转交", "交给更旧的模型", ["网安类 → Opus 4.8", "生物与前沿研发 → Opus 5"], CHIP, INK, BODY),
    ]
    for lx, name, lead, items, fill, ncol, icol in outs:
        d.rounded_rectangle([lx, oy0, lx + ow, oy1], radius=12, fill=fill)
        d.text((lx + 22, oy0 + 18), name, font=f_step, fill=ncol)
        d.text((lx + 22, oy0 + 56), lead, font=f_tag, fill=icol)
        for j, it in enumerate(items):
            d.text((lx + 262, oy0 + 22 + j * 32), "· " + it, font=f_item, fill=icol)

    arrow(d, 60 + 190, 304, 60 + 190, 332, BAR, width=3, head=9)
    arrow(d, 620 + 190, 304, 620 + 190, 332, BAR, width=3, head=9)

    # 提示栏
    n0, n1 = 480, 566
    d.rounded_rectangle([60, n0, W - 60, n1], radius=10, fill=BG)
    d.text((80, n0 + 14), "政策线不在「模型会不会」上，在「你让它对什么做」上：",
           font=f_note, fill=INK)
    d.text((80, n0 + 44), "同一件事，对源代码放行，对编译好的二进制拦住。", font=f_note, fill=BODY)

    d.text((60, 580), "机制与政策线均据 Anthropic 官方模型卡，经 The New Stack 与 ThreatFrontier 独立引述。",
           font=f_small, fill=MUTED)

    img.save(path, "PNG")
    return path


# ----------------------------------------------------------------------------
# fig_b：同一套机制，三种行为
# ----------------------------------------------------------------------------
def fig_b(path):
    W, H = 1200, 620
    img = Image.new("RGB", (W, H), WHITE)
    d = ImageDraw.Draw(img)

    f_title = load_font(32, bold=True)
    f_step = load_font(21, bold=True)
    f_item = load_font(17)
    f_big = load_font(30, bold=True)
    f_note = load_font(17)
    f_small = load_font(16)

    center_text(d, W // 2, 32, "同一套机制，三种行为", f_title, INK)
    d.rectangle([W // 2 - 46, 80, W // 2 + 46, 84], fill=BAR)

    cols = [
        ("官方应用", "自动", "命中即回退，不需要你做任何事", BAR, WHITE, WHITE),
        ("API · 未开启回退", "不换", "请求被拦后照原样返回", LIGHT, INK, BODY),
        ("API · 已开启回退", "重试", "在官方推荐的模型上再来一次", CHIP, INK, BODY),
    ]
    x0, top, bot = 60, 118, 372
    cw, gap = 340, 30
    for i, (name, big, lead, fill, ncol, icol) in enumerate(cols):
        lx = x0 + i * (cw + gap)
        d.rounded_rectangle([lx, top, lx + cw, bot], radius=12, fill=fill)
        d.rectangle([lx, top, lx + cw, top + 6], fill=BAR)
        d.text((lx + 24, top + 24), name, font=f_step, fill=ncol)
        center_text(d, lx + cw // 2, top + 76, big, f_big, ncol if fill is BAR else DEEP)
        d.line([lx + 70, top + 128, lx + cw - 70, top + 128], fill=LINE, width=2)
        # 折行显示说明
        words = lead
        d.text((lx + 24, top + 148), words[:15], font=f_item, fill=icol)
        if len(words) > 15:
            d.text((lx + 24, top + 178), words[15:30], font=f_item, fill=icol)
        if len(words) > 30:
            d.text((lx + 24, top + 208), words[30:], font=f_item, fill=icol)

    # HTTP 200 特写
    b0, b1 = 400, 528
    d.rounded_rectangle([60, b0, W - 60, b1], radius=12, fill=BG)
    d.rectangle([60, b0, 68, b1], fill=WARN)
    d.text((96, b0 + 20), "最容易漏掉的一处：被拦下的 API 请求，以 HTTP 200 返回",
           font=f_note, fill=INK)
    d.text((96, b0 + 54), "正文里才是「拒绝」——只看状态码的监控、重试与计费逻辑，会把它记成一次成功调用。",
           font=f_note, fill=BODY)
    d.text((96, b0 + 88), "多轮流程里，不同步骤还可能由能力不同的模型处理，而这种不一致未必出现在成绩单上。",
           font=f_note, fill=BODY)

    d.text((60, 548), "据 The New Stack（2026-09-22）与 ThreatFrontier 同日分析；接口形态以官方文档为准。",
           font=f_small, fill=MUTED)

    img.save(path, "PNG")
    return path


# ----------------------------------------------------------------------------
# 抖音竖版封面 / 头图（1080x1440，深色底 + 本期主色）
# ----------------------------------------------------------------------------
def illu_route(d, f_tiny):
    """本期插图：上面是你点名的模型，下面是可能实际执行的模型，虚线相连。"""
    ACCENT, INK, GRAY, DIM, LINE = DY_ACCENT, DY_INK, DY_GRAY, DY_DIM, DY_LINE

    bx, bw = 240, 600

    # 上框：你点的
    t0, t1 = 588, 712
    d.rounded_rectangle([bx, t0, bx + bw, t1], radius=12, fill=DY_BG, outline=ACCENT, width=4)
    d.text((bx + 28, t0 + 24), "你点名的模型", font=f_tiny, fill=GRAY)
    d.text((bx + 28, t0 + 62), "Opus 5.5", font=f_tiny, fill=ACCENT)

    # 虚线
    dashed_line(d, bx + bw // 2, t1 + 6, bx + bw // 2, t1 + 92, fill=ACCENT, width=4, dash=14, gap=10)

    # 虚线旁标签：改挂到虚线右侧的空白带（原写法 bx+bw+34 会顶出 1080 边界）
    tag = "被分类器命中的请求"
    l, t_, r, b_ = d.textbbox((0, 0), tag, font=f_tiny)
    tx = bx + bw // 2 + 30
    d.text((tx, t1 + 26), tag, font=f_tiny, fill=GRAY)

    # 下框：可能执行的
    b0, b1 = t1 + 100, t1 + 224
    d.rounded_rectangle([bx, b0, bx + bw, b1], radius=12, fill=DIM, outline=LINE, width=3)
    d.text((bx + 28, b0 + 24), "可能实际执行的", font=f_tiny, fill=GRAY)
    d.text((bx + 28, b0 + 62), "Opus 4.8", font=f_tiny, fill=INK)


def douyin(path, headline, eyebrow, subtitle, stats, checks):
    W, H = 1080, 1440
    PAD = 96
    img = Image.new("RGB", (W, H), DY_BG)
    d = ImageDraw.Draw(img)

    f_eye = load_font(40, bold=True)
    f_head = load_font(80, bold=True)
    f_sub = load_font(38)
    f_stats = load_font(30)
    f_gate = load_font(27)
    f_tiny = load_font(26)

    d.rectangle([PAD, 118, PAD + 74, 126], fill=DY_ACCENT)
    d.text((PAD, 152), eyebrow, font=f_eye, fill=DY_ACCENT)

    y = 316
    for line in headline:
        color = DY_ACCENT if line.startswith("*") else DY_INK
        d.text((PAD, y), line.lstrip("*"), font=f_head, fill=color)
        y += 112

    illu_route(d, f_tiny)

    d.text((PAD, 1092), subtitle, font=f_sub, fill=DY_GRAY)
    d.line([PAD, 1168, W - PAD, 1168], fill=DY_LINE, width=2)
    for i, txt in enumerate(checks):
        cy = 1204 + i * 50
        d.rounded_rectangle([PAD, cy + 12, PAD + 10, cy + 22], radius=5, fill=DY_ACCENT)
        d.text((PAD + 26, cy), txt, font=f_gate, fill=DY_GRAY)
    d.text((PAD, 1376), stats, font=f_stats, fill=DY_GRAY)

    img.save(path, "PNG")
    return path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True, help="当日产出目录绝对路径")
    a = ap.parse_args()

    self_check()

    print("saved:", cover(os.path.join(a.root, "cover.png")))

    assets = os.path.join(a.root, "assets")
    douyin_dir = os.path.join(a.root, "douyin")
    os.makedirs(assets, exist_ok=True)
    os.makedirs(douyin_dir, exist_ok=True)

    print("saved:", fig_a(os.path.join(assets, "fig_a_routes.png")))
    print("saved:", fig_b(os.path.join(assets, "fig_b_three.png")))

    headline = ["你点的是 Opus 5.5，", "*跑的可能不是它"]
    eyebrow = "AI 工程 · 安全路由"
    subtitle = "自家应用自动换，API 要你自己开"
    stats = "被标红的请求 → 交给更旧的模型"
    checks = [
        "你点名的模型，不一定是执行的模型",
        "被拒绝的请求，以 HTTP 200 返回",
        "回退到的旧模型，抗注入更弱",
    ]

    print("saved:", douyin(os.path.join(douyin_dir, "douyin_cover.png"),
                           headline, eyebrow, subtitle, stats, checks))
    print("saved:", douyin(os.path.join(douyin_dir, "douyin_head.png"),
                           headline, eyebrow, subtitle, stats, checks))


if __name__ == "__main__":
    main()
