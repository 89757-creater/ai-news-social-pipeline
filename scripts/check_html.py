# -*- coding: utf-8 -*-
"""公众号 HTML 稿排版自检（技能 fact-check-rules.md 末节的必查项）。

用法：
    python check_html.py <html 绝对路径> [--title "标题"] [--expect 关键词1 关键词2 ...]

说明：
    · 前 9 项为**通用排版铁律**：纯 inline style / 禁背景简写 / 全角引号 / 标签配对 / 无外链。
    · 「必含章节」为通用结构检查（数据来源 / 免责声明 / 评论区引导），每天适用。
    · 选题特有的「关键数字是否落地」用 --expect 传入，**不要写死在脚本里**
      （2026-09-18 修正：原版把某一天的关键词硬编码进来，换选题后必然 FAIL，
        属于脚本自身的缺陷，非稿件问题）。

输出每项 PASS/FAIL；有 FAIL 时退出码 1。
"""
import argparse
import re
import sys

from html.parser import HTMLParser

# 每期稿件都应出现的结构段（正文里的标题文字）
REQUIRED_SECTIONS = ["数据来源", "免责声明"]


class Pair(HTMLParser):
    VOID = {"img", "br", "hr", "meta", "input", "link"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.errors = []

    def handle_starttag(self, tag, attrs):
        if tag in self.VOID:
            return
        self.stack.append(tag)

    def handle_endtag(self, tag):
        if tag in self.VOID:
            return
        if not self.stack:
            self.errors.append(f"多余的闭合标签 </{tag}>")
            return
        if self.stack[-1] != tag:
            self.errors.append(f"标签不配对：期望 </{self.stack[-1]}>，实际 </{tag}>")
            if tag in self.stack:
                while self.stack and self.stack.pop() != tag:
                    pass
            return
        self.stack.pop()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("html", help="HTML 稿绝对路径")
    ap.add_argument("--title", default=None, help="稿件标题，用于校验字数与字节")
    ap.add_argument("--expect", nargs="*", default=[], help="本篇必含的关键词/数字，逐项检查是否出现")
    a = ap.parse_args()

    src = open(a.html, encoding="utf-8").read()
    checks = []

    def add(name, count, ok=None):
        good = (count == 0) if ok is None else ok
        checks.append((name, count, good))

    # ---- 排版铁律 ----
    add("<style> 标签", src.count("<style"))
    add("class= 属性", len(re.findall(r'\bclass\s*=', src)))
    add("<script> 标签", src.count("<script"))
    add("** 残留", src.count("**"))
    add("background: 简写", len(re.findall(r'background\s*:(?!-)', src)))
    add("外链 http（src/href）", len(re.findall(r'(?:src|href)\s*=\s*["\']https?://', src)))

    # 半角引号只检查正文文本节点——先把标签整段剥离，
    # 否则 style="..." / alt="..." 这类属性值里的中文会被误判（技能里记录的老坑）。
    text_only = re.sub(r"<[^>]+>", "", src)
    add("正文半角引号（双）", len(re.findall(r'"[^"]*[\u4e00-\u9fff][^"]*"', text_only)))
    add("正文半角引号（单）", len(re.findall(r"'[^']*[\u4e00-\u9fff][^']*'", text_only)))

    p = Pair()
    p.feed(src)
    add("标签闭合配对", len(p.errors) + len(p.stack))

    # ---- 通用结构 ----
    for sec in REQUIRED_SECTIONS:
        add(f"含章节「{sec}」", src.count(sec), src.count(sec) > 0)

    # ---- 表格单元格显式 color（微信端不写会渲染成灰）----
    tds = re.findall(r"<td\b[^>]*>", src)
    if tds:
        missing = [t for t in tds if "color" not in t]
        add("td 显式 color（共 %d 个）" % len(tds), len(missing))

    # ---- 标题 ----
    if a.title:
        add("标题字数 ≤30", len(a.title), len(a.title) <= 30)
        add("标题字节 ≤64", len(a.title.encode("utf-8")), len(a.title.encode("utf-8")) <= 64)

    # ---- 选题关键词（由调用方传入）----
    for n in a.expect:
        add(f"含关键数字「{n}」", src.count(n), src.count(n) > 0)

    fails = 0
    for name, count, good in checks:
        flag = "PASS" if good else "FAIL"
        if not good:
            fails += 1
        print(f"[{flag}] {name} = {count}")
    if p.errors:
        for e in p.errors[:10]:
            print("   标签问题:", e)
    if p.stack:
        print("   未闭合:", p.stack)

    print(f"\n合计 {len(checks)} 项，{fails} 项未过")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
