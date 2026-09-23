#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""一眼看清「管理页作品数 / 编辑器里稿子还在不在」的状态探针。

2026-09-18 新增。用于「删除后发布失败」这类事故的定位：
发布脚本只看页面文本，点完发布页面会跳到文章阅读页 → 脚本判「结果不明」，
但真实情况可能是**根本没发出去**。唯一可靠判据是管理页的作品数 + 目标标题是否在场。

用法：
  python state_check.py                      # 打印管理页计数 + 编辑器概要
  python state_check.py --title 机器人能走下产线  # 额外检查该标题是否已发布
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cdp_read as R  # noqa: E402

JS_COUNT = r"""(()=>{
  const t = (document.body && document.body.innerText) || '';
  const m = t.match(/作品\s*[（(](\d+)[)）]/);
  const del = [].slice.call(document.querySelectorAll('*'))
    .filter(e => e.children.length === 0 && (e.innerText || '').trim() === '删除作品').length;
  return JSON.stringify({count: m ? +m[1] : null, dels: del});
})()"""

JS_EDITOR = r"""(()=>{
  const t = (document.body && document.body.innerText) || '';
  const btns = [].slice.call(document.querySelectorAll('button, [role=button]'))
    .filter(e => ['发布', '暂存离开'].includes((e.innerText || '').trim()))
    .map(e => {
      const r = e.getBoundingClientRect();
      return {t: (e.innerText || '').trim(), dis: !!e.disabled,
              box: [Math.round(r.left), Math.round(r.top)], w: Math.round(r.width)};
    });
  const mm = t.match(/配乐[\s\S]{0,60}/);
  const titleEl = document.querySelector('textarea, input[type=text]');
  return JSON.stringify({
    len: t.length,
    title: titleEl ? (titleEl.value || '').slice(0, 40) : null,
    music: mm ? mm[0].replace(/\n+/g, ' ').slice(0, 70) : null,
    btns: btns,
  });
})()"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=9222)
    ap.add_argument("--title", default="", help="检查该标题是否已出现在管理页")
    args = ap.parse_args()

    out = {}

    mgs = R.pages(args.port, "content/manage")
    if mgs:
        R.dedupe_tabs("content/manage", keep=1, port=args.port)
        mgs = R.pages(args.port, "content/manage")
        c = R.connect_retry(mgs[0]["webSocketDebuggerUrl"])
        try:
            R.reload_and_wait(c, R.JS_MANAGE_READY, timeout=40)
            raw = c.eval(JS_COUNT)
            out["manage"] = json.loads(raw) if raw and raw.startswith("{") else raw
            if args.title:
                t = c.eval("(document.body && document.body.innerText) || ''") or ""
                out["manage"]["hasTitle"] = args.title in t
        finally:
            c.close()
    else:
        out["manage"] = "NO_TAB"

    eds = R.pages(args.port, "content/post/article")
    if eds:
        c = R.connect_retry(eds[0]["webSocketDebuggerUrl"])
        try:
            raw = c.eval(JS_EDITOR)
            out["editor"] = json.loads(raw) if raw and raw.startswith("{") else raw
        finally:
            c.close()
    else:
        out["editor"] = "NO_TAB"

    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
