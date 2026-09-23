#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成「抖音文章 · 配乐分配核对表」一张图，用于交付与验收。

数据是**硬编码的本轮事实**（2026-09-18 用户要求「每篇不同轻松忧郁纯音乐、不要太清」），
不是从页面抓的 —— 因为抖音作品列表**不显示配乐**，只能靠发稿时的回读日志作证。
若要重跑，改下面的 ROWS 即可。

排版约束（踩过的坑）：曲名最长的一条 `Batmirtt Zarell` 会与右侧状态标签**横向重叠**，
标题两行会**溢出卡片底边**。所以这里用固定列宽 + `shrink_to_fit()` 兜底，不靠估算。
"""
import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

WS = Path(r"C:/Users/suge0/WorkBuddy/automation-2026-09-13-16-27-29")
OUT = WS / "douyin_bgm_sheet.png"

FONT_DIR = os.environ.get("WINDIR", r"C:\Windows") + r"\Fonts"


def load_font(size, bold=False):
    names = ["msyhbd.ttc", "msyh.ttc", "simhei.ttf"] if bold else ["msyh.ttc", "msyhbd.ttc", "simsun.ttc"]
    for n in names:
        p = os.path.join(FONT_DIR, n)
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:  # noqa: BLE001
                continue
    return ImageFont.load_default()


BG = (245, 243, 239)
CARD = (255, 255, 255)
INK = (26, 26, 28)
GRAY = (122, 120, 116)
LINE = (226, 222, 214)
ACCENT = (178, 58, 46)
OK = (46, 122, 74)

ROWS = [
    ("2026-09-14", "AI 写了 7.5 万行代码，\n却说没创造任何东西", "无人的旷野", "Matrix Tone · 空旷冷寂（飙升榜）",
     "已发布", "配「活了 35 小时却没创造任何东西」的虚无"),
    ("2026-09-16", "AI 装个依赖包，\n为什么顺手开了整栋楼的门", "Batmirtt Zarell", "jony · 现代氛围（纯音乐）",
     "已发布", "配「权限一放开就收不回」的失控感"),
    ("2026-09-17", "机器人抖，真不怪它笨", "Meyjan", "T3NZU · 电子凉感（纯音乐）",
     "已发布", "配毫秒级循环里那点无奈的机械感"),
    ("2026-09-18", "机器人能走下产线，\n但还赚不了钱", "Betkol NATEN", "jony · 低沉行进（纯音乐）",
     "已发布", "配「能干活了、账还没算清」的反差；\n发布曾被配额拒绝，09-19 10:24 补发成功"),
    ("2026-09-19", "加密了，但钥匙不在你手上", "轻音乐（释怀）", "赵东俊 · 冷静克制（热门榜）",
     "已发布", "配「加密了却打不开」的取证复盘；\n发稿日志回读：选择配乐 | 轻音乐（释怀） | 02:23"),
]

W = 1240
PAD = 64
HEAD = 250
ROW_H = 172
FOOT = 210
H = HEAD + ROW_H * len(ROWS) + FOOT

img = Image.new("RGB", (W, H), BG)
d = ImageDraw.Draw(img)

f_title = load_font(58, True)
f_sub = load_font(29)
f_meta = load_font(25)
f_date = load_font(28, True)
f_name = load_font(35, True)
f_music = load_font(40, True)
f_musmeta = load_font(24)
f_stat = load_font(28, True)
f_why = load_font(24)
f_foot = load_font(24)

CONTENT_R = W - PAD


def fit(text, size, bold, max_w):
    """把字号缩到能放进 max_w；返回 (font, 实际宽度)。"""
    while size > 16:
        f = load_font(size, bold)
        w = d.textlength(text, font=f)
        if w <= max_w:
            return f, w
        size -= 1
    f = load_font(16, bold)
    return f, d.textlength(text, font=f)


def wrap(text, font, max_w):
    """按字符宽度折行（中文无空格，逐字累加）。

    ⚠️ 必须先把作者写死的 `\n` 拆开：`textlength()` 遇到多行文本会直接
    `ValueError: can't measure length of multiline text`（2026-09-18 踩到）。
    """
    lines = []
    for para in text.split("\n"):
        cur = ""
        for ch in para:
            if d.textlength(cur + ch, font=font) > max_w and cur:
                lines.append(cur)
                cur = ch
            else:
                cur += ch
        lines.append(cur) if cur else None
    return lines


# ── 页头
d.text((PAD, 52), "抖音文章 · 配乐分配核对表", font=f_title, fill=INK)
# 副标题/元信息都可能超宽（2026-09-18 出过一次右侧被裁）→ 统一用 fit() 自适应缩字号
_sub = "5 篇本人创作作品（09-14 / 16 / 17 / 18 / 19），每篇一首互不复用的现代风格纯音乐（已排除太清 TaiQing 与全部古风曲）"
_meta = "2026-09-18 删除旧作后重发 —— 抖音「文章」发布后没有编辑入口，配乐只能在重发那一刻写入"
f_sub2, _ = fit(_sub, 29, False, CONTENT_R - PAD)
f_meta2, _ = fit(_meta, 22, False, CONTENT_R - PAD)
d.text((PAD, 132), _sub, font=f_sub2, fill=GRAY)
d.text((PAD, 174), _meta, font=f_meta2, fill=GRAY)
d.line([(PAD, HEAD - 30), (CONTENT_R, HEAD - 30)], fill=LINE, width=2)

# 列坐标
C_DATE = PAD + 46
W_DATE = 176
C_NAME = C_DATE + W_DATE
W_NAME = 452
C_MUSIC = C_NAME + W_NAME
W_MUSIC = CONTENT_R - C_MUSIC - 24

y = HEAD
for date, title, music, musmeta, status, why in ROWS:
    top, bot = y + 8, y + ROW_H - 10
    d.rounded_rectangle([PAD, top, CONTENT_R, bot], radius=18, fill=CARD, outline=LINE, width=2)
    d.rounded_rectangle([PAD + 18, top + 22, PAD + 26, bot - 22], radius=4, fill=ACCENT)

    inner = top + 22
    d.text((C_DATE, inner), date, font=f_date, fill=GRAY)
    col = OK if status == "已发布" else ACCENT
    d.text((C_DATE, inner + 42), status, font=f_stat, fill=col)

    d.multiline_text((C_NAME, inner + 4), title, font=f_name, fill=INK, spacing=12)

    f_m, w_m = fit(music, 40, True, W_MUSIC)
    d.text((C_MUSIC, inner + 6), music, font=f_m, fill=ACCENT)
    d.text((C_MUSIC, inner + 58), musmeta, font=f_musmeta, fill=GRAY)
    for i, ln in enumerate(wrap(why, f_why, W_MUSIC)[:2]):
        d.text((C_MUSIC, inner + 92 + i * 30), ln, font=f_why, fill=GRAY)

    y += ROW_H

# ── 脚注
d.line([(PAD, y + 12), (CONTENT_R, y + 12)], fill=LINE, width=2)
NOTES = [
    "另：2026-09-15「茧中茧，信息套时代」为图文体裁、非本轮改动对象，未纳入本表。",
    "配乐生效依据：发稿日志中的「当前配乐区」DOM 回读（如「选择配乐 | Batmirtt Zarell | 02:29 | 修改音乐」），"
    "以及发布前检查（封面/配乐均已生效）—— 五篇均通过。",
    "2026-09-18 那篇：09-18 晚首次重发被服务端以 status_code=536「今日发布10次长图文，已达上限」拒绝，"
    "稿子保留在编辑器；09-19 10:24 补发成功，接口返回 status_code=0，终检「作品数 5（期望 5）」。",
    "提示：抖音作品列表不展示配乐，故配乐信息以发稿日志为唯一凭证。",
]
yy = y + 38
for note in NOTES:
    for ln in wrap(note, f_foot, CONTENT_R - PAD):
        d.text((PAD, yy), ln, font=f_foot, fill=GRAY)
        yy += 32
    yy += 4

img.save(OUT)
print("saved:", OUT, img.size)
