#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把《抖音版文案.md》填入抖音文章编辑器（标题 / 摘要 / 正文）。

只填不发布 —— 发布是不可逆的公开动作，留给人工确认后再点。
依赖同目录的 cdp_read.py（复用其 CDP 封装）。
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cdp_read import CDP, list_targets  # noqa: E402

WS = Path(r"C:/Users/suge0/WorkBuddy/automation-2026-09-13-16-27-29")
DOC = WS / "social/2026-09-15/douyin/抖音版文案.md"


def section(text, name):
    m = re.search(r"^##\s*" + re.escape(name) + r"[^\n]*\n+(.*?)(?=\n##\s|\Z)", text, re.S | re.M)
    return m.group(1).strip() if m else ""


def pick(text, names):
    for n in names:
        v = section(text, n)
        if v:
            return v
    return ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--doc", default=str(DOC), help="抖音版文案.md 路径")
    ap.add_argument("--clear", action="store_true",
                    help="插入正文前先清空编辑器（重填时必加，否则内容会末尾追加、越填越长）")
    args = ap.parse_args()

    raw = Path(args.doc).read_text(encoding="utf-8")

    title = pick(raw, ["标题", "文章标题"]).splitlines()[0].strip()
    summary = pick(raw, ["摘要", "文章摘要"]).splitlines()[0].strip()
    body = pick(raw, ["正文", "文章正文"])
    body = re.sub(r"\*\*(.+?)\*\*", r"\1", body)          # 富文本编辑器不认 markdown 星号
    body = re.sub(r"^#{1,6}\s*", "", body, flags=re.M)    # 三级及以下小标题去掉井号，保留文字
    body = re.sub(r"^>\s?", "", body, flags=re.M)         # 去掉引用块符号
    body = re.sub(r"^\s*[-*]\s+", "· ", body, flags=re.M)  # 无序列表转圆点
    body = re.sub(r"^\s*-{3,}\s*$", "", body, flags=re.M)   # 去掉 markdown 水平线（会被当成正文文字带进去）
    body = re.sub(r"\n{3,}", "\n\n", body)
    paras = [p.strip() for p in body.split("\n\n") if p.strip()]

    print(f"标题({len(title)}字): {title}")
    print(f"摘要({len(summary)}字): {summary}")
    print(f"正文: {len(paras)} 段 / {len(body)} 字")

    pages = [t for t in list_targets(9222)
             if t.get("type") == "page" and "post/article" in (t.get("url") or "")]
    if not pages:
        print("ERROR: 未找到抖音文章编辑器页面（post/article）")
        return 1

    c = CDP(pages[0]["webSocketDebuggerUrl"])
    try:
        c.call("Runtime.enable")

        # ── 标题 / 摘要：React 受控 input，必须走原生 setter + input 事件 ──
        setter_js = """
        (() => {
          const setNative = (el, val) => {
            const s = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
            s.call(el, val);
            el.dispatchEvent(new Event('input', { bubbles: true }));
            el.dispatchEvent(new Event('change', { bubbles: true }));
          };
          const inputs = [...document.querySelectorAll('input.semi-input')];
          const t = inputs.find(e => (e.placeholder || '').includes('文章标题'));
          const d = inputs.find(e => (e.placeholder || '').includes('摘要'));
          if (t) setNative(t, TITLE);
          if (d) setNative(d, SUMMARY);
          return JSON.stringify({title: t ? t.value : null, summary: d ? d.value : null});
        })()
        """
        js = setter_js.replace("TITLE", json.dumps(title, ensure_ascii=False)) \
                       .replace("SUMMARY", json.dumps(summary, ensure_ascii=False))
        print("标题/摘要写入结果:", c.eval(js))

        # ── 正文：tiptap / ProseMirror，逐段 execCommand 插入 ──
        body_js = """
        (() => {
          const el = document.querySelector('.ProseMirror[contenteditable="true"]');
          if (!el) return 'NO_EDITOR';
          el.focus();
          const sel = window.getSelection();
          const range = document.createRange();
          range.selectNodeContents(el);
          sel.removeAllRanges();
          sel.addRange(range);
          if (CLEAR) { document.execCommand('delete'); }
          const sel2 = window.getSelection();
          const range2 = document.createRange();
          range2.selectNodeContents(el);
          range2.collapse(false);
          sel2.removeAllRanges();
          sel2.addRange(range2);
          const paras = PARAS;
          for (let i = 0; i < paras.length; i++) {
            if (i > 0) document.execCommand('insertParagraph');
            document.execCommand('insertText', false, paras[i]);
          }
          return JSON.stringify({len: el.innerText.length, head: el.innerText.slice(0, 60)});
        })()
        """.replace("PARAS", json.dumps(paras, ensure_ascii=False)) \
           .replace("CLEAR", "true" if args.clear else "false")
        print("正文写入结果:", c.eval(body_js))

        # ── 回读校验 ──
        verify = c.eval("""(() => {
          const el = document.querySelector('.ProseMirror[contenteditable="true"]');
          const inputs = [...document.querySelectorAll('input.semi-input')];
          const t = inputs.find(e => (e.placeholder||'').includes('文章标题'));
          return JSON.stringify({
            titleVal: t ? t.value : null,
            bodyLen: el ? el.innerText.length : 0,
            bodyParas: el ? el.querySelectorAll('p,div').length : 0,
            bodyTail: el ? el.innerText.slice(-80) : ''
          });
        })()""")
        print("回读校验:", verify)
    finally:
        c.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
