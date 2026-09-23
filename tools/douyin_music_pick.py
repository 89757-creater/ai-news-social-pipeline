#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""抖音文章 · 配乐选择（**支持滚动到首屏之后** + **支持按风格词搜索**）

为什么需要它（一）：`douyin_music.py --tab X --keyword Y` 只在页签**首屏**的
渲染 DOM 里找曲名。而「纯音乐」页签共 73 条，真正可用的曲目大量落在首屏之后
（实测 `Midnight Drift` 在第 57 条）—— 首屏找不到就直接 ERROR，
调用方会误以为是"这首不在这个页签里"。

为什么需要它（二）：配乐面板 12 个页签里**没有「爵士」「R&B」这类风格页签**，
用户 2026-09-21 把配乐风格定为 R&B / 爵士 / 后朋克 之后，只能走面板顶部的
`input[placeholder="搜索音乐"]` 按风格词检索 → `--search 爵士`。

用法：
  python douyin_music_pick.py --search "爵士" --list            # 先看风格下有什么
  python douyin_music_pick.py --search "爵士" --keyword "夜上海"  # 搜风格 → 按曲名选中
  python douyin_music_pick.py --tab "纯音乐" --keyword "Midnight Drift"
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

JS_OPEN = """
(()=>{
  if(document.querySelector('.semi-sidesheet-content')) return 'ALREADY_OPEN';
  const kws=['选择音乐','修改音乐','添加音乐','点击添加音乐','更换音乐','替换音乐'];
  for(const k of kws){
    const s=[...document.querySelectorAll('span,div,button')]
      .find(e=>e.children.length===0 && (e.innerText||'').trim()===k);
    if(s){ s.click(); return 'CLICKED:'+k; }
  }
  const act=[...document.querySelectorAll('[class*=action-]')]
    .find(e=>/音乐/.test((e.innerText||'').trim()));
  if(act){ act.click(); return 'CLICKED:action'; }
  return 'NO_ENTRY';
})()"""

JS_TAB = """
(()=>{
  const t=[...document.querySelectorAll('.semi-tabs-tab')].find(e=>(e.innerText||'').trim()===__T__);
  if(!t) return 'NO_TAB';
  t.click(); return 'OK';
})()"""

JS_ACTIVE = "(()=>{const t=document.querySelector('.semi-tabs-tab-active');return t?t.innerText.trim():'NONE';})()"

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
  return 'SCROLLED:' + best.scrollTop + '/' + best.scrollHeight;
})()"""

# 滚动加载完之后，按 (曲名, 作者) 命中并点它的「使用」
JS_USE_BY_NAME = """
(()=>{
  const cards=[...document.querySelectorAll('div[class*=card-container-]')]
    .filter(e=>!/card-container-right/.test(e.className));
  const pairs=[];
  for(const card of cards){
    const btn=[...card.querySelectorAll('button')].find(b=>/^使用$/.test((b.innerText||'').trim()));
    if(!btn) continue;
    const lines=(card.innerText||'').split('\\n').map(s=>s.trim()).filter(Boolean).filter(s=>s!=='使用');
    pairs.push({btn:btn, name:lines[0]||'', sub:lines[1]||'', count:lines.find(l=>/人使用/.test(l))||''});
  }
  let i = pairs.findIndex(p=>p.name.indexOf(__K__)>=0 || p.sub.indexOf(__K__)>=0);
  if(i < 0) return 'NOT_FOUND:' + pairs.length;
  pairs[i].btn.click();
  return JSON.stringify({idx:i, name:pairs[i].name, sub:pairs[i].sub, count:pairs[i].count});
})()"""

JS_MUSIC_BLOCK = """(()=>{
  const t=document.body?document.body.innerText:'';
  const i=t.indexOf('选择配乐');
  return i>=0 ? t.slice(i, i+110).replace(/\\n/g,' | ') : 'NO_BLOCK';
})()"""

JS_CLOSE = """
(()=>{
  const b=[...document.querySelectorAll('button')].find(e=>/semi-sidesheet-close/.test(e.className||''));
  if(!b) return 'NO_CLOSE';
  b.click(); return 'CLOSED';
})()"""

# 面板顶部的风格搜索框：input[placeholder="搜索音乐"]
# 受控输入 → 原生 setter + input/change + Enter（部分实现要真实回车才触发检索）
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tab", default="纯音乐")
    ap.add_argument("--search", default=None, help="按风格词走搜索框（如 爵士 / R&B）；给定时忽略 --tab")
    ap.add_argument("--keyword", default=None)
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--scroll", type=int, default=3)
    ap.add_argument("--keep-open", action="store_true")
    a = ap.parse_args()

    ps = [p for p in pages(9222) if "post/article" in (p.get("url") or "")]
    if not ps:
        print("ERROR: 没有 content/post/article 标签页")
        return 1
    c = CDP(ps[0]["webSocketDebuggerUrl"])
    c.call("Runtime.enable")
    try:
        print("打开面板:", c.eval(JS_OPEN))
        time.sleep(2.5)

        if a.search:
            r = c.eval(JS_TYPE_SEARCH.replace("__K__", json.dumps(a.search, ensure_ascii=False)))
            print("风格搜索:", r)
            if isinstance(r, str) and r.startswith("NO_INPUT"):
                print("ERROR: 面板里没找到「搜索音乐」输入框")
                return 1
            time.sleep(3.5)
        else:
            r = c.eval(JS_TAB.replace("__T__", json.dumps(a.tab, ensure_ascii=False)))
            if r != "OK":
                print(f"ERROR: 没找到页签「{a.tab}」")
                return 1
            time.sleep(2.5)
            print("当前页签:", c.eval(JS_ACTIVE))

        seen, order = {}, []
        for _ in range(a.scroll + 1):
            for k in json.loads(c.eval(JS_CARDS) or "[]"):
                key = (k["name"], k["sub"])
                if key not in seen:
                    seen[key] = k
                    order.append(k)
            c.eval(JS_SCROLL)
            time.sleep(1.2)
        print(f"候选池: {len(order)} 条（含滚动懒加载）")

        if a.list:
            for i, k in enumerate(order):
                print(f"[{i:2d}] {k['name'][:30]:32s} | {k['sub'][:16]:18s} | {k['dur']:6s} | {k['count']}")
            if not a.keep_open:
                print("关闭面板:", c.eval(JS_CLOSE))
            return 0

        if not a.keyword:
            print("ERROR: 需要 --keyword（或 --list 先看）")
            return 1

        res = c.eval(JS_USE_BY_NAME.replace("__K__", json.dumps(a.keyword, ensure_ascii=False)))
        if isinstance(res, str) and res.startswith("NOT_FOUND"):
            print(f"ERROR: 滚动后仍未找到「{a.keyword}」（候选池 {res.split(':')[1]} 条）")
            return 1
        info = json.loads(res)
        time.sleep(3)
        print(f"已选择: [{info['idx']}] {info['name']} | {info['sub']} | {info['count']}")

        if not a.keep_open:
            print("关闭面板:", c.eval(JS_CLOSE))
            time.sleep(1)
        print("当前配乐区:", c.eval(JS_MUSIC_BLOCK))
        return 0
    finally:
        c.close()


if __name__ == "__main__":
    raise SystemExit(main())
