#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""在页面上按 placeholder 关键词定位输入框，真实点击并用 CDP insertText 输入文本。

React 受控输入直接改 value 无效，必须走 insertText。

用法：
  python douyin_type.py --ph "验证码" --text "025027"
  python douyin_type.py --ph "验证码" --text "025027" --enter
"""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cdp_read import CDP, list_targets  # noqa: E402

FIND = r"""
(() => {
  const kw = __KW__;
  const all = [].slice.call(document.querySelectorAll('input,textarea'));
  let hit = all.filter(function (e) {
    const ph = (e.placeholder || '') + (e.getAttribute('data-placeholder') || '');
    return ph.indexOf(kw) >= 0;
  })[0];
  if (!hit) {
    hit = all.filter(function (e) {
      const r = e.getBoundingClientRect();
      return r.width > 100 && r.height > 18;
    })[0];
  }
  if (!hit) return JSON.stringify({ err: 'NOT_FOUND', n: all.length });
  const r = hit.getBoundingClientRect();
  return JSON.stringify({ tag: hit.tagName, ph: hit.placeholder || '',
    x: Math.round(r.x + r.width / 2), y: Math.round(r.y + r.height / 2) });
})()
"""


def click(c, x, y):
    for et in ("mouseMoved", "mousePressed", "mouseReleased"):
        p = {"type": et, "x": x, "y": y, "modifiers": 0}
        if et != "mouseMoved":
            p.update({"button": "left", "buttons": 1, "clickCount": 1})
        c.call("Input.dispatchMouseEvent", p)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=9222)
    ap.add_argument("--pick", default="post/article")
    ap.add_argument("--ph", default="", help="placeholder 关键词")
    ap.add_argument("--text", required=True)
    ap.add_argument("--enter", action="store_true", help="输入后按回车")
    args = ap.parse_args()

    targets = [x for x in list_targets(args.port) if x.get("type") == "page"]
    hit = [x for x in targets if args.pick in (x.get("url") or "")]
    if not hit:
        print("ERROR: 找不到标签页")
        return 1

    c = CDP(hit[0]["webSocketDebuggerUrl"])
    try:
        c.call("Page.enable")
        c.call("Runtime.enable")
        c.call("Page.bringToFront")

        d = json.loads(c.eval(FIND.replace("__KW__", json.dumps(args.ph, ensure_ascii=False))))
        print("输入框:", d)
        if d.get("err"):
            return 1

        click(c, d["x"], d["y"])
        time.sleep(0.4)
        c.call("Input.insertText", {"text": args.text})
        print("已输入:", args.text)
        time.sleep(0.4)

        if args.enter:
            for kt in ("keyDown", "keyUp"):
                c.call("Input.dispatchKeyEvent", {"type": kt, "key": "Enter", "code": "Enter",
                                                  "windowsVirtualKeyCode": 13, "nativeVirtualKeyCode": 13})
            print("已回车")

        time.sleep(1.2)
        print("尾部:", (c.eval("(document.body.innerText||'').slice(-200)") or "").replace("\n", " | "))
    finally:
        c.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
