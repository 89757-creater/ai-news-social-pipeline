#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""给抖音文章编辑器上传图片（文章头图 / 封面）。

踩过的坑：抖音是 React，用 DOM 元素 .click() 不触发上传逻辑（事件委托不在该节点上）。
改用 CDP 派发**真实鼠标事件**，并拦截原生文件选择框，再注入文件。
依赖同目录 cdp_read.py。
"""
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cdp_read import CDP, list_targets  # noqa: E402

CENTER_JS = """
(() => {
  const kw = KEY;
  const leaf = [...document.querySelectorAll('*')]
    .filter(e => e.children.length === 0 && (e.innerText || '').trim() === kw)[0];
  if (!leaf) return JSON.stringify({ err: 'NOT_FOUND' });
  const el = leaf.closest('[class*=content-upload-]') || leaf;
  el.scrollIntoView({ block: 'center', behavior: 'instant' });
  const r = el.getBoundingClientRect();
  return JSON.stringify({
    x: Math.round(r.x + r.width / 2),
    y: Math.round(r.y + r.height / 2),
    cls: String(el.className).slice(0, 40)
  });
})()
"""


def find_page():
    pages = [t for t in list_targets(9222)
             if t.get("type") == "page" and "post/article" in (t.get("url") or "")]
    return pages[0] if pages else None


def wait_event(c, method, timeout=8):
    """等待某个 CDP 事件（call 只处理带 id 的响应，事件会被这里捕获）。"""
    c.ws.settimeout(timeout)
    try:
        while True:
            msg = json.loads(c.ws.recv())
            if msg.get("method") == method:
                return msg
    except Exception:
        return None
    finally:
        try:
            c.ws.settimeout(90)
        except Exception:
            pass


def attach_file(c, path, tries=5):
    for i in range(tries):
        doc = c.call("DOM.getDocument", {"depth": -1})
        root = doc["result"]["root"]["nodeId"]
        q = c.call("DOM.querySelector", {"nodeId": root, "selector": "input[type=file]"})
        nid = (q.get("result") or {}).get("nodeId")
        if nid:
            r = c.call("DOM.setFileInputFiles", {"nodeId": nid, "files": [path]})
            return "ERROR " + json.dumps(r["error"]) if "error" in r else "SET_OK"
        time.sleep(1.2)
    return "NO_FILE_INPUT"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--keyword", required=True)
    ap.add_argument("--file", required=True)
    ap.add_argument("--wait", type=float, default=8.0)
    args = ap.parse_args()

    page = find_page()
    if not page:
        print("ERROR: 未找到文章编辑器页面")
        return 1

    c = CDP(page["webSocketDebuggerUrl"])
    try:
        c.call("Page.enable")
        c.call("Runtime.enable")
        c.call("DOM.enable")
        c.call("Page.setInterceptFileChooserDialog", {"enabled": True})

        c.call("Page.bringToFront")
        time.sleep(0.6)

        raw = c.eval(CENTER_JS.replace("KEY", json.dumps(args.keyword, ensure_ascii=False)))
        print("目标坐标:", raw)
        d = json.loads(raw)
        if d.get("err"):
            print("ERROR: 找不到上传区域")
            return 1

        for t in ("mouseMoved", "mousePressed", "mouseReleased"):
            p = {"type": t, "x": d["x"], "y": d["y"]}
            if t == "mousePressed":
                p.update({"button": "left", "buttons": 1, "clickCount": 1})
            if t == "mouseReleased":
                p.update({"button": "left", "buttons": 0, "clickCount": 1})
            c.call("Input.dispatchMouseEvent", p)
        print("已派发真实鼠标点击 @", d["x"], d["y"])
        time.sleep(1.2)

        ev = c.wait_event("Page.fileChooserOpened", 8)
        print("fileChooserOpened:", "YES" if ev else "NO")
        if ev:
            bnode = (ev.get("params") or {}).get("backendNodeId")
            if bnode:
                r = c.call("DOM.setFileInputFiles", {"backendNodeId": bnode, "files": [args.file]})
                print("按事件注入:", "ERROR " + json.dumps(r["error"]) if "error" in r else "SET_OK")
            else:
                print("事件里没有 backendNodeId")
        else:
            print("DOM 兜底注入:", attach_file(c, args.file))

        time.sleep(args.wait)

        chk = c.eval("""JSON.stringify({
          fileInputs: document.querySelectorAll('input[type=file]').length,
          imgs: [...document.querySelectorAll('img')].filter(i => /^https?:/.test(i.src)).length,
          hasReplace: document.body.innerText.includes('重新上传') || document.body.innerText.includes('更换封面'),
          dialogs: [...document.querySelectorAll('[class*=modal],[class*=Modal],[role=dialog]')]
            .map(e => ({cls: String(e.className).slice(0,45), txt: (e.innerText || '').slice(0, 90)}))
            .filter(x => x.txt).slice(0, 6),
          tail: document.body.innerText.slice(-260)
        })""")
        print("上传后状态:", chk)
    finally:
        c.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
