#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""抖音创作者中心 · 删除作品（按标题精确定位，防误删）

为什么不能直接用 `douyin_click.py --text "删除作品"`：
作品列表里每个卡片都有同名按钮，按文案盲点会删错作品。**删除不可逆**。

本脚本的定位链：
  1. 按标题关键词找**文本最短的**包含该词的可见元素 → 即为作品标题
  2. 取页面所有「删除作品」叶子按钮，按与标题的**纵向距离**排序取最近的一个
  3. `delta`（按钮与标题的 y 差）超过 `--max-delta` 直接中止，宁可不删

用法：
  python douyin_delete.py --title "机器人能走下产线" --dry    # 只开弹窗、dump 按钮，然后点取消
  python douyin_delete.py --title "机器人能走下产线"          # 开弹窗并确认删除
"""
import argparse
import json
import sys
import time
from pathlib import Path

WS = Path(r"C:/Users/suge0/WorkBuddy/automation-2026-09-13-16-27-29")
sys.path.insert(0, str(WS / "tools"))
from cdp_read import (CDP, JS_MANAGE_READY, NEUTRALIZE_JS, connect_retry,  # noqa: E402
                      dedupe_tabs, pages, reload_and_wait, wait_until)

# 确认弹窗里是否还留着「确定/取消」——用来判断上一次点击有没有被受理
JS_MODAL_ALIVE = r"""(()=>{
  const all = [].slice.call(document.querySelectorAll('*')).filter(function(e){
    return e.children.length === 0 && ['确定','取消'].indexOf((e.innerText||'').trim()) >= 0;
  }).filter(function(e){ const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; });
  return all.length;
})()"""

# 按文案 + 目标纵坐标定位并派发**完整指针/鼠标事件序列**。
# 真实点击在这个页面会被静默吞掉（坐标对、elementFromPoint 也对，就是没反应），
# 而只派发 click 又会被依赖 mousedown/hover 的组件忽略，所以整串事件都要发。
JS_DOM_SEQ = r"""(()=>{
  const kw = __KW__, wantY = __Y__;
  const list = [].slice.call(document.querySelectorAll('*')).filter(function(e){
    return e.children.length === 0 && (e.innerText || '').trim() === kw;
  }).map(function(e){ return {el: e, r: e.getBoundingClientRect()}; })
    .filter(function(o){ return o.r.width > 0 && o.r.height > 0; });
  if (!list.length) return 'NO_BTN';
  list.sort(function(a, b){
    return Math.abs((a.r.top + a.r.height / 2) - wantY) - Math.abs((b.r.top + b.r.height / 2) - wantY);
  });
  const o = list[0];
  const x = Math.round(o.r.left + o.r.width / 2), y = Math.round(o.r.top + o.r.height / 2);
  ['pointerover','pointerenter','mouseover','mouseenter','pointermove','mousemove',
   'pointerdown','mousedown','pointerup','mouseup','click'].forEach(function(type){
    const Ctor = (type.indexOf('pointer') === 0 && window.PointerEvent) ? PointerEvent : MouseEvent;
    try {
      o.el.dispatchEvent(new Ctor(type, {bubbles: true, cancelable: true, view: window,
        clientX: x, clientY: y, button: 0, buttons: 1,
        pointerId: 1, pointerType: 'mouse', isPrimary: true}));
    } catch (_) {}
  });
  return 'DOM_SEQ@' + x + ',' + y;
})()"""

JS_FIND = r"""(()=>{
  const kw = __KW__;
  const cands = [].slice.call(document.querySelectorAll('*'))
    .filter(function(e){ const t=(e.innerText||'').trim(); return t.indexOf(kw)>=0 && t.length<160; });
  if(!cands.length) return JSON.stringify({err:'NO_TITLE'});
  cands.sort(function(a,b){ return (a.innerText||'').length - (b.innerText||'').length; });
  const len0 = (cands[0].innerText||'').trim().length;
  // 同标题可能有多条（重发过的作品会并存）→ 全部返回，由调用方按时间挑
  const titles = cands.filter(function(e){ return (e.innerText||'').trim().length <= len0; });
  const btns = [].slice.call(document.querySelectorAll('*'))
    .filter(function(e){ return e.children.length===0 && (e.innerText||'').trim()==='删除作品'; })
    .map(function(e){ const r=e.getBoundingClientRect();
      return {x:Math.round(r.x+r.width/2), y:Math.round(r.y+r.height/2), top:r.top}; });
  if(!btns.length) return JSON.stringify({err:'NO_BTN'});
  const items = titles.map(function(t){
    const tr = t.getBoundingClientRect();
    let card = t, timeText = '';
    for (let i = 0; i < 10 && card.parentElement; i++) {          // 往上找卡片里的发布日期
      card = card.parentElement;
      const m = (card.innerText || '').match(/20\d\d年\d\d月\d\d日\s+\d\d:\d\d/);
      if (m) { timeText = m[0].replace(/\s+/g, ' '); break; }
    }
    const sorted = btns.slice().sort(function(a,b){ return Math.abs(a.top-tr.top) - Math.abs(b.top-tr.top); });
    const pick = sorted[0];
    return {titleText:(t.innerText||'').trim().slice(0, 60), timeText: timeText,
            titleY: Math.round(tr.top), btnY: Math.round(pick.top),
            delta: Math.round(Math.abs(pick.top - tr.top)), x: pick.x, y: pick.y};
  });
  return JSON.stringify({n: items.length, items: items});
})()"""

# 确认弹窗里的按钮（Semi Design modal）
JS_MODAL = r"""(()=>{
  const all = [].slice.call(document.querySelectorAll('*'))
    .filter(function(e){ return e.children.length===0; });
  const out = [];
  all.forEach(function(e){
    const t = (e.innerText||'').trim();
    if (!t || t.length > 8) return;
    if (['删除','确认删除','确定','取消','我再想想','删除作品'].indexOf(t) < 0) return;
    const r = e.getBoundingClientRect();
    if (r.width<=0 || r.height<=0) return;
    out.push({t:t, x:Math.round(r.x+r.width/2), y:Math.round(r.y+r.height/2),
              cls:String(e.className).slice(0,50)});
  });
  const body = document.body.innerText || '';
  const i = body.indexOf('删除');
  return JSON.stringify({btns: out, hint: i>=0 ? body.slice(Math.max(0,i-90), i+90).replace(/\n/g,' | ') : ''});
})()"""


def click(c, x, y):
    # 先解绑隐形遮挡，否则坐标对、也不报错，但点击被吃掉（见 cdp_read.NEUTRALIZE_JS）
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
    ap.add_argument("--title", required=True, help="作品标题关键词（须唯一）")
    ap.add_argument("--time", default=None,
                    help="只删发布日期含该串的那条，如 19:10 或 2026年09月18日 19:10（重发过的同名作品靠它区分）")
    ap.add_argument("--dry", action="store_true", help="只开弹窗看按钮，不确认（会自动点取消）")
    ap.add_argument("--max-delta", type=int, default=200, help="按钮与标题最大允许纵向偏差")
    ap.add_argument("--confirm-text", default="确定", help="确认按钮文案（2026-09-18 实测为「确定」）")
    ap.add_argument("--ready-timeout", type=float, default=30.0,
                    help="等内容管理页渲染出作品列表的最长秒数")
    a = ap.parse_args()

    # 残留的多个 content/manage 标签会让「第一个标签」指向过期快照 → 先收敛成一个
    killed = dedupe_tabs("content/manage", keep=1)
    if killed:
        print(f"（清理了 {killed} 个残留的管理页标签，避免读到过期快照）")
    ps = pages(9222, "content/manage")
    if not ps:
        print("ERROR: 没有 content/manage 标签页")
        return 1
    c = connect_retry(ps[0]["webSocketDebuggerUrl"])
    c.call("Page.enable")
    c.call("Page.bringToFront")
    try:      # 后台标签会被浏览器节流，点击容易被静默丢弃
        c.call("Emulation.setFocusEmulationEnabled", {"enabled": True})
    except Exception:
        pass
    try:
        # 关键：先确认列表**真的渲染出来了**再定位。
        # 固定 sleep 在慢加载时会把白屏当就绪，之后所有定位都落空（表现为 NO_TITLE）
        ok, n_btn, waited = wait_until(c, JS_MANAGE_READY, timeout=a.ready_timeout)
        if not ok:
            print(f"   列表未就绪（{waited:.1f}s，按钮数 {n_btn}），强制重载后再等")
            ok, n_btn, w2 = reload_and_wait(c, JS_MANAGE_READY, timeout=a.ready_timeout)
            waited += w2
        if not ok:
            print(f"ERROR: 内容管理页 {waited:.1f}s 内未渲染出作品列表，未执行删除")
            return 1
        print(f"   页面就绪（{waited:.1f}s，{n_btn} 个作品卡片）")

        raw = c.eval(JS_FIND.replace("__KW__", json.dumps(a.title, ensure_ascii=False)))
        d = json.loads(raw or "{}")
        if d.get("err"):
            print("ERROR:", d["err"], "|", raw)
            return 1
        items = d.get("items", [])
        print(f"匹配到 {len(items)} 条：")
        for i, it in enumerate(items):
            print("  [%d] %s | %s | delta=%d" % (i, it["titleText"][:40], it["timeText"] or "(无时间)", it["delta"]))

        if a.time:
            items = [it for it in items if a.time in (it["timeText"] or "")]
            if not items:
                print(f"ERROR: 没有发布时间含「{a.time}」的那条，未执行删除")
                return 1
            print(f"按时间「{a.time}」筛出 {len(items)} 条")
        if len(items) > 1:
            print("ERROR: 仍有多条无法区分，请加 --time 精确指定，未执行删除")
            return 1
        if not items:
            print("ERROR: 无候选")
            return 1

        tgt = items[0]
        print("标题:", tgt["titleText"], "| 发布:", tgt["timeText"])
        print("按钮纵坐标:", tgt["btnY"], "delta=", tgt["delta"])
        if tgt["delta"] > a.max_delta:
            print(f"!! delta={tgt['delta']} 超过上限 {a.max_delta}，判定为定位不可信，中止")
            return 1

        # 点「删除作品」→ 等确认弹窗真的出现。
        # 这个点击会被静默吞掉（现象：点完没有任何反应、也不报错），
        # 所以：先真实点击，验一次；没反应就换 DOM 事件序列，再验。
        opened, m = False, {}
        for attempt in range(1, 5):
            if attempt <= 2:
                click(c, tgt["x"], tgt["y"])
                how = "真实点击"
            else:
                how = c.eval(JS_DOM_SEQ
                             .replace("__KW__", json.dumps("删除作品", ensure_ascii=False))
                             .replace("__Y__", str(tgt["btnY"] + 9)))
            time.sleep(1.6)
            m = json.loads(c.eval(JS_MODAL) or "{}")
            if any(b["t"] == "取消" for b in m.get("btns", [])):
                opened = True
                if attempt > 1:
                    print(f"   确认弹窗出现（第 {attempt} 次以「{how}」生效）")
                break
            print(f"   确认弹窗未出现（{how}），重试第 {attempt} 次")
        if not opened:
            print("ERROR: 点「删除作品」后确认弹窗始终不出现，未执行删除")
            return 1
        print("弹窗按钮:", json.dumps(m.get("btns"), ensure_ascii=False))
        print("弹窗上下文:", (m.get("hint") or "")[:200])

        if a.dry:
            for b in m.get("btns", []):
                if b["t"] == "取消":
                    click(c, b["x"], b["y"])
                    print("已点「取消」关闭弹窗（dry-run，未删除）")
                    break
            return 0

        hit = [b for b in m.get("btns", []) if b["t"] == a.confirm_text]
        if not hit:
            print(f"ERROR: 弹窗里没找到「{a.confirm_text}」按钮，未执行删除")
            return 1
        # 确认按钮同样会「点了没反应」→ 真实点击与 DOM 事件序列轮换，各验一次
        done = False
        for attempt in range(1, 5):
            if attempt <= 2:
                click(c, hit[0]["x"], hit[0]["y"])
                how = "真实点击"
            else:
                how = c.eval(JS_DOM_SEQ
                             .replace("__KW__", json.dumps(a.confirm_text, ensure_ascii=False))
                             .replace("__Y__", str(hit[0]["y"])))
            time.sleep(1.6)
            if str(c.eval(JS_MODAL_ALIVE)) in ("0", "None", ""):
                done = True
                print(f"删除确认已受理（第 {attempt} 次以「{how}」生效）")
                break
            print(f"   确认弹窗仍在（{how}），重试第 {attempt} 次")
        if not done:
            print("ERROR: 确认按钮试了 4 次仍未受理，未删除")
            return 1
        time.sleep(2)
        tail = (c.eval("document.body.innerText") or "")[-200:].replace("\n", " | ")
        print("删除后页面尾部:", tail)
        return 0
    finally:
        c.close()


if __name__ == "__main__":
    raise SystemExit(main())
