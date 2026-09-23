#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""抖音「点发布」为什么没生效？—— 网络 + DOM 双向取证探针。

背景（2026-09-18）：09-18 那篇删除后重发，`douyin_click.py` 成功命中 BUTTON「发布」
（`same:true`、坐标正确），但作品没出现在内容管理页，脚本只能报 rc=3「结果不明」。
可能的原因有三类，必须区分开：

  (a) 点击根本没进 React 的处理函数（事件被吃 / 目标不是真正的按钮）
  (b) 点击进去了，但前端校验拦住（弹 toast，且 toast 0.6s 就消失，事后读不到）
  (c) 点击进去了，接口也发了，但服务端拒绝（响应体里有原因）

本脚本同时铺三张网取证：
  1. **fetch/XHR 钩子** —— 记录点下去后真实发出的请求 URL + 状态 + 响应片段（判 (c)）
  2. **MutationObserver on toast** —— 把出现过的 toast 文案全部留下（判 (b)）
  3. **点击前后 innerText 变化** —— 判断页面是否发生了跳转/换块（判 (a)）

用法：
  python douyin_publish_probe.py                # 探针 + 真点「发布」
  python douyin_publish_probe.py --no-click     # 只装钩子，不点（用于对照）
"""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cdp_read as R  # noqa: E402

INSTALL_JS = r"""(()=>{
  if (window.__netlog) return 'ALREADY';
  window.__netlog = [];
  window.__toasts = [];
  const push = (o) => { window.__netlog.push(o); if (window.__netlog.length > 200) window.__netlog.shift(); };

  const of = window.fetch;
  window.fetch = function(...a){
    let url = ''; try { url = (typeof a[0] === 'string') ? a[0] : (a[0] && a[0].url) || ''; } catch(e){}
    const rec = { t: 'fetch', url: String(url).slice(0, 200), status: null, body: '' };
    push(rec);
    return of.apply(this, a).then(function(resp){
      rec.status = resp.status;
      try { resp.clone().text().then(function(txt){ rec.body = String(txt).slice(0, 400); }); } catch(e){}
      return resp;
    });
  };

  const oo = XMLHttpRequest.prototype.open;
  const os = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open = function(m, u){
    this.__u = String(u).slice(0, 200); this.__rec = { t: 'xhr', url: this.__u, status: null, body: '' };
    push(this.__rec);
    return oo.apply(this, arguments);
  };
  XMLHttpRequest.prototype.send = function(){
    const self = this;
    this.addEventListener('load', function(){
      try { self.__rec.status = self.status; self.__rec.body = String(self.responseText || '').slice(0, 400); } catch(e){}
    });
    return os.apply(this, arguments);
  };

  // toast 捕手：抖音 toast 生命周期极短（实测 0.6s），必须靠 MutationObserver 留痕
  const grab = () => {
    [].slice.call(document.querySelectorAll('[class*=toast], [class*=Toast], [class*=message-]'))
      .forEach(function(e){
        const s = (e.innerText || '').trim();
        if (s && window.__toasts.indexOf(s) < 0) window.__toasts.push(s);
      });
  };
  grab();
  if (!window.__mo) {
    window.__mo = new MutationObserver(function(){ grab(); });
    window.__mo.observe(document.body, { childList: true, subtree: true, characterData: true });
  }
  window.__clickEvents = window.__clickEvents || [];
  document.addEventListener('click', function(e){
    const p = e.target;
    window.__clickEvents.push({ txt: (p && (p.innerText || '')).trim().slice(0, 20),
      cls: String((p && p.className) || '').slice(0, 50), trusted: e.isTrusted });
    if (window.__clickEvents.length > 50) window.__clickEvents.shift();
  }, true);
  return 'INSTALLED';
})()"""

READ_JS = r"""(()=>JSON.stringify({
  net: (window.__netlog || []).slice(-40),
  toasts: (window.__toasts || []).slice(-12),
  clicks: (window.__clickEvents || []).slice(-6),
  href: location.href,
  textLen: ((document.body && document.body.innerText) || '').length,
}))()"""

LIST_PUB = r"""(()=>{
  const kw = '发布';
  const all = [].slice.call(document.querySelectorAll('*'))
    .filter(e => e.children.length === 0 && (e.innerText || '').trim() === kw)
    .filter(e => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; });
  // ⚠️ 2026-09-22 修正：编辑器很长，「发布」按钮常在视口之外
  //   （实测 y=1662 > 视口高）。此时 getBoundingClientRect() 给出的 y 是视口外坐标，
  //   dispatchMouseEvent 打过去等于点在页面外——**按钮既不报错也没反应**，
  //   取证结果里只有 net=[] toasts=[]，看起来像"服务端没回应"，实为压根没点到。
  //   修法：读坐标前先把目标滚到视口中央（behavior:'instant' 保证同步完成布局）。
  if (all[0]) {
    try { all[0].scrollIntoView({block: 'center', behavior: 'instant'}); }
    catch (e) { all[0].scrollIntoView({block: 'center'}); }
  }
  return JSON.stringify(all.map(function(e, i){
    const r = e.getBoundingClientRect();
    const cx = Math.round(r.x + r.width/2), cy = Math.round(r.y + r.height/2);
    const top = document.elementFromPoint(cx, cy);
    return { i: i, tag: e.tagName, cls: String(e.className).slice(0, 60),
             box: [Math.round(r.x), Math.round(r.y), Math.round(r.width), Math.round(r.height)],
             x: cx, y: cy,
             vpH: window.innerHeight,
             inView: cy >= 0 && cy <= window.innerHeight,
             topCls: String((top && top.className) || '').slice(0, 60),
             topTag: top && top.tagName,
             reach: !!(top && (top === e || top.contains(e) || e.contains(top))) };
  }));
})()"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=9222)
    ap.add_argument("--no-click", action="store_true")
    ap.add_argument("--wait", type=float, default=14.0)
    a = ap.parse_args()

    ps = R.pages(a.port, "content/post/article")
    if not ps:
        print("ERROR: 没有 post/article 标签页")
        return 1
    c = R.connect_retry(ps[0]["webSocketDebuggerUrl"])
    try:
        c.call("Page.enable")
        c.call("Page.bringToFront")
        print("解绑隐形浮层:", c.eval(R.NEUTRALIZE_JS))
        print("装钩子:", c.eval(INSTALL_JS))
        print("点击前的发布按钮候选:", c.eval(LIST_PUB))

        if a.no_click:
            print("（--no-click，等待 %.0fs 后读日志）" % a.wait)
            time.sleep(a.wait)
            print(c.eval(READ_JS))
            return 0

        d = json.loads(c.eval(LIST_PUB))
        if not d:
            print("ERROR: 找不到可见的「发布」按钮")
            return 1
        tgt = d[0]
        if not tgt.get("reach"):
            print("!! 按钮被遮挡（elementFromPoint 命中 %s）" % tgt.get("topCls"))
        print(f"点 ({tgt['x']},{tgt['y']})")
        for et in ("mouseMoved", "mousePressed", "mouseReleased"):
            p = {"type": et, "x": tgt["x"], "y": tgt["y"], "modifiers": 0}
            if et != "mouseMoved":
                p.update({"button": "left", "buttons": 1, "clickCount": 1})
            c.call("Input.dispatchMouseEvent", p)

        t0 = time.time()
        last_len = None
        while time.time() - t0 < a.wait:
            time.sleep(1.0)
            st = c.eval("JSON.stringify({href:location.href, len:((document.body&&document.body.innerText)||'').length})")
            print(f"  +{time.time()-t0:4.1f}s {st}")
            try:
                o = json.loads(st)
                if last_len is not None and o.get("len") != last_len:
                    print("     ^^ 文本长度变化")
                last_len = o.get("len")
            except Exception:  # noqa: BLE001
                pass

        raw = c.eval(READ_JS)
        print("\n===== 取证结果 =====")
        try:
            o = json.loads(raw)
            print("-- 网络请求（后 40 条）--")
            for r in o["net"]:
                print(f"   [{r['t']}] {r['status']} {r['url'][:150]}")
                if r.get("body"):
                    print(f"        body: {r['body'][:300]}")
            print("-- 捕获到的 toast --", o["toasts"])
            print("-- 页面上的 click 事件 --", json.dumps(o["clicks"], ensure_ascii=False))
            print("-- href:", o["href"], " textLen:", o["textLen"])
        except Exception:  # noqa: BLE001
            print(raw)
    finally:
        c.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
