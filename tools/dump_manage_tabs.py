#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""诊断：列出所有 content/manage 标签的加载状态与是否含目标标题。

为什么要这个：`page_ws()` / `douyin_delete.py` 都取「第一个 URL 含 content/manage 的标签」，
但反复跑会残留多个管理页标签，其中**旧的仍停在上一次加载的快照**。
如果标签顺序在两次调用之间发生变化，删除脚本就可能读到「过期快照」→ 报 NO_TITLE。
"""
import json
import re
import sys
from pathlib import Path

WS = Path(r"C:/Users/suge0/WorkBuddy/automation-2026-09-13-16-27-29")
sys.path.insert(0, str(WS / "tools"))
from cdp_read import CDP, list_targets  # noqa: E402

JS = r"""(()=>{
  const txt = document.body.innerText || '';
  const m = txt.match(/作品 \((\d+)\)/);
  const btns = [].slice.call(document.querySelectorAll('*')).filter(function(e){
    return e.children.length === 0 && (e.innerText || '').trim() === '删除作品';
  });
  const titles = [].slice.call(document.querySelectorAll('*')).filter(function(e){
    const t = (e.innerText || '').trim();
    return t.indexOf('AI 写了 7.5 万行代码') >= 0 && t.length < 160;
  }).map(function(e){ return (e.innerText || '').trim().slice(0, 70); });
  return JSON.stringify({len: txt.length, posts: m ? m[1] : null,
                         delBtns: btns.length, ready: btns.length > 0,
                         hitTitle: titles, head: txt.slice(0, 90).replace(/\n/g, ' | ')});
})()"""


def main():
    n = 0
    for t in list_targets(9222):
        if t.get("type") != "page" or "content/manage" not in (t.get("url") or ""):
            continue
        n += 1
        try:
            c = CDP(t["webSocketDebuggerUrl"])
            c.call("Runtime.enable")
            d = json.loads(c.eval(JS) or "{}")
            c.close()
        except Exception as e:  # noqa: BLE001
            print(f"[{n}] {t['id'][:8]} ERR {e}")
            continue
        print(f"[{n}] {t['id'][:8]} len={d.get('len')} posts={d.get('posts')} "
              f"ready={d.get('ready')} 删除作品按钮={d.get('delBtns')}")
        print(f"    头部: {d.get('head')}")
        for s in d.get("hitTitle") or []:
            print(f"    命中标题: {s}")
    print(f"共 {n} 个 content/manage 标签")


if __name__ == "__main__":
    main()
