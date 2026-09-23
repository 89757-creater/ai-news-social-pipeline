#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""抖音配乐面板 · 输入框侦察 + 按关键词搜索（用于按「风格」找曲）

背景：配乐面板有 12 个页签（推荐/热门榜/飙升榜/原创榜/卡点/纯音乐/旅行/DJ/搞笑/流行/伤感…），
**没有「爵士」「R&B」「后朋克」这类风格页签**。要按风格选曲只有两条路：
  ① 用面板里的搜索框直接搜风格词；
  ② 逐个页签翻（慢且盲）。
本脚本先确认有没有搜索框，有就直接搜。

用法：
  python probe_music_search.py --dump                     # 只侦察：列出面板里的输入框
  python probe_music_search.py --search "爵士"             # 搜关键词并列出结果
  python probe_music_search.py --search "R&B" --scroll 2
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

EDITOR_URL = "https://creator.douyin.com/creator-micro/content/post/article?default-tab=5"

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

# 侦察：面板里所有可见输入框（含 placeholder / class），以及面板顶部文案
JS_DUMP_INPUTS = """
(()=>{
  const root=document.querySelector('.semi-sidesheet-content')||document.body;
  const r=root.getBoundingClientRect();
  const ins=[...root.querySelectorAll('input,textarea')].map(function(e,i){
    const b=e.getBoundingClientRect();
    return {i:i, tag:e.tagName, type:e.type||'', ph:(e.placeholder||e.getAttribute('data-placeholder')||''),
            cls:(e.className||'').slice(0,80), box:[Math.round(b.x),Math.round(b.y),Math.round(b.width),Math.round(b.height)],
            vis:(b.width>0&&b.height>0)};
  });
  return JSON.stringify({sheet:[Math.round(r.x),Math.round(r.y),Math.round(r.width),Math.round(r.height)],
                         inputs:ins, head:(root.innerText||'').slice(0,220).replace(/\\n/g,' | ')});
})()"""

JS_CARDS = """
(()=>{
  const cards=[...document.querySelectorAll('div[class*=card-container-]')]
    .filter(e=>!/card-container-right/.test(e.className));
  const out=[];
  for(const card of cards){
    const btn=[...card.querySelectorAll('button')].find(b=>/^使用$/.test((b.innerText||'').trim()));
    if(!btn) continue;
    const lines=(card.innerText||'').split('\\n').map(s=>s.trim()).filter(Boolean).filter(s=>s!=='使用');
    out.push({name:lines[0]||'', sub:lines[1]||'', dur:lines[2]||'',
              count:lines.find(l=>/人使用/.test(l))||''});
  }
  return JSON.stringify(out);
})()"""

JS_SCROLL = """
(()=>{
  const root=document.querySelector('.semi-sidesheet-content') || document.body;
  const cands=[...root.querySelectorAll('div')]
    .filter(e=>e.scrollHeight > e.clientHeight + 40);
  if(!cands.length) return 'NO_SCROLLER';
  let best=cands[0];
  for(const e of cands) if(e.scrollHeight-e.clientHeight > best.scrollHeight-best.clientHeight) best=e;
  best.scrollTop = best.scrollHeight;
  return 'SCROLLED';
})()"""

# 受控输入：原生 setter + 完整指针/键盘事件序列，最后回车
JS_TYPE_SEARCH = """
(()=>{
  const root=document.querySelector('.semi-sidesheet-content')||document.body;
  const el=[...root.querySelectorAll('input,textarea')].filter(function(e){
    const b=e.getBoundingClientRect(); return b.width>40 && b.height>10;})[0];
  if(!el) return 'NO_INPUT';
  const proto = el.tagName==='TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
  const setter = Object.getOwnPropertyDescriptor(proto,'value').set;
  el.focus();
  setter.call(el, __K__);
  el.dispatchEvent(new Event('input',{bubbles:true}));
  el.dispatchEvent(new Event('change',{bubbles:true}));
  el.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',code:'Enter',keyCode:13,which:13,bubbles:true}));
  el.dispatchEvent(new KeyboardEvent('keyup',{key:'Enter',code:'Enter',keyCode:13,which:13,bubbles:true}));
  return 'TYPED:' + el.value;
})()"""

JS_PRESS_ENTER = """
(()=>{
  const root=document.querySelector('.semi-sidesheet-content')||document.body;
  const el=[...root.querySelectorAll('input,textarea')].filter(function(e){
    const b=e.getBoundingClientRect(); return b.width>40 && b.height>10;})[0];
  if(!el) return 'NO_INPUT';
  el.focus();
  el.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',code:'Enter',keyCode:13,which:13,bubbles:true}));
  el.dispatchEvent(new KeyboardEvent('keyup',{key:'Enter',code:'Enter',keyCode:13,which:13,bubbles:true}));
  return 'ENTERED';
})()"""


def get_cdp():
    ps = [p for p in pages(9222) if "post/article" in (p.get("url") or "")]
    if not ps:
        return None
    c = CDP(ps[0]["webSocketDebuggerUrl"])
    c.call("Runtime.enable")
    return c


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dump", action="store_true")
    ap.add_argument("--search", default=None)
    ap.add_argument("--scroll", type=int, default=2)
    ap.add_argument("--keep-open", action="store_true")
    a = ap.parse_args()

    c = get_cdp()
    if c is None:
        print("ERROR: 没有 content/post/article 标签页")
        return 1
    try:
        print("打开面板:", c.eval(JS_OPEN))
        time.sleep(2.5)

        if a.dump:
            print(c.eval(JS_DUMP_INPUTS))
            return 0

        if a.search:
            r = c.eval(JS_TYPE_SEARCH.replace("__K__", json.dumps(a.search, ensure_ascii=False)))
            print("输入搜索词:", r)
            time.sleep(3)
            if isinstance(r, str) and r.startswith("TYPED:"):
                # 有些实现需要真实按键才触发检索
                c.eval(JS_PRESS_ENTER)
            time.sleep(2.5)

            seen, order = {}, []
            for _ in range(a.scroll + 1):
                for k in json.loads(c.eval(JS_CARDS) or "[]"):
                    key = (k["name"], k["sub"])
                    if key not in seen:
                        seen[key] = k
                        order.append(k)
                c.eval(JS_SCROLL)
                time.sleep(1.2)
            print(f"「{a.search}」候选 {len(order)} 条：")
            for i, k in enumerate(order):
                print(f"[{i:2d}] {k['name'][:30]:32s} | {k['sub'][:16]:18s} | {k['dur']:6s} | {k['count']}")
            return 0

        print("ERROR: 需要 --dump 或 --search")
        return 1
    finally:
        c.close()


if __name__ == "__main__":
    raise SystemExit(main())
