#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""文章编辑器「发布前体检」：把发布所需的每个字段都读一遍，并截图。

为什么要独立一个探针：`douyin_post_article.py` 的 rc 判据只看「点击后页面文本」，
一旦点失败（不报错、不生效）就只剩「结果不明」。要定位到底是**哪个字段没就绪**
导致发布被拒，必须能一眼看到编辑器里的真实状态。

用法：
  python editor_probe.py            # 打印体检结果
  python editor_probe.py --shot x.png
"""
import argparse
import base64
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cdp_read as R  # noqa: E402

JS = r"""(()=>{
  const t = (document.body && document.body.innerText) || '';
  const q = (sel) => [].slice.call(document.querySelectorAll(sel));
  const leaf = (txt) => q('*').filter(e => e.children.length === 0
      && (e.innerText || '').trim() === txt).length;
  const inView = (e) => { const r = e.getBoundingClientRect();
      return r.width > 0 && r.height > 0 && r.top < window.innerHeight && r.bottom > 0; };

  // 头图/封面：编辑器里以 <img> 呈现（上传成功后 src 变成 blob:/http）
  const imgs = q('img').filter(e => !/avatar|icon|logo/i.test(String(e.className) + (e.src||'')))
      .map(e => ({ cls: String(e.className).slice(0, 40), src: (e.src||'').slice(0, 40),
                   w: Math.round(e.getBoundingClientRect().width) }));

  // 话题：编辑器里话题是形如 #xxx 的叶子节点；统计「添加话题」按钮附近的计数文本
  const topicChips = q('*').filter(e => e.children.length === 0
      && /^#.+/.test((e.innerText || '').trim())).map(e => (e.innerText || '').trim().slice(0, 20));

  const mm = t.match(/选择配乐[\s\S]{0,80}/);
  const inputs = q('textarea, input[type=text]').map(e => ({
      tag: e.tagName, val: (e.value || '').slice(0, 40),
      ph: (e.placeholder || '').slice(0, 20), w: Math.round(e.getBoundingClientRect().width) }));

  const pubBtns = q('button, [role=button]').filter(e => (e.innerText || '').trim() === '发布')
      .map(e => { const r = e.getBoundingClientRect();
        return { dis: !!e.disabled, box: [Math.round(r.left), Math.round(r.top)],
                 w: Math.round(r.width), h: Math.round(r.height), view: inView(e) }; });

  return JSON.stringify({
    href: location.href,
    textLen: t.length,
    inputs: inputs,
    imgs: imgs,
    topicChips: topicChips,
    music: mm ? mm[0].replace(/\n+/g, ' ').slice(0, 90) : null,
    hasSettings: /谁可以看/.test(t),
    pubBtns: pubBtns,
    toasts: [].slice.call(document.querySelectorAll('[class*=toast], [class*=Toast], [class*=message]'))
        .map(e => (e.innerText || '').trim()).filter(Boolean).slice(0, 5),
    tail: t.slice(-260).replace(/\n+/g, ' | '),
  });
})()"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=9222)
    ap.add_argument("--shot", default="")
    args = ap.parse_args()

    ps = R.pages(args.port, "content/post/article")
    if not ps:
        print("ERROR: 没有 post/article 标签页")
        return 1
    c = R.connect_retry(ps[0]["webSocketDebuggerUrl"])
    try:
        c.call("Page.enable")
        try:
            c.eval(R.NEUTRALIZE_JS)
        except Exception:  # noqa: BLE001
            pass
        raw = c.eval(JS)
        try:
            d = json.loads(raw)
        except Exception:  # noqa: BLE001
            print("解析失败：", raw)
            return 1
        print(json.dumps(d, ensure_ascii=False, indent=2))
        if args.shot:
            s = c.call("Page.captureScreenshot", {"format": "png"})
            data = s.get("result", {}).get("data")
            if data:
                open(args.shot, "wb").write(base64.b64decode(data))
                print("截图:", args.shot)
    finally:
        c.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
