#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""抖音竖版封面 · 差异化插图 + 差异化配色版（1080×1440）

设计取舍：
  · **版式统一、底色统一为深色**，保证刷流里认得出是同一个号；
  · **插图主体每期不同**（2026-09-18 首版）—— 此前各期只有长短条/刻度尺，视觉高度雷同；
  · **配色每期一套**（2026-09-18 追加）—— 客户要求"颜色也做差异化"。
    落点是把原本的全局色板拆成 `PALETTES`，每期挑一套：
    主色（accent）沿色相环分布开，灰调（gray/dim/line/arrow）跟着主色带一点点色相，
    这样"整体色调不同"但不花——底子还是深色 + 一套字重。
    ⚠️ 只有色值变，**坐标/尺寸/字号/线宽一律不动**，否则等于改版式。

**新增一期的做法**（三处）：
  1. `PALETTES` 里加一套色板（或在既有里挑一套）；
  2. 写一个 `illu_xxx(d, f_tiny, P)`：只用 `BOX` / `CX` / `CY` 定坐标。
     函数体**照旧直接写 `ACCENT` / `WHITE` / `GRAY` / `DIM` / `LINE` / `ARROW`** ——
     在函数开头一行把它们从 `P` 解包出来即可（见下），不要在函数体里到处写 `P["..."]`；
  3. 往 `TOPICS` 加一条（date / eyebrow / headline / subtitle / stats / illu / palette）。

用法：
  python gen_douyin_cover_illu.py --list
  python gen_douyin_cover_illu.py --palettes
  python gen_douyin_cover_illu.py --topic line_robot --outdir ./out --prefix douyin
  python gen_douyin_cover_illu.py --all --root <当日/多期根目录>
"""
import argparse
import os

from PIL import Image, ImageDraw, ImageFont

W, H = 1080, 1440
PAD = 96


def _rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


# ---------------------------------------------------------------------------
# 色板：每期一套。统一的是"深底 + 一套字重 + 竖版版式"，
# 变化的是主色及其同色相的灰阶 —— 手机信息流里一眼能区分是哪一篇。
# 主色色相刻意沿色相环拉开：橙红 15° / 琥珀 45° / 青瓷 160° / 靛蓝 210° / 紫罗兰 265°。
# ⚠️ **底色（bg）也算差异化的一部分**，别只换 accent：底色是画面最大面积的那块。
#    但深色底的 RGB 距离天然很小，所以除了换色相还要拉开**明度**——
#    实测教训：最初 ochre #140F0E 与 amber #16110A 只差 4.9，肉眼几乎同色。
#    现在五套底色两两最小距离 ≥16（`verify_cover_color.py` 的 A2 会卡这条）。
# ---------------------------------------------------------------------------
PALETTES = {
    # 09-18 产业分歧 · 赭红 —— 账号原基调，最"重"的一期留给最硬的账
    "ochre": dict(bg="#180B09", ink="#F2ECE9", accent="#CF6F55", soft="#E8A88C",
                  gray="#A6938C", arrow="#8A7671", dim="#4E3A35", line="#2A1C19"),
    # 09-14 长时自主编码 · 靛蓝 —— 冷、疏离，配"没创造任何东西"的虚无
    "indigo": dict(bg="#0A1424", ink="#E8EDF2", accent="#5E93C4", soft="#8FBADF",
                   gray="#8C99A6", arrow="#6E7C8A", dim="#3D4855", line="#1E2833"),
    # 09-15 数据换额度 · 琥珀 —— 交易感 / 标价感（该期为图文，非本人创作）
    "amber": dict(bg="#251B07", ink="#F2EDE2", accent="#D9A227", soft="#EFC96B",
                  gray="#A69A86", arrow="#8C8271", dim="#4A4133", line="#33291A"),
    # 09-16 权限粒度 · 青瓷绿 —— 钥匙与门锁的金属锈绿
    "celadon": dict(bg="#08150F", ink="#E4F0E9", accent="#4EA383", soft="#86C7AC",
                    gray="#86A093", arrow="#6E8A7C", dim="#384A41", line="#17281F"),
    # 09-17 毫秒级循环 · 紫罗兰 —— 电子 / 频率的冷紫
    "violet": dict(bg="#1A0F26", ink="#EDEAF6", accent="#8E7BD4", soft="#B9ACE8",
                   gray="#9690AB", arrow="#7C7595", dim="#443D5C", line="#2A2340"),
    # 09-19 数据边界 · 石板蓝灰 + 玫红 —— 底色比前五套整体提亮一档（均值 35），
    # 与前五期两两最小 RGB 距离 20.6（判据 ≥12）；主色落在色相环空档 ~330°（玫红）
    "slate": dict(bg="#1A222E", ink="#EDF1F6", accent="#CE5B84", soft="#E8A0BC",
                  gray="#9AA6B6", arrow="#7C8899", dim="#3C4759", line="#2A3542"),
}

FONT_DIR = os.environ.get("WINDIR", r"C:\Windows") + r"\Fonts"

BOX = (PAD, 646, W - PAD, 1010)          # 插图区 888 × 364
CX = (BOX[0] + BOX[2]) // 2
CY = (BOX[1] + BOX[3]) // 2


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


def label(d, cx, y, text, f, fill, align="center"):
    l, t, r, b = d.textbbox((0, 0), text, font=f)
    if align == "center":
        d.text((cx - (r - l) / 2 - l, y), text, font=f, fill=fill)
    elif align == "right":
        d.text((cx - (r - l) - l, y), text, font=f, fill=fill)
    else:
        d.text((cx - l, y), text, font=f, fill=fill)


# ---------------------------------------------------------------------------
# 插图主体（各期一个，互不复用）
# 约定：函数开头把当期色板解包成局部变量，函数体照旧写颜色名。
# ---------------------------------------------------------------------------
def illu_two_tags(d, f_tiny, P):
    """09-15：两张价签——一张写着钱，一张写着你的数据。下排是那条额度条。"""
    ACCENT, WHITE, ARROW, LINE, GRAY = P["accent"], P["ink"], P["arrow"], P["line"], P["gray"]
    f_mid = load_font(46, True)
    sy, sh, tw = BOX[1] + 34, 106, 336

    for i, (txt, col) in enumerate([("¥ 0", ACCENT), ("你的数据", WHITE)]):
        x = BOX[0] + 16 + i * 520
        d.rounded_rectangle([x, sy, x + tw, sy + sh], radius=16, outline=col, width=6)
        hx = x + 46
        d.ellipse([hx - 14, sy + sh // 2 - 14, hx + 14, sy + sh // 2 + 14], outline=col, width=5)
        label(d, x + tw // 2 + 34, sy + 26, txt, f_mid, col)

    label(d, CX, sy + 24, "=", f_mid, ARROW)

    # 下排：一条拉满的额度条
    by = BOX[1] + 212
    gx0, gx1 = BOX[0] + 16, BOX[2] - 16
    d.rounded_rectangle([gx0, by, gx1, by + 22], radius=11, fill=LINE)
    d.rounded_rectangle([gx0, by, gx0 + int((gx1 - gx0) * 0.84), by + 22], radius=11, fill=ACCENT)
    label(d, gx0, by + 40, "额度条", f_tiny, GRAY, align="left")
    label(d, gx1, by + 40, "×50", f_tiny, ACCENT, align="right")

    label(d, CX, BOX[3] - 46, "一张写着钱，一张写着你的数据", f_tiny, GRAY)


def illu_code_zero(d, f_tiny, P):
    """09-14：代码堆成山，价值是零。左＝不断增长的代码行，右＝一个空心 0。"""
    ACCENT, WHITE, DIM, ARROW, GRAY = P["accent"], P["ink"], P["dim"], P["arrow"], P["gray"]
    x0 = BOX[0] + 10
    top = BOX[1] + 40
    max_w = 300
    for i in range(15):                       # 代码行：15 条，长度参差
        y = top + i * 14
        w = max_w - abs(i - 7) * 14
        col = ACCENT if i in (5, 10) else (WHITE if 6 <= i <= 9 else DIM)
        d.rounded_rectangle([x0, y, x0 + w, y + 7], radius=3, fill=col)
    label(d, x0 + max_w // 2, BOX[3] - 78, "7.5 万行代码", f_tiny, GRAY)

    # 右：空心 0（环本身就是那个零，不再叠文字）
    rcx, rcy, R = BOX[0] + 700, CY - 30, 118
    d.ellipse([rcx - R, rcy - R, rcx + R, rcy + R], outline=ACCENT, width=16)
    label(d, rcx, BOX[3] - 78, "创造的价值", f_tiny, GRAY)

    # 中间断开的箭头
    ay = rcy
    d.line([x0 + 330, ay, x0 + 470, ay], fill=ARROW, width=5)
    d.polygon([(x0 + 486, ay), (x0 + 458, ay - 12), (x0 + 458, ay + 12)], fill=ARROW)


def illu_keys(d, f_tiny, P):
    """09-16：一条命令一把钥匙。大小不一的一串钥匙挂在同一根环上。"""
    ACCENT, ACCENT_SOFT, DIM, GRAY, LINE = (
        P["accent"], P["soft"], P["dim"], P["gray"], P["line"])
    ring_y = BOX[1] + 46
    x0 = BOX[0] + 60
    d.line([x0, ring_y, BOX[2] - 60, ring_y], fill=LINE, width=6)

    specs = [("大", 52, 128, ACCENT), ("中", 38, 104, ACCENT_SOFT),
             ("中", 38, 104, ACCENT_SOFT), ("中", 38, 104, ACCENT_SOFT),
             ("小", 27, 82, DIM), ("小", 27, 82, DIM), ("小", 27, 82, DIM)]
    x = x0 + 40
    for tag, bw, stem, col in specs:
        bow_r = bw // 2
        # 钥匙环（空心圆）
        d.ellipse([x - bow_r, ring_y + 12, x + bow_r, ring_y + 12 + bw], outline=col, width=7)
        # 钥匙杆
        sy = ring_y + 12 + bw
        d.line([x, sy, x, sy + stem], fill=col, width=8)
        # 齿
        d.line([x, sy + stem - 26, x + 18, sy + stem - 26], fill=col, width=7)
        d.line([x, sy + stem - 10, x + 12, sy + stem - 10], fill=col, width=7)
        x += bw + 72

    label(d, CX, BOX[3] - 62, "会话级授权　→　逐条命令授权", f_tiny, GRAY)


def illu_clocks(d, f_tiny, P):
    """09-17：两个对不上的时钟。上排稀疏脉冲（模型推理），下排密集脉冲（控制回路）。"""
    ACCENT, ACCENT_SOFT, WHITE, DIM, GRAY, LINE = (
        P["accent"], P["soft"], P["ink"], P["dim"], P["gray"], P["line"])
    left = BOX[0] + 10

    ty = BOX[1] + 54                       # 稀疏：5–10 Hz
    for i in range(4):
        x = left + 20 + i * 140
        d.line([x, ty, x, ty + 62], fill=ACCENT, width=12)
    label(d, left, ty + 74, "大脑 · 5–10 Hz", f_tiny, GRAY, align="left")

    by = BOX[1] + 180                      # 密集：267 Hz
    for i in range(34):
        x = left + i * 16
        d.line([x, by, x, by + 62], fill=DIM if i % 3 else ACCENT_SOFT, width=5)
    label(d, left, by + 74, "手 · 267 Hz", f_tiny, ACCENT_SOFT, align="left")

    # 右：时钟
    ccx, ccy, R = BOX[0] + 740, BOX[1] + 158, 108
    d.ellipse([ccx - R, ccy - R, ccx + R, ccy + R], outline=LINE, width=8)
    d.line([ccx, ccy, ccx, ccy - 66], fill=ACCENT, width=9)
    d.line([ccx, ccy, ccx + 48, ccy + 34], fill=ACCENT, width=9)
    d.ellipse([ccx - 8, ccy - 8, ccx + 8, ccy + 8], fill=WHITE)


def illu_line_robot(d, f_tiny, P):
    """09-18：机器人走下产线，后面还有三道关口。"""
    ACCENT, WHITE, DIM, GRAY, LINE = P["accent"], P["ink"], P["dim"], P["gray"], P["line"]
    ly = BOX[2] - 70                       # 产线与地面同高
    d.line([BOX[0] + 6, ly, BOX[0] + 424, ly], fill=ACCENT, width=10)
    for i in range(4):                     # 产线支脚
        x = BOX[0] + 46 + i * 118
        d.line([x, ly, x, ly + 26], fill=LINE, width=5)
    for i in range(10):                    # 产线上的节拍刻度
        x = BOX[0] + 24 + i * 42
        d.line([x, ly - 16, x, ly - 6], fill=DIM, width=4)

    # 机器人（侧面简笔，正迈步走下产线）
    bx = BOX[0] + 524
    d.ellipse([bx - 30, ly - 208, bx + 30, ly - 148], outline=WHITE, width=7)      # 头
    d.line([bx, ly - 148, bx, ly - 140], fill=WHITE, width=6)                      # 颈
    d.rounded_rectangle([bx - 42, ly - 140, bx + 42, ly - 52], radius=16,
                        outline=WHITE, width=7)                                    # 躯干
    d.line([bx + 42, ly - 122, bx + 58, ly - 56], fill=WHITE, width=7)              # 手臂（垂放，与腿明显区分）
    d.line([bx - 6, ly - 52, bx - 44, ly], fill=WHITE, width=8)                    # 后腿
    d.line([bx - 4, ly - 52, bx + 38, ly - 26], fill=ACCENT, width=8)              # 前腿（抬起）
    d.line([bx + 38, ly - 26, bx + 38, ly], fill=ACCENT, width=8)

    # 右侧三道递减横条
    gx0, gx1 = BOX[0] + 626, BOX[2] - 6
    for i, frac in enumerate([1.0, 0.72, 0.46]):
        y = BOX[1] + 74 + i * 66
        d.rounded_rectangle([gx0, y, gx1, y + 14], radius=7, fill=LINE)
        d.rounded_rectangle([gx0, y, gx0 + int((gx1 - gx0) * frac), y + 14], radius=7, fill=ACCENT)

    label(d, CX, BOX[3] - 38, "三道关口：寿命 · 可用率 · 回本周期", f_tiny, GRAY)


def illu_lock_key(d, f_tiny, P):
    """09-19：一把锁 + 一把够不着的钥匙。虚线断开＝钥匙不在你这边。"""
    ACCENT, WHITE, GRAY, ARROW, LINE = (
        P["accent"], P["ink"], P["gray"], P["arrow"], P["line"])
    bw, bh = 300, 216
    bx0 = BOX[0] + 60
    by1 = BOX[1] + 96

    # 锁梁（上半圆）
    d.arc([bx0 + bw // 2 - 78, by1 - 96, bx0 + bw // 2 + 78, by1 + 96],
          start=180, end=360, fill=ACCENT, width=14)
    # 锁体
    d.rounded_rectangle([bx0, by1, bx0 + bw, by1 + bh], radius=18, outline=ACCENT, width=7)
    d.ellipse([bx0 + bw // 2 - 17, by1 + 66, bx0 + bw // 2 + 17, by1 + 100], outline=ACCENT, width=6)
    d.rectangle([bx0 + bw // 2 - 5, by1 + 96, bx0 + bw // 2 + 5, by1 + 142], fill=ACCENT)
    label(d, bx0 + bw // 2, by1 + bh + 12, "313MB  .enc", f_tiny, GRAY)

    # 断开的虚线：够不着
    dy = by1 + bh // 2
    for i in range(6):
        sx = bx0 + bw + 40 + i * 26
        d.line([sx, dy, sx + 13, dy], fill=ARROW, width=5)

    # 钥匙（在右侧远端）
    kx = BOX[2] - 300
    d.ellipse([kx, dy - 46, kx + 92, dy + 46], outline=WHITE, width=11)
    d.line([kx + 92, dy, kx + 232, dy], fill=WHITE, width=15)
    for i in range(3):
        tx = kx + 150 + i * 32
        d.line([tx, dy, tx, dy + 38], fill=WHITE, width=11)
    label(d, kx + 116, dy + 62, "密钥：只在云端", f_tiny, ACCENT)


# ---------------------------------------------------------------------------
# 选题登记表：新增一期只加一条
# ---------------------------------------------------------------------------
TOPICS = {
    "code_zero": dict(
        date="2026-09-14", eyebrow="AI 编程 · 自主编码",
        headline=["7.5 万行代码，", "*没创造任何东西"],
        subtitle="35 小时没人盯着，它换了一副面孔",
        stats="2026-09-14 · 长时自主编码 · machineslop",
        illu=illu_code_zero, palette="indigo",
    ),
    "two_tags": dict(
        date="2026-09-15", eyebrow="AI 编程 · 数据交换",
        headline=["50 倍免费用量，", "*换你的报错记录"],
        subtitle="它不收钱，收的是你怎么把错改对的全过程",
        stats="2026-09-15 · 50 倍额度 · 报错记录换训练",
        illu=illu_two_tags, palette="amber",
    ),
    "keys": dict(
        date="2026-09-16", eyebrow="AI 编程 · 权限粒度",
        headline=["一条命令，", "*一把钥匙"],
        subtitle="授权从会话级，降到命令级",
        stats="2026-09-16 · 7 处权限收口 · 三档选模型",
        illu=illu_keys, palette="celadon",
    ),
    "clocks": dict(
        date="2026-09-17", eyebrow="具身智能 · 工程真相",
        headline=["机器人抖，", "*真不怪它笨"],
        subtitle="卡的是两个对不上的时钟",
        stats="5–10 Hz 推理 vs 267 Hz 控制 · 差 30–50 倍",
        illu=illu_clocks, palette="violet",
    ),
    "line_robot": dict(
        date="2026-09-18", eyebrow="具身智能 · 产业分歧",
        headline=["能走下产线，", "*不等于能赚钱"],
        subtitle="近 20 家车企入局造人，有人先算了笔账",
        stats="关节寿命 1–3 个月 · 回收期 1.5–3 年",
        illu=illu_line_robot, palette="ochre",
    ),
    "zcode_pack": dict(
        date="2026-09-19", eyebrow="AI 编程 · 数据边界",
        headline=["加密了，", "*钥匙不在你手上"],
        subtitle="一个 313MB 的加密包，躺在程序员硬盘上",
        stats="2026-09-19 · 近九成是 .git 历史 · 564 次上传重试",
        illu=illu_lock_key, palette="slate",
    ),
}


def render(topic_key):
    cfg = TOPICS[topic_key]
    pal = cfg.get("palette", "ochre")
    if pal not in PALETTES:
        raise KeyError(f"未知色板 {pal!r}，可选：{sorted(PALETTES)}")
    P = {k: _rgb(v) for k, v in PALETTES[pal].items()}
    BG, WHITE, ACCENT, GRAY, LINE = P["bg"], P["ink"], P["accent"], P["gray"], P["line"]

    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    f_eye = load_font(40, True)
    f_head = load_font(86, True)
    f_sub = load_font(40)
    f_stats = load_font(32)
    f_tiny = load_font(26)

    d.rectangle([PAD, 118, PAD + 74, 126], fill=ACCENT)
    d.text((PAD, 152), cfg["eyebrow"], font=f_eye, fill=ACCENT)

    y = 330
    for line in cfg["headline"]:
        col = ACCENT if line.startswith("*") else WHITE
        d.text((PAD, y), line.lstrip("*"), font=f_head, fill=col)
        y += 118

    d.rectangle([PAD, 640, W - PAD, 642], fill=LINE)
    cfg["illu"](d, f_tiny, P)
    d.rectangle([PAD, 1016, W - PAD, 1018], fill=LINE)

    d.text((PAD, 1090), cfg["subtitle"], font=f_sub, fill=GRAY)
    d.line([PAD, 1190, W - PAD, 1190], fill=LINE, width=2)
    d.text((PAD, 1230), cfg["stats"], font=f_stats, fill=GRAY)
    return img


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true", help="列出已登记的选题")
    ap.add_argument("--palettes", action="store_true", help="列出所有色板及其被哪几期使用")
    ap.add_argument("--topic", help="选题 key")
    ap.add_argument("--outdir", default=".")
    ap.add_argument("--prefix", default="douyin")
    ap.add_argument("--all", action="store_true", help="渲染全部选题，写入 <root>/<date>/douyin/")
    ap.add_argument("--root", help="多期根目录（social 目录），配合 --all")
    a = ap.parse_args()

    if a.palettes:
        used = {}
        for k, v in TOPICS.items():
            used.setdefault(v.get("palette"), []).append(v["date"])
        for name, cols in PALETTES.items():
            days = " ".join(sorted(used.get(name, []))) or "（未使用）"
            print(f"{name:9s} accent={cols['accent']} bg={cols['bg']}  用于 {days}")
        return 0

    if a.list:
        for k, v in TOPICS.items():
            print(f"{k:12s} {v['date']}  [{v.get('palette')}]  "
                  f"{' / '.join(x.lstrip('*') for x in v['headline'])}")
        return 0

    if a.all:
        if not a.root:
            print("ERROR: --all 需要 --root")
            return 1
        for k, v in TOPICS.items():
            outdir = os.path.join(a.root, v["date"], "douyin")
            os.makedirs(outdir, exist_ok=True)
            img = render(k)
            for name in ("douyin_cover.png", "douyin_head.png"):
                p = os.path.join(outdir, name)
                img.save(p, "PNG")
                print("saved:", p)
        return 0

    if not a.topic:
        print("ERROR: 需要 --topic 或 --all（--list 查看可选）")
        return 1
    os.makedirs(a.outdir, exist_ok=True)
    img = render(a.topic)
    for name in (f"{a.prefix}_cover.png", f"{a.prefix}_head.png"):
        p = os.path.join(a.outdir, name)
        img.save(p, "PNG")
        print("saved:", p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
