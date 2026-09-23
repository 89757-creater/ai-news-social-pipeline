#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""核实：重载所有 content/manage 标签，输出作品数与被删标题是否已消失。

为什么要「重载后再读」：抖音管理页是 SPA，标签从别的页面跳转过来时
可能还停在上一次的快照上（表现为作品数少 1、新作品看不到）。
"""
import io
import json
import sys
import time
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

WS = Path(r"C:/Users/suge0/WorkBuddy/automation-2026-09-13-16-27-29")
sys.path.insert(0, str(WS / "tools"))
from cdp_read import CDP, JS_MANAGE_READY, pages, wait_until  # noqa: E402

URL = "https://creator.douyin.com/creator-micro/content/manage?enter_from=publish"
KW = "AI 写了 7.5 万行代码"

for idx, t in enumerate(pages(9222, "content/manage"), 1):
    c = CDP(t["webSocketDebuggerUrl"])
    try:
        c.call("Runtime.enable")
        c.call("Page.enable")
        c.call("Page.navigate", {"url": URL})
        time.sleep(4)
        wait_until(c, JS_MANAGE_READY, timeout=30)
        txt = c.eval("document.body.innerText") or ""
        c.call("Page.bringToFront")
        shot = c.call("Page.captureScreenshot", {"format": "png"})
        data = shot.get("result", {}).get("data")
        if data:
            import base64
            (WS / f"manage_verify_{idx}.png").write_bytes(base64.b64decode(data))
        i = txt.find("作品 (")
        print(f"--- 标签 {idx} ({t['id'][:8]}) len={len(txt)}")
        print("   ", txt[i:i + 40].replace("\n", " ") if i >= 0 else "(读不到作品数)")
        print("    含被删标题:", KW in txt)
        print("    含 09-14 新作:", "2026年09月14日" in txt)
    finally:
        c.close()
