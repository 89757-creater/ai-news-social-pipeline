#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""按可见文案定位并真实点击页面元素（CDP trusted 鼠标事件 + userGesture）。

抖音编辑器大量使用 React 委托 + 自绘组件，DOM 上的 .click() 不生效，
必须走 Input.dispatchMouseEvent 合成真实鼠标事件。

用法：
  python douyin_click.py --text "完成"               # 列出候选并点第 0 个
  python douyin_click.py --text "公开" --nth 0
  python douyin_click.py --text "发布" --list        # 只列候选，不点
"""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cdp_read import CDP, list_targets, NEUTRALIZE_JS  # noqa: E402


LIST_JS = r"""
(() => {
  const kw = __KW__;
  return JSON.stringify([].slice.call(document.querySelectorAll('*'))
    .filter(function (e) { return e.children.length === 0 && (e.innerText || '').trim() === kw; })
    .map(function (e, i) {
      const r = e.getBoundingClientRect();
      return { i: i, tag: e.tagName, cls: String(e.className).slice(0, 60),
               vis: r.width > 0 && r.height > 0,
               box: [Math.round(r.x), Math.round(r.y), Math.round(r.width), Math.round(r.height)] };
    }));
})()
"""

CLICK_JS = r"""
(() => {
  const kw = __KW__, nth = __NTH__;
  const all = [].slice.call(document.querySelectorAll('*'))
    .filter(function (e) { return e.children.length === 0 && (e.innerText || '').trim() === kw; })
    .filter(function (e) { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; });
  if (!all.length) return JSON.stringify({ err: 'NOT_FOUND' });
  const leaf = all[Math.min(nth, all.length - 1)];
  leaf.scrollIntoView({ block: 'center', behavior: 'instant' });
  const rb = leaf.getBoundingClientRect();
  const cx = Math.round(rb.x + rb.width / 2), cy = Math.round(rb.y + rb.height / 2);
  const top = document.elementFromPoint(cx, cy) || leaf;
  const same = !!(top === leaf || top.contains(leaf) || leaf.contains(top));
  return JSON.stringify({ total: all.length, text: (leaf.innerText || '').trim(),
    hit: { tag: top.tagName, cls: String(top.className).slice(0, 70) },
    same: same, x: cx, y: cy });
})()
"""

# 兜底：入口被浮层挡住时（如面板遮罩淡出中、可拖拽预览面板压住），坐标点击必然落空，
# 改派 DOM 原生 click。（2026-09-18 实测：Semi Design 组件与普通按钮均可用。）
DOM_FALLBACK = r"""
(() => {
  const kw = __KW__, nth = __NTH__;
  const all = [].slice.call(document.querySelectorAll('*'))
    .filter(function (e) { return e.children.length === 0 && (e.innerText || '').trim() === kw; })
    .filter(function (e) { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; });
  if (!all.length) return 'NOT_FOUND';
  all[Math.min(nth, all.length - 1)].click();
  return 'DOM_CLICKED';
})()
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=9222)
    ap.add_argument("--pick", default="post/article")
    ap.add_argument("--text", required=True)
    ap.add_argument("--nth", type=int, default=0)
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--wait", type=float, default=2.5)
    ap.add_argument("--shot", default="")
    args = ap.parse_args()

    targets = [x for x in list_targets(args.port) if x.get("type") == "page"]
    hit = [x for x in targets if args.pick in (x.get("url") or "")]
    if not hit:
        print("ERROR: 找不到标签页:", args.pick)
        return 1

    c = CDP(hit[0]["webSocketDebuggerUrl"])
    try:
        c.call("Page.enable")
        c.call("DOM.enable")
        c.call("Runtime.enable")
        c.call("Page.bringToFront")
        # 已滑出视口的抽屉会以「看不见的全屏容器」吃掉鼠标事件，先解绑（见 cdp_read.NEUTRALIZE_JS）
        try:
            print("解绑隐形抽屉:", c.eval(NEUTRALIZE_JS))
        except Exception:
            pass

        kw = json.dumps(args.text, ensure_ascii=False)
        print("候选:", c.eval(LIST_JS.replace("__KW__", kw)))
        if args.list:
            return 0

        # 目标可能被浮层临时压住（面板遮罩淡出中 / 可拖拽预览面板），先等它散开
        d = None
        for attempt in range(12):
            raw = c.eval(CLICK_JS.replace("__KW__", kw).replace("__NTH__", str(args.nth)))
            try:
                d = json.loads(raw)
            except Exception:
                print("点击: 解析失败", raw)
                return 1
            if d.get("err"):
                print("ERROR:", d["err"])
                return 1
            if d.get("same"):
                break
            if attempt == 0:
                print("  目标被遮挡，等待散开：", d.get("hit"))
            time.sleep(0.4)

        if d.get("same"):
            print("点击:", raw)
            for et in ("mouseMoved", "mousePressed", "mouseReleased"):
                p = {"type": et, "x": d["x"], "y": d["y"], "modifiers": 0}
                if et != "mouseMoved":
                    p.update({"button": "left", "buttons": 1, "clickCount": 1})
                c.call("Input.dispatchMouseEvent", p)
        else:
            print("点击: 遮挡未散开（%s），改用 DOM click" % d.get("hit"))
            print("  ", c.eval(DOM_FALLBACK.replace("__KW__", kw).replace("__NTH__", str(args.nth))))

        time.sleep(args.wait)
        tail = c.eval("(document.body.innerText || '').slice(-240)")
        print("点击后尾部文本:", (tail or "").replace("\n", " | "))

        if args.shot:
            import base64
            shot = c.call("Page.captureScreenshot", {"format": "png"})
            data = shot.get("result", {}).get("data")
            if data:
                with open(args.shot, "wb") as f:
                    f.write(base64.b64decode(data))
                print("截图:", args.shot)
    finally:
        c.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
