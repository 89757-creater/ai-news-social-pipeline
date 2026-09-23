#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""抖音文章编辑器 · 添加话题。

React 受控输入必须用 CDP Input.insertText 触发真实 input 事件，直接改 value 无效。

流程：点搜索框 -> insertText -> 列出候选 -> 点选 -> （可选）确认添加

用法：
  python douyin_topic.py --text "AI" --list          # 只输入并列候选
  python douyin_topic.py --text "AI"                 # 输入并点第一个候选
  python douyin_topic.py --text "人工智能" --nth 2
"""
import argparse
import base64
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cdp_read import CDP, list_targets, NEUTRALIZE_JS  # noqa: E402

FIND_INPUT = r"""
(() => {
  const W = window.innerWidth, H = window.innerHeight;
  // ⚠️ 必须限定「真的在视口里」：音乐抽屉那类滑出视口的容器里还留着
  //    placeholder="搜索音乐" 的 input，且它在 DOM 里**排在话题框前面**，
  //    旧写法按「含话题或含搜索」取 [0] 会稳定命中它 —— 字全打进了音乐搜索框，
  //    表现是「话题计数始终 0/5、且不报任何错」（2026-09-18 实测）。
  const all = [].slice.call(document.querySelectorAll('input,textarea')).filter(function (e) {
    const r = e.getBoundingClientRect();
    const cs = getComputedStyle(e);
    if (r.width <= 1 || r.height <= 1) return false;
    if (r.left >= W - 2 || r.top >= H - 2 || r.left <= -2) return false;
    if (cs.visibility === 'hidden' || cs.display === 'none') return false;
    return true;
  });
  const phOf = function (e) { return (e.placeholder || '') + (e.getAttribute('data-placeholder') || ''); };
  // 先认「话题」，再退而求其次认「搜索」（但排除音乐搜索框）
  let hit = all.filter(function (e) { return phOf(e).indexOf('话题') >= 0; })[0];
  if (!hit) {
    hit = all.filter(function (e) {
      const ph = phOf(e);
      return ph.indexOf('搜索') >= 0 && ph.indexOf('音乐') < 0;
    })[0];
  }
  if (!hit) {
    return JSON.stringify({ err: 'INPUT_NOT_FOUND', n: all.length,
      cand: all.map(function (e) { const r = e.getBoundingClientRect();
        return phOf(e).slice(0, 18) + '@' + Math.round(r.left); }) });
  }
  const r = hit.getBoundingClientRect();
  return JSON.stringify({ tag: hit.tagName, ph: hit.placeholder || '',
    x: Math.round(r.x + r.width / 2), y: Math.round(r.y + r.height / 2) });
})()
"""

OPTIONS = r"""
(() => {
  const W = window.innerWidth, H = window.innerHeight;
  const cands = [];
  [].slice.call(document.querySelectorAll('div,li,span,p,a')).forEach(function (e) {
    const t = (e.innerText || '').trim();
    if (t.length < 3 || t.charAt(0) !== '#') return;   // 排除单独的 "#" 图标
    if (t.length > 40) return;
    if (t.split('\n').length > 2) return;              // 排除整个下拉容器（含多行）
    if (t.indexOf('点击添加话题') >= 0) return;        // 编辑器里的入口文案，不是候选
    const r = e.getBoundingClientRect();
    if (r.width <= 0 || r.height <= 0 || r.height > 80) return;
    if (r.left >= W - 2 || r.top >= H - 2) return;     // 视口外（滑出的抽屉）不算
    cands.push({ text: t.replace(/\s+/g, ' '), cls: String(e.className).slice(0, 44),
                 x: Math.round(r.x + r.width / 2), y: Math.round(r.y + r.height / 2),
                 w: Math.round(r.width) });
  });
  // 同一行去重：保留宽度最大的（最外层行容器，点击面积最大）
  const rows = [];
  cands.forEach(function (c) {
    const hit = rows.filter(function (x) { return Math.abs(x.y - c.y) < 6; })[0];
    if (!hit) rows.push(c);
    else if (c.w > hit.w) { hit.text = c.text; hit.x = c.x; hit.w = c.w; hit.cls = c.cls; }
  });
  // searchSection-* 是搜索框下方的「搜索入口」行，与真实话题项同名但不是话题项，
  // 点它只会把词留在搜索框里（表现为「点了但计数不变」）。排到最后。
  rows.sort(function (a, b) {
    const sa = /searchSection/.test(a.cls) ? 1 : 0;
    const sb = /searchSection/.test(b.cls) ? 1 : 0;
    return sa - sb || a.y - b.y;
  });
  return JSON.stringify(rows.slice(0, 12));
})()
"""


JS_IS_FOCUSED = """(()=>{var a=document.activeElement;return !!a && ((a.placeholder||'')+(a.getAttribute('data-placeholder')||'')).indexOf('话题')>=0;})()"""

JS_DOM_FOCUS = """(()=>{var l=[].slice.call(document.querySelectorAll('input,textarea')).filter(function(e){return ((e.placeholder||'')+(e.getAttribute('data-placeholder')||'')).indexOf('话题')>=0;});if(l[0]){l[0].focus();return 'FOCUSED';}return 'NO';})()"""

JS_TOPIC_VALUE = """(()=>{var l=[].slice.call(document.querySelectorAll('input')).filter(function(e){return ((e.placeholder||'')+(e.getAttribute('data-placeholder')||'')).indexOf('话题')>=0;});return l.length? l[0].value : 'NOT_FOUND';})()"""

JS_DROPDOWN_OPEN = "(()=>{return document.querySelectorAll('[class*=dropdownItem]').length;})()"

# React 受控输入的可靠写值法：走**原生 value setter** 再派发 input/change。
# 直接 `el.value = x` 会被 React 的受控逻辑吞掉（这就是「直接改 value 无效」的由来），
# 而原生 setter 能绕过它。优点：**覆盖**而非追加，不受焦点/Ctrl+A 是否生效影响。
JS_SET_VALUE = r"""(()=>{
  const kw = __TEXT__;
  const l = [].slice.call(document.querySelectorAll('input')).filter(function(e){
    return ((e.placeholder || '') + (e.getAttribute('data-placeholder') || '')).indexOf('话题') >= 0;
  });
  if (!l.length) return 'NO_INPUT';
  const el = l[0];
  el.focus();
  const d = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value');
  d.set.call(el, kw);
  el.dispatchEvent(new Event('input', {bubbles: true}));
  el.dispatchEvent(new Event('change', {bubbles: true}));
  return el.value;
})()"""

# 点选候选的兜底：派发**完整指针/鼠标事件序列**。
# ⚠️ Semi 的下拉项常依赖 hover 记录的 activeIndex 或 mousedown 才提交，
#    只发一个 click（甚至真实点击若被透明层吃掉）都不会生效。
JS_PICK_DOM = r"""(()=>{
  const kw = __TEXT__;
  const items = [].slice.call(document.querySelectorAll('[class*=dropdownItem]')).filter(function(e){
    return ((e.innerText || '') + '').indexOf(kw) >= 0;
  });
  if (!items.length) return 'NO_ITEM';
  const el = items[0];
  const r = el.getBoundingClientRect();
  const x = Math.round(r.left + r.width / 2), y = Math.round(r.top + r.height / 2);
  const fire = function(type){
    const Ctor = (type.indexOf('pointer') === 0 && window.PointerEvent) ? PointerEvent : MouseEvent;
    try {
      el.dispatchEvent(new Ctor(type, {bubbles: true, cancelable: true, view: window,
        clientX: x, clientY: y, button: 0, buttons: 1,
        pointerId: 1, pointerType: 'mouse', isPrimary: true}));
    } catch (_) {}
  };
  ['pointerover','pointerenter','mouseover','mouseenter','pointermove','mousemove',
   'pointerdown','mousedown','pointerup','mouseup','click'].forEach(fire);
  return 'DOM_SEQ@' + x + ',' + y;
})()"""


def click(c, x, y):
    # ⚠️ 必须先解开「隐形遮挡」——否则坐标正确、elementFromPoint 也对，
    #    但鼠标事件被透明浮层吃掉，表现为「点了但没反应、也不报错」
    #    （2026-09-18 实测，见 cdp_read.NEUTRALIZE_JS）
    try:
        c.eval(NEUTRALIZE_JS)
    except Exception:
        pass
    for et in ("mouseMoved", "mousePressed", "mouseReleased"):
        p = {"type": et, "x": x, "y": y, "modifiers": 0}
        if et != "mouseMoved":
            p.update({"button": "left", "buttons": 1, "clickCount": 1})
        c.call("Input.dispatchMouseEvent", p)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=9222)
    ap.add_argument("--pick", default="post/article")
    ap.add_argument("--text", required=True)
    ap.add_argument("--nth", type=int, default=0)
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--shot", default="")
    args = ap.parse_args()

    targets = [x for x in list_targets(args.port) if x.get("type") == "page"]
    hit = [x for x in targets if args.pick in (x.get("url") or "")]
    if not hit:
        print("ERROR: 找不到标签页")
        return 1

    c = CDP(hit[0]["webSocketDebuggerUrl"])
    try:
        c.call("Page.enable")
        c.call("DOM.enable")
        c.call("Runtime.enable")
        c.call("Page.bringToFront")

        raw = c.eval(FIND_INPUT)
        print("搜索框:", raw)
        d = json.loads(raw)
        if d.get("err"):
            return 1

        # ── 聚焦 + 写值 ──
        # 先真实点击（理想路径），没聚焦上就 DOM focus（否则后续输入会打进别处）
        click(c, d["x"], d["y"])
        time.sleep(0.4)
        if not c.eval(JS_IS_FOCUSED):
            print("   真实点击未聚焦，改用 DOM focus")
            c.eval(JS_DOM_FOCUS)
            time.sleep(0.3)
        # 首选原生 setter 写值：覆盖式，不会像键盘输入那样把旧值往后接
        val = c.eval(JS_SET_VALUE.replace("__TEXT__", json.dumps(args.text, ensure_ascii=False))) or ""
        if val != args.text:
            print("   原生 setter 未生效（框内=%r），改用键盘输入" % val)
            for kt in ("keyDown", "keyUp"):
                c.call("Input.dispatchKeyEvent", {"type": kt, "key": "a", "code": "KeyA", "modifiers": 2,
                                                  "windowsVirtualKeyCode": 65, "nativeVirtualKeyCode": 65})
            time.sleep(0.2)
            c.call("Input.insertText", {"text": args.text})
            time.sleep(0.6)
            val = c.eval(JS_TOPIC_VALUE) or ""
            if args.text not in val:
                print("   insertText 也未生效，改逐字符输入")
                for ch in args.text:
                    c.call("Input.dispatchKeyEvent", {"type": "char", "text": ch})
                    time.sleep(0.06)
                time.sleep(0.5)
                val = c.eval(JS_TOPIC_VALUE) or ""
        print("已输入:", args.text, "| 框内实际:", repr(val))

        # ⚠️ 候选是**异步**拉回来的。弹窗会先显示「搜索中...」，
        #    实测要 4 秒上下；原来固定 sleep(2) 会让候选列表还是空的时候就往下走。
        #    改为轮询等待（最多 ~10 秒），拿到候选立刻继续。
        opts, arr = "[]", []
        for _ in range(13):
            time.sleep(0.8)
            opts = c.eval(OPTIONS)
            try:
                arr = json.loads(opts)
            except Exception:
                arr = []
            if arr:
                break
        print("候选话题:", (opts or "")[:300])

        if args.shot:
            shot = c.call("Page.captureScreenshot", {"format": "png"})
            data = shot.get("result", {}).get("data")
            if data:
                with open(args.shot, "wb") as f:
                    f.write(base64.b64decode(data))
                print("截图:", args.shot)

        if args.list:
            return 0

        if not arr:
            print("没有候选，改用回车尝试提交")
            for kt in ("keyDown", "keyUp"):
                c.call("Input.dispatchKeyEvent", {"type": kt, "key": "Enter", "code": "Enter",
                                                  "windowsVirtualKeyCode": 13, "nativeVirtualKeyCode": 13})
        else:
            pick = arr[min(args.nth, len(arr) - 1)]
            print("点选:", pick["text"], "->", pick["x"], pick["y"])
            click(c, pick["x"], pick["y"])
            time.sleep(1.3)
            # 选中成功后下拉应消失；还在说明这次点击没被受理
            if str(c.eval(JS_DROPDOWN_OPEN)) not in ("0", "None", ""):
                word = pick["text"].lstrip("#").split()[0]
                print("   真实点击未选中（下拉仍开着），改用 DOM 事件序列：",
                      c.eval(JS_PICK_DOM.replace("__TEXT__", json.dumps(word, ensure_ascii=False))))
                time.sleep(1.2)
        time.sleep(1.5)
        print("弹窗尾部:", (c.eval("(document.body.innerText||'').slice(-160)") or "").replace("\n", " | "))
    finally:
        c.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
