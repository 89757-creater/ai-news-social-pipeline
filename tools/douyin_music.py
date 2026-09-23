#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""抖音文章 · 配乐选择（CDP）

为什么需要它：抖音「文章」体裁支持配乐，但配乐只能在发布/编辑时设置。
**已发布的文章没有编辑入口**（2026-09-18 实测：4 篇文章体裁作品均只有
「设置权限 / 作品置顶 / 删除作品」）——所以配乐必须写进**发稿流程**，
本脚本就是那一步。

⚠️ 踩坑记录（2026-09-18）：音乐面板是右侧抽屉（semi-sidesheet），
在 1031px 宽的窗口里它渲染在 x≈1152，**整个在视口外**，
`elementFromPoint` 返回 null、坐标点击必然落空。
解法：**用 DOM 原生 `.click()` 派发**——实测对页签和「使用」按钮都生效，
且不受元素是否在视口内影响。（此前「DOM .click() 对 React 无效」的经验
不适用于 Semi Design 的这套组件，已用 `t.click()` 验证：页签即刻切换。）

用法：
  python douyin_music.py --tab "纯音乐" --list          # 先看再选，别盲点
  python douyin_music.py --tab "纯音乐" --keyword "太清"  # 按曲名/作者匹配
  python douyin_music.py --tab "纯音乐" --index 6        # 按序号（配合 --list）
  python douyin_music.py --current                      # 读当前已选配乐

前置：文章编辑器页面已打开（content/post/article）。
"""
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cdp_read import CDP, list_targets  # noqa: E402

TABS = ["推荐", "热门榜", "收藏", "飙升榜", "原创榜", "卡点", "纯音乐", "旅行", "DJ", "搞笑", "流行", "伤感"]

# 曲目卡片容器 .card-container-*（排除 .card-container-right-*，那是右侧计数块）
# 卡片 innerText 形如：曲名 / 作者 / 时长 / N万人使用
JS_CARDS = """
(()=>{
  const cards=[...document.querySelectorAll('div[class*=card-container-]')]
    .filter(e=>!/card-container-right/.test(e.className));
  const out=[];
  for(const card of cards){
    const btn=[...card.querySelectorAll('button')].find(b=>/^使用$/.test((b.innerText||'').trim()));
    if(!btn) continue;
    const lines=(card.innerText||'').split('\\n').map(s=>s.trim()).filter(Boolean).filter(s=>s!=='使用');
    out.push({name: lines[0]||'', sub: lines[1]||'', dur: lines[2]||'',
              count: lines.find(l=>/人使用/.test(l))||''});
  }
  return JSON.stringify(out);
})()
"""

JS_ACTIVE_TAB = "(()=>{const t=document.querySelector('.semi-tabs-tab-active'); return t?t.innerText.trim():'NONE';})()"

JS_PICK_TAB = """
(()=>{
  const t=[...document.querySelectorAll('.semi-tabs-tab')].find(e=>(e.innerText||'').trim()===TABNAME);
  if(!t) return 'NO_TAB';
  t.click();
  return 'OK';
})()
"""

# 按序号点第 N 张卡片的「使用」
JS_USE_BY_INDEX = """
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
  if(IDX < 0 || IDX >= pairs.length) return 'IDX_OUT_OF_RANGE:' + pairs.length;
  pairs[IDX].btn.click();
  return JSON.stringify({name:pairs[IDX].name, sub:pairs[IDX].sub, count:pairs[IDX].count});
})()
"""

JS_OPEN_PANEL = """
(()=>{
  if(document.querySelector('.semi-sidesheet-content')) return 'ALREADY_OPEN';
  // 入口文案随状态变：未选配乐时是「添加/选择音乐」，已选配乐时是「修改音乐」
  const kws=['选择音乐','修改音乐','添加音乐','点击添加音乐','更换音乐','替换音乐'];
  for(const k of kws){
    const s=[...document.querySelectorAll('span,div,button')]
      .find(e=>e.children.length===0 && (e.innerText||'').trim()===k);
    if(s){ s.click(); return 'CLICKED:'+k; }
  }
  // 兜底：配乐区块里的 action 类按钮（class 形如 action-XXXX）
  const act=[...document.querySelectorAll('[class*=action-]')]
    .find(e=>/音乐/.test((e.innerText||'').trim()));
  if(act){ act.click(); return 'CLICKED:action'; }
  return 'NO_ENTRY';
})()
"""

JS_CLOSE_PANEL = """
(()=>{
  const b=[...document.querySelectorAll('button')].find(e=>/semi-sidesheet-close/.test(e.className||''));
  if(!b) return 'NO_CLOSE';
  b.click();
  return 'CLOSED';
})()
"""

JS_MUSIC_BLOCK = """(()=>{
  const t=document.body?document.body.innerText:'';
  const i=t.indexOf('选择配乐');
  return i>=0 ? t.slice(i, i+100).replace(/\\n/g,' | ') : 'NO_BLOCK';
})()"""


def connect():
    pages = [t for t in list_targets(9222)
             if t.get("type") == "page" and "post/article" in (t.get("url") or "")]
    if not pages:
        print("ERROR: 未找到抖音文章编辑器页面（content/post/article）")
        return None
    c = CDP(pages[0]["webSocketDebuggerUrl"])
    c.call("Runtime.enable")
    return c


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tab", default=None, help="分类页签：" + " / ".join(TABS))
    ap.add_argument("--keyword", default=None, help="按曲名或作者匹配")
    ap.add_argument("--index", type=int, default=None, help="按序号选中（0-based）")
    ap.add_argument("--list", action="store_true", help="只列出，不点选")
    ap.add_argument("--current", action="store_true", help="读当前已选中的配乐")
    ap.add_argument("--keep-open", action="store_true", help="选完后不关闭面板")
    a = ap.parse_args()

    c = connect()
    if c is None:
        return 1
    try:
        if a.current:
            print("当前配乐区:", c.eval(JS_MUSIC_BLOCK))
            return 0

        r = c.eval(JS_OPEN_PANEL)
        print("打开音乐面板:", r)
        if r == "NO_ENTRY":
            return 1
        time.sleep(2)

        if a.tab:
            if a.tab not in TABS:
                print(f"ERROR: --tab 只支持 {TABS}")
                return 1
            r = c.eval(JS_PICK_TAB.replace("TABNAME", f'"{a.tab}"'))
            if r == "NO_TAB":
                print(f"ERROR: 没找到页签「{a.tab}」")
                return 1
            time.sleep(3)
            active = c.eval(JS_ACTIVE_TAB)
            print(f"当前页签: {active}")
            if active != a.tab:
                print(f"ERROR: 页签切换失败（期望 {a.tab}，实际 {active}）")
                return 1

        cards = json.loads(c.eval(JS_CARDS))
        if not cards:
            print("ERROR: 面板里没读到曲目（可能还在加载，稍后重试）")
            return 1

        if a.list:
            for i, k in enumerate(cards):
                print(f"[{i:2d}] {k['name'][:26]:28s} | {k['sub'][:14]:16s} | {k['dur']:6s} | {k['count']}")
            # ⚠️ 列完必须收面板：留着它会在后续上传时盖住「编辑封面」弹窗的「完成」按钮，
            #    点击静默失效（2026-09-18 实测，排查成本很高）。
            if not a.keep_open:
                print("关闭面板:", c.eval(JS_CLOSE_PANEL))
                time.sleep(1)
                sheet = c.eval("(()=>{const l=document.querySelectorAll('[class*=semi-sidesheet]');"
                               "for(let i=0;i<l.length;i++){const r=l[i].getBoundingClientRect();"
                               "if(r.width>0&&r.height>0) return true;} return false;})()")
                if sheet:
                    for et in ("keyDown", "keyUp"):
                        c.call("Input.dispatchKeyEvent", {"type": et, "key": "Escape", "code": "Escape",
                                                          "windowsVirtualKeyCode": 27, "nativeVirtualKeyCode": 27})
                    time.sleep(0.8)
                    print("   Esc 兜底后再查抽屉:",
                          c.eval("(()=>{const l=document.querySelectorAll('[class*=semi-sidesheet]');"
                                 "for(let i=0;i<l.length;i++){const r=l[i].getBoundingClientRect();"
                                 "if(r.width>0&&r.height>0) return 'STILL_OPEN';} return 'CLOSED';})()"))
            return 0

        if a.keyword:
            idx = next((i for i, k in enumerate(cards) if a.keyword in k["name"] or a.keyword in k["sub"]), None)
            if idx is None:
                print(f"ERROR: 没有匹配「{a.keyword}」的曲目；用 --list 看可选项")
                return 1
        elif a.index is not None:
            idx = a.index
        else:
            print("ERROR: 需要 --keyword 或 --index（或 --list 先看）")
            return 1

        res = c.eval(JS_USE_BY_INDEX.replace("IDX", str(idx)))
        if isinstance(res, str) and res.startswith("IDX_OUT_OF_RANGE"):
            print(f"ERROR: --index 越界（共 {res.split(':')[1]} 条）")
            return 1
        info = json.loads(res)
        time.sleep(3)
        print(f"已选择: [{idx}] {info['name']} | {info['sub']} | {info['count']}")

        if not a.keep_open:
            print("关闭面板:", c.eval(JS_CLOSE_PANEL))
            time.sleep(1)
        print("当前配乐区:", c.eval(JS_MUSIC_BLOCK))
    finally:
        c.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
