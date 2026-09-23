# -*- coding: utf-8 -*-
"""md2wx.py —— 公众号 Markdown 稿 → 微信兼容 HTML（纯 inline style）

规则（与 ai-news-social-pipeline 排版铁律一致）：
  · 纯 inline style，无 <style> / class / <script> / 外链
  · 只用 background-color，禁止 background 简写
  · 小标题 = 中性深色 + 主题色 4px 左竖线
  · 表格 td 显式写 color
  · 半角引号在转换前统一为全角

用法:
  python md2wx.py <稿.md> [-o <出.html>] [--accent "#37536B"] [--banner "#F2F5F8"]
                   [--eyebrow "深度观察 · AI 工程"]
"""
import argparse
import io
import os
import re
import sys

C_NUM = "#2A2F36"   # 中性深色（标题 / 强调）
C_BODY = "#3D444D"  # 正文
C_MUTE = "#5C6675"  # 次要文字
C_CODE_BG = "#EEF2F6"
C_CODE_FG = "#2C5573"
C_BORDER = "#DCE5ED"

P_STYLE = "margin:0 0 18px 0;color:" + C_BODY + ";"
P_LAST = "margin:0 0 22px 0;color:" + C_BODY + ";"


def read_frontmatter(text):
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.S)
    meta = {}
    if m:
        for line in m.group(1).split("\n"):
            if ":" in line:
                k, v = line.split(":", 1)
                meta[k.strip()] = v.strip()
        body = text[m.end():]
    else:
        body = text
    return meta, body


def fix_quotes(text):
    """把正文里的半角双引号按行内出现顺序配成全角弯引号。"""
    out = []
    for line in text.split("\n"):
        if line.count('"') % 2 == 0 and '"' in line:
            buf, flip = [], 0
            for ch in line:
                if ch == '"':
                    buf.append("\u201c" if flip == 0 else "\u201d")
                    flip ^= 1
                else:
                    buf.append(ch)
            line = "".join(buf)
        out.append(line)
    return "\n".join(out)


def esc(t):
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def inline(t):
    t = esc(t)
    t = re.sub(r"\*\*(.+?)\*\*",
               lambda m: '<strong style="color:%s;">%s</strong>' % (C_NUM, m.group(1)), t)
    t = re.sub(r"`([^`]+)`",
               lambda m: '<code style="background-color:%s;padding:1px 5px;border-radius:4px;'
                         'font-size:13.5px;color:%s;">%s</code>' % (C_CODE_BG, C_CODE_FG, m.group(1)), t)
    return t


def render_table(rows):
    head = rows[0]
    body = rows[2:]
    n = len(head)
    w = round(100.0 / n, 1)
    widths = [w] * n
    widths[-1] = round(100 - w * (n - 1), 1)
    h = []
    h.append('<table style="width:100%;border-collapse:collapse;margin:0 0 20px 0;'
             'font-size:13.5px;line-height:1.7;">')
    h.append("<tr>")
    for i, c in enumerate(head):
        h.append('<td style="width:%s%%;padding:9px 10px;background-color:#F4F7FA;'
                 'border:1px solid %s;color:%s;font-weight:700;">%s</td>'
                 % (widths[i], C_BORDER, C_NUM, inline(c)))
    h.append("</tr>")
    for r in body:
        h.append("<tr>")
        for i, c in enumerate(r):
            h.append('<td style="padding:9px 10px;border:1px solid %s;color:%s;">%s</td>'
                     % (C_BORDER, C_BODY, inline(c)))
        h.append("</tr>")
    h.append("</table>")
    return "".join(h)


def split_row(line):
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|"):
        line = line[:-1]
    return [c.strip() for c in line.split("|")]


def convert(md_path, accent, banner, eyebrow):
    raw = io.open(md_path, encoding="utf-8").read()
    meta, body = read_frontmatter(raw)
    body = fix_quotes(body)

    out = []
    out.append('<section style="background-color:#FFFFFF;padding:0 0 8px 0;font-size:15px;'
               'line-height:1.85;color:%s;">' % C_BODY)
    out.append('')
    out.append('  <section style="background-color:%s;padding:26px 22px;border-radius:8px;'
               'margin:0 0 24px 0;">' % banner)
    out.append('    <p style="margin:0 0 10px 0;font-size:13px;letter-spacing:1px;'
               'color:#7C93A8;">%s</p>' % esc(eyebrow))
    out.append('    <h1 style="margin:0 0 12px 0;font-size:22px;line-height:1.45;'
               'color:%s;font-weight:700;">%s</h1>' % (C_NUM, esc(meta.get("title", ""))))
    desc = meta.get("description", "")
    if desc:
        out.append('    <p style="margin:0;font-size:14px;line-height:1.7;color:%s;">%s</p>'
                   % (C_MUTE, esc(desc)))
    out.append('  </section>')
    out.append('')

    lines = body.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i].rstrip()
        s = line.strip()

        if not s:
            i += 1
            continue

        # 水平线 / 图片
        if re.match(r"^-{3,}$", s):
            i += 1
            continue
        m = re.match(r"^!\[([^\]]*)\]\(([^)]+)\)$", s)
        if m:
            out.append('  <img src="%s" style="width:100%%;display:block;margin:0 0 10px 0;'
                       'border-radius:6px;" alt="%s">' % (m.group(2), esc(m.group(1))))
            out.append('')
            i += 1
            continue

        # 标题
        m = re.match(r"^#{1,6}\s+(.*)$", s)
        if m:
            out.append('  <h2 style="margin:30px 0 16px 0;padding:0 0 0 12px;border-left:4px solid %s;'
                       'font-size:17px;line-height:1.5;color:%s;font-weight:700;">%s</h2>'
                       % (accent, C_NUM, inline(m.group(1))))
            out.append('')
            i += 1
            continue

        # 表格
        if s.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append(split_row(lines[i]))
                i += 1
            if len(rows) >= 2 and re.match(r"^:?-{2,}", rows[1][0]):
                out.append("  " + render_table(rows))
                out.append('')
            continue

        # 列表
        m = re.match(r"^(\d+)\.\s+(.*)$", s)
        if m:
            out.append('  <p style="%s">%s. %s</p>' % (P_STYLE, m.group(1), inline(m.group(2))))
            i += 1
            continue
        if re.match(r"^[-*]\s+", s):
            out.append('  <p style="%s">· %s</p>' % (P_STYLE, inline(re.sub(r"^[-*]\s+", "", s))))
            i += 1
            continue

        # 普通段落（合并连续行）
        buf = [s]
        i += 1
        while i < len(lines):
            nxt = lines[i].strip()
            if (not nxt or nxt.startswith("#") or nxt.startswith("|")
                    or re.match(r"^!\[", nxt) or re.match(r"^[-*]\s+", nxt)
                    or re.match(r"^\d+\.\s+", nxt) or re.match(r"^-{3,}$", nxt)):
                break
            buf.append(nxt)
            i += 1
        # 判断是否本段后面紧跟另一段（用于最后一段的 margin）
        rest = [l.strip() for l in lines[i:] if l.strip()]
        is_last = len(rest) == 0
        out.append('  <p style="%s">%s</p>' % (P_LAST if is_last else P_STYLE,
                                               inline("".join(buf))))
        out.append('')

    out.append('</section>')
    return "\n".join(out), meta


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("md")
    ap.add_argument("-o", "--out")
    ap.add_argument("--accent", default="#37536B")
    ap.add_argument("--banner", default="#F2F5F8")
    ap.add_argument("--eyebrow", default="深度观察 · AI 工程")
    a = ap.parse_args()

    html, meta = convert(a.md, a.accent, a.banner, a.eyebrow)
    out = a.out or os.path.splitext(a.md)[0] + ".html"
    io.open(out, "w", encoding="utf-8", newline="\n").write(html + "\n")
    cjk = len(re.findall(r"[\u4e00-\u9fff]", html))
    print("写出: %s" % out)
    print("HTML 内 CJK = %d" % cjk)
    print("title = %s" % meta.get("title", ""))
    print("title bytes = %d, desc bytes = %d"
          % (len(meta.get("title", "").encode("utf-8")),
             len(meta.get("description", "").encode("utf-8"))))


if __name__ == "__main__":
    main()
