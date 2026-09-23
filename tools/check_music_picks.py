#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""发稿前预检：MUSIC_BY_DATE 里每首配乐**是否真的能在指定页签选中**。

为什么要有这一步：抖音配乐面板是「页签 + 首屏候选」结构，
曲名搜索只在该页签首屏里做（`douyin_music.py --tab X --keyword Y`）。
候选池里有的曲子分布在别的页签，一旦页签写错，要等到整篇发稿跑到第 5 步
才发现选不上 —— 那时稿子、头图、封面都已经填进去了，白跑一趟。

这里**一次开面板**把 4 首全验一遍，只读+试选，不发布。

用法：python check_music_picks.py [--date 2026-09-14 ...]
"""
import argparse
import io
import json
import sys
import time
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

WS = Path(r"C:/Users/suge0/WorkBuddy/automation-2026-09-13-16-27-29")
sys.path.insert(0, str(WS / "tools"))
from cdp_read import CDP, pages  # noqa: E402
import douyin_post_article as P  # noqa: E402

JS_OPEN = """
(()=>{
  if(document.querySelector('.semi-sidesheet-content')) return 'ALREADY_OPEN';
  const kws=['选择音乐','修改音乐','添加音乐','点击添加音乐','更换音乐','替换音乐'];
  for(const k of kws){
    const s=[...document.querySelectorAll('span,div,button')]
      .find(e=>e.children.length===0 && (e.innerText||'').trim()===k);
    if(s){ s.click(); return 'CLICKED:'+k; }
  }
  return 'NO_ENTRY';
})()"""

JS_TAB = """
(()=>{
  const t=[...document.querySelectorAll('.semi-tabs-tab')].find(e=>(e.innerText||'').trim()===__T__);
  if(!t) return 'NO_TAB'; t.click(); return 'OK';
})()"""

JS_ACTIVE = "(()=>{const t=document.querySelector('.semi-tabs-tab-active');return t?t.innerText.trim():'NONE';})()"

# ⚠️ 抽屉关闭后 `.semi-sidesheet-content` 这个节点**仍然留在 DOM 里**，
# 所以「节点存在」不能当「面板开着」的判据（会被空壳骗到，随后一张卡片都读不到）。
# 真正的判据是**页签渲染出来了**。
JS_PANEL_READY = "(()=>{return document.querySelectorAll('.semi-tabs-tab').length;})()"

JS_ESC = None  # 见 open_panel 里的 Input.dispatchKeyEvent

# 在当前页签首屏里按曲名找卡片并点「使用」，返回是否命中
JS_USE_BY_NAME = """
(()=>{
  const kw=__KW__;
  const cards=[...document.querySelectorAll('div[class*=card-container-]')]
    .filter(e=>!/card-container-right/.test(e.className));
  for(const card of cards){
    const btn=[...card.querySelectorAll('button')].find(b=>/^使用$/.test((b.innerText||'').trim()));
    if(!btn) continue;
    const lines=(card.innerText||'').split('\\n').map(s=>s.trim()).filter(Boolean).filter(s=>s!=='使用');
    if((lines[0]||'').indexOf(kw)>=0 || (lines[1]||'').indexOf(kw)>=0){
      btn.click();
      return JSON.stringify({hit:true, name:lines[0]||'', sub:lines[1]||'', count:lines.find(l=>/人使用/.test(l))||''});
    }
  }
  const names=cards.map(c=>(c.innerText||'').split('\\n').map(s=>s.trim()).filter(Boolean)[0]).filter(Boolean);
  return JSON.stringify({hit:false, available:names.slice(0,20)});
})()"""

JS_BLOCK = """(()=>{const t=document.body.innerText;const i=t.indexOf('选择配乐');
  return i>=0?t.slice(i,i+70).replace(/\\n/g,' | '):'NO_BLOCK';})()"""


EDITOR_URL = "https://creator.douyin.com/creator-micro/content/post/article?default-tab=5"

# 页面「真的可用」的判据：配乐入口文案出现（选择音乐 / 修改音乐）
JS_EDITOR_READY = """
(()=>{return [].slice.call(document.querySelectorAll('span,div,button'))
  .filter(e=>e.children.length===0 && /^(选择音乐|修改音乐|添加音乐)$/.test((e.innerText||'').trim())).length;})()"""


def reload_editor(c, timeout=40.0):
    """重载编辑器页。

    为什么必须重载：配乐抽屉被「关得不干净」之后会进入坏状态 ——
    `.semi-sidesheet-content` 节点还在、页签文本也读得到，但**曲目列表不再渲染**
    （`card-container-*` 为 0、`使用` 按钮为 0，`content-visibility` 把子树判成了不可见）。
    此时任何「打开面板」的尝试都是无效的，重开也不行，只有重载页面能复位。
    编辑器是空稿，重载没有任何损失。
    """
    c.call("Page.enable")
    c.call("Page.bringToFront")
    c.call("Page.navigate", {"url": EDITOR_URL})
    t0 = time.time()
    while time.time() - t0 < timeout:
        time.sleep(1.5)
        if int(c.eval(JS_EDITOR_READY) or 0) >= 1:
            print(f"   编辑器已就绪（{time.time() - t0:.1f}s）")
            return True
    return False


def open_panel(c, tries=4):
    """确保配乐抽屉**真的打开**（判据：页签渲染出来了），返回 True/False。"""
    for i in range(1, tries + 1):
        if int(c.eval(JS_PANEL_READY) or 0) >= 5:
            print(f"   面板已就绪（第 {i} 次检查）")
            return True
        r = c.eval(JS_OPEN)
        n = 0
        for _ in range(15):
            time.sleep(1.0)
            n = int(c.eval(JS_PANEL_READY) or 0)
            if n >= 5:
                break
        if n >= 5:
            print(f"   面板已打开（{r}，{n} 个页签）")
            return True
        print(f"   第 {i} 次打开未生效（{r}，页签数 {n}），按 Esc 后重试")
        for et in ("keyDown", "keyUp"):
            c.call("Input.dispatchKeyEvent", {"type": et, "key": "Escape", "code": "Escape",
                                              "windowsVirtualKeyCode": 27, "nativeVirtualKeyCode": 27})
        time.sleep(1.5)
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", nargs="*", default=list(P.MUSIC_BY_DATE))
    a = ap.parse_args()

    ps = [p for p in pages(9222) if "post/article" in (p.get("url") or "")]
    if not ps:
        print("ERROR: 没有 content/post/article 标签页")
        return 1
    c = CDP(ps[0]["webSocketDebuggerUrl"])
    c.call("Runtime.enable")
    fails = []
    try:
        if not reload_editor(c):
            print("ERROR: 编辑器页重载后仍未就绪")
            return 1
        if not open_panel(c):
            print("ERROR: 配乐面板打不开")
            return 1
        for d in a.date:
            tab, name, why = P.resolve_music(d)
            cur = c.eval(JS_ACTIVE)
            if cur != tab:
                r = c.eval(JS_TAB.replace("__T__", json.dumps(tab, ensure_ascii=False)))
                if r != "OK":
                    print(f"FAIL {d} 页签「{tab}」不存在")
                    fails.append(d)
                    continue
                time.sleep(2.5)
                if c.eval(JS_ACTIVE) != tab:
                    print(f"FAIL {d} 页签切到「{tab}」失败")
                    fails.append(d)
                    continue
            res = json.loads(c.eval(JS_USE_BY_NAME.replace("__KW__", json.dumps(name, ensure_ascii=False))))
            if not res.get("hit"):
                print(f"FAIL {d} [{tab}] 找不到「{name}」；该页签首屏有：{res.get('available')}")
                fails.append(d)
                continue
            # ⚠️ 配乐区的 DOM 文案**更新滞后**于点击（实测会慢一拍）——
            # 固定 sleep 2s 读回会拿到上一首，误判成"选错了"。必须轮询等目标值出现。
            block, matched, waited = "", False, 0.0
            for _ in range(16):
                time.sleep(1.0)
                waited += 1.0
                block = c.eval(JS_BLOCK)
                if P.music_matches(name, block):
                    matched = True
                    break
            print(f"{'OK  ' if matched else 'FAIL'} {d} [{tab}] {res['name']} | {res['sub']} | {res['count']}"
                  f"（回读用时 {waited:.0f}s）")
            print(f"      配乐区回读: {block}")
            if not matched:
                fails.append(d)
    finally:
        c.close()
    print()
    if fails:
        print("❌ 预检未通过：", fails)
        return 1
    print("✅ 4 首配乐全部可在指定页签选中")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
