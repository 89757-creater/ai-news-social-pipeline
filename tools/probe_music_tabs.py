#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""探测抖音配乐面板各页签的候选曲目（一次开面板，逐页签读）。

为什么要单独写：反复调 `douyin_music.py --list` 每次都要开关抽屉，
既慢又容易撞上「关闭不干净」的状态。这里开一次面板，然后逐个页签切换 + 读卡片，
顺带**往下滚几次**把懒加载的曲目也带出来（`--list` 只读首屏）。

用法：python probe_music_tabs.py [--tabs 纯音乐 卡点 DJ] [--scroll 3]
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

# 找面板内可滚动的容器，把它滚到底以触发懒加载
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tabs", nargs="*",
                    default=["推荐", "热门榜", "收藏", "飙升榜", "原创榜", "卡点",
                             "纯音乐", "旅行", "DJ", "搞笑", "流行", "伤感"])
    ap.add_argument("--scroll", type=int, default=3, help="每个页签下滑次数（触发懒加载）")
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
        for tb in a.tabs:
            r = c.eval(JS_TAB.replace("__T__", json.dumps(tb, ensure_ascii=False)))
            if r != "OK":
                print(f"\n--- {tb}: {r}（跳过）")
                continue
            time.sleep(2.5)
            active = c.eval(JS_ACTIVE)
            seen, order = {}, []
            for _ in range(a.scroll + 1):
                for k in json.loads(c.eval(JS_CARDS) or "[]"):
                    key = (k["name"], k["sub"])
                    if key not in seen:
                        seen[key] = k
                        order.append(k)
                c.eval(JS_SCROLL)
                time.sleep(1.2)
            print(f"\n--- {tb}（active={active}，共 {len(order)} 条）")
            for i, k in enumerate(order):
                print(f"[{i:2d}] {k['name'][:30]:32s} | {k['sub'][:16]:18s} | {k['dur']:6s} | {k['count']}")
        return 0
    finally:
        c.close()


if __name__ == "__main__":
    raise SystemExit(main())
