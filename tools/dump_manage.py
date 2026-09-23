#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""只读：把 /content/manage 的作品清单完整 dump 出来（标题/日期/状态/体裁），并截图存档。
不做任何删除动作。
"""
import base64
import json
import sys
import time
from pathlib import Path

WS = Path(r"C:/Users/suge0/WorkBuddy/automation-2026-09-13-16-27-29")
sys.path.insert(0, str(WS / "tools"))
from cdp_read import CDP, list_targets  # noqa: E402

# 每张作品卡片：抓标题、日期、状态、操作按钮（有无「编辑作品」= 图文体裁）
CARDS = r"""(()=>{
  const out = [];
  const nodes = document.querySelectorAll('[class*=card],[class*=item],[class*=work]');
  const seen = new Set();
  nodes.forEach(function(n){
    const t = (n.innerText || '').trim();
    if (!t) return;
    if (!/20\d\d年\d\d月\d\d日/.test(t)) return;          // 必须含日期
    if (t.length > 900) return;                            // 太大的是外层容器
    if (seen.has(t)) return;
    seen.add(t);
    const r = n.getBoundingClientRect();
    out.push({ text: t.replace(/\n+/g, ' | ').slice(0, 700),
               box: [Math.round(r.x), Math.round(r.y), Math.round(r.width), Math.round(r.height)] });
  });
  return JSON.stringify(out);
})()"""


def main():
    pages = [t for t in list_targets(9222)
             if t.get("type") == "page" and "content/manage" in (t.get("url") or "")]
    if not pages:
        print("ERROR: 没有 content/manage 标签页")
        return 1
    c = CDP(pages[0]["webSocketDebuggerUrl"])
    c.call("Runtime.enable")
    c.call("Page.enable")
    try:
        print("URL:", c.eval("location.href"))
        print("文本长度:", c.eval("(document.body.innerText||'').length"))
        time.sleep(2)

        raw = c.eval(CARDS)
        try:
            cards = json.loads(raw or "[]")
        except Exception:
            print("卡片解析失败:", raw[:300])
            cards = []
        print("识别到卡片数:", len(cards))
        for i, cd in enumerate(cards, 1):
            print("-" * 70)
            print(f"[卡片 {i}] box={cd['box']}")
            print("   ", cd["text"])

        data = (c.call("Page.captureScreenshot", {"format": "png"}) or {}).get("result", {}).get("data")
        if data:
            p = WS / "_manage_before_delete.png"
            p.write_bytes(base64.b64decode(data))
            print("\n截图:", p)
    finally:
        c.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
