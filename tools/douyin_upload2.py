#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""抖音创作者中心 · 文章配图上传攻坚（v2）

对前 6 次失败的根因修正：
  1. 未显式 Page.setInterceptFileChooserDialog({enabled:true}) —— 原生文件框弹出后会挂死，
     后续所有鼠标事件被模态框吃掉；
  2. 所有 JS 调用都没带 userGesture —— Chromium 要求 user activation 才允许打开文件选择器；
  3. input[type=file] 可能"创建即用即删" —— 必须 hook HTMLInputElement.prototype.click 抓住引用，
     并在它脱离文档树时重新 append，否则 DOM.setFileInputFiles 无从下手。

用法：
  python douyin_upload2.py --dry                        # 只诊断：装探针 + 点击 + 打印日志
  python douyin_upload2.py --file a.png                 # 点击并注入文件
  python douyin_upload2.py --file a.png,b.png           # 注入多张
  python douyin_upload2.py --keyword "点击上传封面图" --file c.png
"""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cdp_read import CDP, list_targets, NEUTRALIZE_JS  # noqa: E402


PROBE = r"""
(() => {
  window.__probe = [];
  window.__p = (t, e) => window.__probe.push(t + (e !== undefined ? ' :: ' + e : ''));
  if (window.__probeOn) { window.__p('PROBE_RESET'); return 'RESET'; }
  window.__probeOn = true;
  window.__blockFileDialog = true;

  // 1) 抓住动态创建的 file input，并阻止原生文件框
  const oc = HTMLInputElement.prototype.click;
  HTMLInputElement.prototype.click = function () {
    if (String(this.type).toLowerCase() === 'file') {
      window.__fileInput = this;
      if (!this.isConnected) {
        try { document.body.appendChild(this); window.__p('APPEND_INPUT'); }
        catch (e) { window.__p('APPEND_FAIL', String(e)); }
      }
      window.__p('FILE_INPUT_CLICK', 'accept=' + this.accept + ' cls=' + String(this.className).slice(0, 40));
      if (window.__blockFileDialog) { window.__p('BLOCKED_NATIVE_DIALOG'); return; }
    }
    return oc.apply(this, arguments);
  };

  // 2) File System Access API
  const sp = window.showOpenFilePicker;
  if (typeof sp === 'function') {
    window.showOpenFilePicker = function () {
      window.__p('SHOW_OPEN_FILE_PICKER', JSON.stringify([].slice.call(arguments)).slice(0, 160));
      return sp.apply(this, arguments);
    };
    window.__p('showOpenFilePicker', 'DEFINED');
  } else {
    window.__p('showOpenFilePicker', 'UNDEFINED');
  }

  // 3) 捕捉 createElement('input')
  const oce = Document.prototype.createElement;
  Document.prototype.createElement = function (t) {
    const el = oce.apply(this, arguments);
    if (String(t).toLowerCase() === 'input') {
      window.__lastInput = el;
      window.__p('CREATE_INPUT');
      el.addEventListener('change',
        function () { window.__p('INPUT_CHANGE', 'files=' + (el.files ? el.files.length : -1)); }, true);
    }
    return el;
  };

  // 4) 全局 change
  document.addEventListener('change', function (e) {
    const t = e.target;
    window.__p('DOC_CHANGE', (t && t.tagName) + '/' + (t && t.type) +
               ' files=' + (t && t.files ? t.files.length : -1));
  }, true);

  window.__p('PROBE_INSTALLED');
  return 'PROBE_INSTALLED';
})()
"""

LOCATE = r"""
(() => {
  const kw = __KW__;
  const leaf = [].slice.call(document.querySelectorAll('*'))
    .filter(function (e) { return e.children.length === 0 && (e.innerText || '').trim() === kw; })[0];
  if (!leaf) return JSON.stringify({ err: 'LEAF_NOT_FOUND' });
  leaf.scrollIntoView({ block: 'center', behavior: 'instant' });
  const r0 = leaf.getBoundingClientRect();
  const cx = Math.round(r0.x + r0.width / 2);
  const cy = Math.round(r0.y + r0.height / 2);
  const top = document.elementFromPoint(cx, cy);
  const box = top ? top.getBoundingClientRect() : r0;
  return JSON.stringify({
    leafBox: [Math.round(r0.x), Math.round(r0.y), Math.round(r0.width), Math.round(r0.height)],
    top: top ? { tag: top.tagName, cls: String(top.className).slice(0, 70),
                 same: !!(top === leaf || top.contains(leaf) || leaf.contains(top)) } : null,
    x: Math.round(box.x + box.width / 2),
    y: Math.round(box.y + box.height / 2),
    lx: cx, ly: cy
  });
})()
"""

STATE = r"""
JSON.stringify({
  fileInputsInDom: document.querySelectorAll('input[type=file]').length,
  hasFileInputRef: !!window.__fileInput,
  httpImgs: [].slice.call(document.querySelectorAll('img')).filter(function (i) { return /^https?:/.test(i.src); }).length,
  txt: (document.body.innerText || '').slice(-260),
  probe: window.__probe || []
})
"""

# 直接对入口元素派发 DOM click——绕开被浮层遮挡（如可拖拽的手机预览面板）导致坐标点击落空的问题
DOM_CLICK = r"""
(() => {
  const kw = __KW__;
  const leaf = [].slice.call(document.querySelectorAll('*'))
    .filter(function (e) { return e.children.length === 0 && (e.innerText || '').trim() === kw; })[0];
  if (!leaf) return 'LEAF_NOT_FOUND';
  leaf.scrollIntoView({ block: 'center', behavior: 'instant' });
  leaf.click();
  return 'DOM_CLICKED';
})()
"""


def ev_gesture(c, expr):
    """带 userGesture 的求值——满足 Chromium 打开文件选择器的 user activation 要求。"""
    r = c.call("Runtime.evaluate", {"expression": expr, "returnByValue": True,
                                    "awaitPromise": True, "userGesture": True})
    res = r.get("result", {})
    if "exceptionDetails" in res:
        return "[JS ERROR] " + str(res["exceptionDetails"].get("text"))
    return res.get("result", {}).get("value")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=9222)
    ap.add_argument("--pick", default="post/article")
    ap.add_argument("--keyword", default="点击上传图片")
    ap.add_argument("--file", default="", help="要注入的图片路径，多个用逗号分隔")
    ap.add_argument("--dry", action="store_true", help="只诊断不注入")
    ap.add_argument("--wait", type=float, default=4.0)
    args = ap.parse_args()

    targets = [x for x in list_targets(args.port) if x.get("type") == "page"]
    hit = [x for x in targets if args.pick in (x.get("url") or "")]
    if not hit:
        print("ERROR: 找不到标签页，含关键词:", args.pick)
        for t in targets[:10]:
            print("   -", (t.get("url") or "")[:100])
        return 1
    t = hit[0]
    print("目标标签:", (t.get("url") or "")[:110])

    c = CDP(t["webSocketDebuggerUrl"])
    try:
        c.call("Page.enable")
        c.call("DOM.enable")
        c.call("Runtime.enable")

        # 关键修正 1：切到前台（后台标签会被节流，且 user activation 可能失效）
        c.call("Page.bringToFront")
        # 关键修正 2：显式开启文件框拦截，避免原生模态框挂死
        r = c.call("Page.setInterceptFileChooserDialog", {"enabled": True})
        print("文件框拦截:", "OK" if "error" not in r else json.dumps(r["error"]))
        # 顺手清掉可能残留的弹窗
        for kt in ("keyDown", "keyUp"):
            c.call("Input.dispatchKeyEvent", {"type": kt, "key": "Escape", "code": "Escape",
                                              "windowsVirtualKeyCode": 27, "nativeVirtualKeyCode": 27})
        time.sleep(0.5)
        # 关键修正 3：解绑「已滑出视口的抽屉」残留的全屏全屏容器（会静默吃掉所有鼠标事件，
        # 见 cdp_read.NEUTRALIZE_JS；不加这句时坐标点击会「成功派发但毫无反应」）
        try:
            print("解绑隐形抽屉:", c.eval(NEUTRALIZE_JS))
        except Exception:
            pass

        # 现状
        st0 = c.eval("JSON.stringify({title: document.title.slice(0,60), url: location.href.slice(-60),"
                     " txtLen: (document.body && document.body.innerText || '').length})")
        print("页面:", st0)

        # 装探针
        print("探针:", c.eval(PROBE))

        # 定位上传区
        raw = ev_gesture(c, LOCATE.replace("__KW__", json.dumps(args.keyword, ensure_ascii=False)))
        print("定位:", raw)
        try:
            d = json.loads(raw)
        except Exception:
            print("ERROR: 定位失败")
            return 1
        if d.get("err"):
            print("ERROR:", d["err"])
            return 1

        # 先走 DOM click：不受浮层遮挡影响（抖音的「手机预览」面板可被拖到中间盖住入口）
        probe_hit = "(window.__probe||[]).some(function(x){return x.indexOf('FILE_INPUT_CLICK')>=0;})"
        dom = ev_gesture(c, DOM_CLICK.replace("__KW__", json.dumps(args.keyword, ensure_ascii=False)))
        print("DOM click:", dom)
        time.sleep(0.8)
        fired = c.eval(probe_hit)

        if not fired:
            # 回落：真实鼠标点击（trusted）。用 leaf 自身中心，不用被遮挡后的 top 中心
            px, py = d.get("lx", d["x"]), d.get("ly", d["y"])
            if d.get("top") and not d["top"].get("same"):
                print("  !! 入口被遮挡，top =", d["top"].get("cls"))
            for et in ("mouseMoved", "mousePressed", "mouseReleased"):
                p = {"type": et, "x": px, "y": py, "modifiers": 0}
                if et != "mouseMoved":
                    p.update({"button": "left", "buttons": 1, "clickCount": 1})
                c.call("Input.dispatchMouseEvent", p)
            print("已点击(坐标):", px, py, "->", d.get("top"))
            time.sleep(0.8)
            fired = c.eval(probe_hit)
            print("坐标点击是否触发文件选择器:", "YES" if fired else "NO")
        else:
            print("DOM click 已触发文件选择器（绕过遮挡）")

        fce = c.wait_event("Page.fileChooserOpened", 4)
        print("Page.fileChooserOpened:", "YES" if fce else "NO")
        time.sleep(1.2)

        if fce:
            bnode = (fce.get("params") or {}).get("backendNodeId")
            if bnode and args.file:
                files = [p.strip() for p in args.file.split(",") if p.strip()]
                rr = c.call("DOM.setFileInputFiles", {"backendNodeId": bnode, "files": files})
                print("按事件注入:", "ERROR " + json.dumps(rr["error"]) if "error" in rr else "OK")

        # 抓引用注入（仅在本次确实触发了文件选择器时才注入，避免打到上一次残留的 input）
        if args.file and not args.dry:
            if not (fired or fce):
                print("!! 本次未触发文件选择器，跳过注入（不对残留 input 下手）")
                return 1
            obj = c.call("Runtime.evaluate", {"expression": "window.__fileInput || window.__lastInput || null",
                                              "returnByValue": False}).get("result", {}).get("result", {})
            oid = obj.get("objectId")
            print("file input objectId:", oid or "NONE")
            if oid:
                files = [p.strip() for p in args.file.split(",") if p.strip()]
                for f in files:
                    if not os.path.isfile(f):
                        print("  !! 文件不存在:", f)
                rr = c.call("DOM.setFileInputFiles", {"objectId": oid, "files": files})
                print("按引用注入:", "ERROR " + json.dumps(rr["error"]) if "error" in rr else "OK")

        time.sleep(args.wait)
        st = c.eval(STATE)
        print("=" * 60)
        try:
            sd = json.loads(st)
            print("DOM 内 file input:", sd.get("fileInputsInDom"))
            print("已抓到 input 引用:", sd.get("hasFileInputRef"))
            print("http 图片数:", sd.get("httpImgs"))
            print("探针日志:")
            for line in sd.get("probe", []):
                print("   -", line)
            print("页面尾部文本:", (sd.get("txt") or "").replace("\n", " | ")[:300])
        except Exception:
            print(st)
    finally:
        c.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
