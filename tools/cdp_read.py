#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""通过 CDP 直连本机已启动的浏览器（Chrome/Edge），读页面 / 截图 / 执行 JS / 开新标签。

背景：agent-browser 在本机装不上 Chromium（googlechromelabs 被代理挡），且 connect 会卡死。
本脚本绕过它，直接用 websocket-client 说 CDP 协议。

前置：先用调试端口启动浏览器，且 user-data-dir 必须独立：
  msedge.exe --remote-debugging-port=9222 --user-data-dir=<独立目录> <url>

用法：
  python cdp_read.py --list                    列出全部标签页
  python cdp_read.py                           读当前活动页（文本 + 标题 + URL）
  python cdp_read.py --pick douyin             挑选 URL 含 douyin 的标签页
  python cdp_read.py --new https://x.com       新开标签页并导航到该地址
  python cdp_read.py --js "location.href"      在页面上执行 JS 并打印结果
  python cdp_read.py --shot out.png            截图保存
  python cdp_read.py --text-limit 3000         限制文本输出长度（默认 6000）
"""
import argparse
import base64
import json
import os
import sys
import time
import urllib.parse
import urllib.request

# 本地 CDP 端口不能被代理吞掉
for _k in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "all_proxy", "ALL_PROXY"):
    os.environ.pop(_k, None)

import websocket  # websocket-client

OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))

# ── 「隐形遮挡」解绑（2026-09-18 实测，必读）────────────────────────────────
# 抖音（Semi Design）的浮层**关闭后 DOM 不消失**，而是留下一个「看不见但能拦住鼠标」的壳：
#
#  (a) 右侧抽屉 `.semi-sidesheet`（如「选择音乐」）：关闭后外层容器仍是
#      `visibility:visible; opacity:1; pointer-events:auto` 且铺满整个视口
#      （实测 box=[0,0,1032,800]），只有内层 `.semi-sidesheet-inner` 被平移出右边。
#  (b) 弹窗 `.semi-modal-wrap`（如「添加话题」，`z-index:1000` 全屏）：关闭后
#      `.semi-modal-content` 变成 `opacity:0`，但它**下面的** `emptyText-*` 等后代
#      依旧 `pointer-events:auto`，`document.elementFromPoint()` 会稳定返回那个透明后代。
#
# 后果完全一致且极难排查：`Input.dispatchMouseEvent` 坐标正确、`elementFromPoint` 也对，
# 但事件被透明层吃掉 —— **不报错、不生效**。症状是「点了但计数不变 / 弹窗打不开」。
#
# 处理：把这些「内容已不可见」的浮层设成 `pointer-events:none`。
# 判据用**可见性**而不是尺寸，并且做成可逆（下次调用时可见的会恢复），
# 这样同一个函数在浮层打开/关闭两种状态下都安全。
NEUTRALIZE_JS = r"""(()=>{
  const W = window.innerWidth, H = window.innerHeight;
  let n = 0;
  const mark = function(el, off){
    if (off) {
      if (el.style.pointerEvents !== 'none') { el.style.pointerEvents = 'none'; el.setAttribute('data-neu','1'); n++; }
    } else if (el.getAttribute('data-neu') === '1') {
      el.style.pointerEvents = ''; el.removeAttribute('data-neu');
    }
  };
  const chainInvisible = function(el){
    let cur = el;
    while (cur && cur !== document.documentElement) {
      const cs = getComputedStyle(cur);
      if (parseFloat(cs.opacity || '1') === 0) return true;
      if (cs.visibility === 'hidden' || cs.display === 'none') return true;
      cur = cur.parentElement;
    }
    return false;
  };
  // (b) 弹窗：DOM 结构是 `semi-portal > [semi-modal-mask, semi-modal-wrap > semi-modal > semi-modal-content]`，
  //     mask 是 wrap 的**兄弟**，只解绑 wrap 子树会漏掉它。所以按 portal 整棵判定：
  //     portal 里有 wrap 但 content 不可见 → 整个 portal（mask + wrap + 所有后代）一并解绑。
  [].slice.call(document.querySelectorAll('[class*=semi-portal]')).forEach(function(p){
    const wrap = p.querySelector('[class*=semi-modal-wrap]');
    if (!wrap) return;                       // 不是弹窗 portal（可能是普通下拉），不动
    const content = wrap.querySelector('[class*=semi-modal-content]');
    const cs = content ? getComputedStyle(content) : null;
    // 打开/关闭动画途中 opacity 可能正好是 0，但那不是"已关闭"，别误判成 dead
    const animating = content ? /animate/.test(String(content.className)) : false;
    const dead = !animating && (!content || parseFloat(cs.opacity || '1') === 0
                 || cs.visibility === 'hidden' || cs.display === 'none');
    if (dead) {
      mark(p, true);
      // mask / emptyText 等后代常自带 pointer-events:auto，不继承父级，必须逐个解绑
      [].slice.call(p.querySelectorAll('*')).forEach(function(el){ mark(el, true); });
    } else {
      mark(p, false);
      [].slice.call(p.querySelectorAll('[data-neu]')).forEach(function(el){ mark(el, false); });
    }
  });
  // 兜底：wrap 内部任何「自身或祖先不可见」的后代，单独解绑
  [].slice.call(document.querySelectorAll('[class*=semi-modal-wrap] *')).forEach(function(el){
    if (chainInvisible(el)) mark(el, true);
  });
  // (a) 抽屉：内容滑出视口 → 解绑；另外把 opacity:0 的遮罩一并解绑
  [].slice.call(document.querySelectorAll('[class*=semi-sidesheet]')).forEach(function(el){
    const inner = el.querySelector('[class*=semi-sidesheet-inner]');
    // 滑入/滑出动画途中位置不可信，跳过，等下一次调用再判
    if (/animate|motion/.test(String(el.className))
        || (inner && /animate|motion/.test(String(inner.className)))) return;
    if (parseFloat(getComputedStyle(el).opacity || '1') === 0) { mark(el, true); return; }
    if (!inner) return;
    const r = inner.getBoundingClientRect();
    mark(el, r.left >= W - 2 || r.top >= H - 2 || r.width <= 1 || r.height <= 1);
  });
  return n;
})()"""



def list_targets(port):
    raw = OPENER.open(f"http://127.0.0.1:{port}/json/list", timeout=10).read().decode()
    return json.loads(raw)


def browser_ws(port=9222):
    """取浏览器级 WebSocket（用于 Target.createTarget 新建标签）。"""
    raw = OPENER.open(f"http://127.0.0.1:{port}/json/version", timeout=10).read().decode()
    return json.loads(raw)["webSocketDebuggerUrl"]


def new_tab(url, port=9222, wait=8.0):
    """新开一个标签页并导航到 url。

    为什么需要它：抖音**发布成功后编辑器标签会自动跳到内容管理页**
    （实测），于是「含 post/article 的标签」就消失了，
    下一次想重发时 connect() 会找不到页面而直接报错。所以必须能自愈。
    """
    import time as _t
    c = CDP(browser_ws(port))
    try:
        c.call("Target.createTarget", {"url": url})
    finally:
        c.close()
    _t.sleep(wait)
    return True


def new_tab_http(port, url):
    """备用的开新标签方式（HTTP PUT /json/new）。注意它**不等页面加载完**。"""
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/json/new?{urllib.parse.quote(url, safe='')}", method="PUT")
    raw = OPENER.open(req, timeout=15).read().decode()
    return json.loads(raw)


def pages(port=9222, url_sub=""):
    """列出所有页面标签（可按 URL 子串过滤）。"""
    return [t for t in list_targets(port)
            if t.get("type") == "page" and url_sub in (t.get("url") or "")]


def close_target(target_id, port=9222):
    """关闭一个标签页。"""
    c = CDP(browser_ws(port))
    try:
        c.call("Target.closeTarget", {"targetId": target_id})
    finally:
        c.close()


def dedupe_tabs(url_sub, keep=1, port=9222):
    """同一类页面残留多个标签时只保留 `keep` 个，其余关掉，返回关闭数。

    为什么必须有（2026-09-18 踩坑）：抖音**发布成功后编辑器标签会自动跳转到
    content/manage**，于是每发一次就多一个管理页标签。而 `pages[0]` /「第一个含
    content/manage 的标签」在多次调用之间**顺序并不保证稳定**，且旧标签仍停在
    **上一次加载的快照**上 —— 结果是删除脚本读到一个「没有目标作品的过期页面」，
    报 `NO_TITLE`，看起来像"标题匹配不上"，其实是读错了页面。

    ⚠️ 关完必须**等 `/json/list` 真的不再列出这些标签**再返回（2026-09-18 追加）：
    刚关掉的 target 在列表里还会残留一小会儿，紧接着 `page_ws()` 会挑中它 →
    连上去立刻 `WebSocketConnectionException: Connection to remote host was lost`，
    而且是在下一步的 `Runtime.enable` 上炸，报错位置离真实原因很远。
    """
    ps = pages(port, url_sub)
    victims = ps[:-keep] if keep else list(ps)
    if not victims:
        return 0
    ids = {t["id"] for t in victims}
    for t in victims:
        try:
            close_target(t["id"], port)
        except Exception:  # noqa: BLE001
            pass
    # 等这些 id 从列表里消失（最多 8s），避免后续选中一个正在关闭的标签
    t0 = time.time()
    while time.time() - t0 < 8.0:
        live = {t["id"] for t in pages(port, url_sub)}
        if not (ids & live):
            break
        time.sleep(0.4)
    return len(victims)


def connect_retry(ws_url, tries=3, delay=1.5):
    """带重试的 CDP 连接。用于「标签刚被关 / 页面正在忙」导致的连接即断。"""
    last = None
    for _ in range(tries):
        try:
            c = CDP(ws_url)
            c.call("Runtime.enable")
            return c
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(delay)
    raise last


def wait_until(c, js, timeout=25.0, interval=1.0):
    """轮询执行 js 直到返回**真值**，返回 (ok, 最后取值, 实际等待秒数)。

    为什么不用固定 sleep：慢加载时页面还是白屏，`sleep(8)` 会把空白页当成"已就绪"，
    后续所有定位都落空且不报错。轮询到「关键元素真的出现」才继续，才是可靠的判据。
    """
    import time as _t
    t0 = _t.time()
    last = None
    while True:
        try:
            last = c.eval(js)
        except Exception as e:  # noqa: BLE001
            last = f"[ERR] {e}"
        if last:
            return True, last, _t.time() - t0
        if _t.time() - t0 >= timeout:
            return False, last, _t.time() - t0
        _t.sleep(interval)


def reload_and_wait(c, js, timeout=30.0, interval=1.0):
    """强制重载当前页并等到 js 为真（用于「页面是过期的/没渲染出来」的场景）。"""
    try:
        c.call("Page.reload", {"ignoreCache": True})
    except Exception:  # noqa: BLE001
        pass
    return wait_until(c, js, timeout=timeout, interval=interval)


# 内容管理页「真的渲染好了」的判据：作品卡片上的「删除作品」按钮出现。
# 不要用 `作品 (N)` 文本判断 —— 骨架屏阶段这段文案可能已经存在但列表是空的。
JS_MANAGE_READY = r"""(()=>{
  return [].slice.call(document.querySelectorAll('*')).filter(function(e){
    return e.children.length === 0 && (e.innerText || '').trim() === '删除作品';
  }).length;
})()"""


class CDP:
    def __init__(self, ws_url):
        self.ws = websocket.create_connection(
            ws_url, timeout=90, http_proxy_host=None, http_proxy_port=None, suppress_origin=True)
        self.mid = 0
        self.events = []          # 收集事件消息，避免被 call() 丢掉

    def call(self, method, params=None):
        self.mid += 1
        self.ws.send(json.dumps({"id": self.mid, "method": method, "params": params or {}}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == self.mid:
                return msg
            if "method" in msg:
                self.events.append(msg)

    def wait_event(self, method, timeout=8):
        """等待某个 CDP 事件；先查已收集的，再继续 recv。"""
        for e in self.events:
            if e.get("method") == method:
                return e
        self.ws.settimeout(timeout)
        try:
            while True:
                msg = json.loads(self.ws.recv())
                if msg.get("method") == method:
                    return msg
                if "method" in msg:
                    self.events.append(msg)
        except Exception:
            return None
        finally:
            try:
                self.ws.settimeout(90)
            except Exception:
                pass

    def drain_events(self, method):
        return [e for e in self.events if e.get("method") == method]

    def eval(self, expr):
        r = self.call("Runtime.evaluate",
                      {"expression": expr, "returnByValue": True, "awaitPromise": True})
        res = r.get("result", {})
        if "exceptionDetails" in res:
            return f"[JS ERROR] {res['exceptionDetails'].get('text')}"
        return res.get("result", {}).get("value")

    def close(self):
        try:
            self.ws.close()
        except Exception:
            pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=9222)
    ap.add_argument("--list", action="store_true", help="列出全部标签页后退出")
    ap.add_argument("--pick", default="", help="挑选 URL 含该关键词的标签页")
    ap.add_argument("--new", default="", help="新开标签页并导航")
    ap.add_argument("--js", default="", help="执行 JS 表达式并打印结果")
    ap.add_argument("--shot", default="", help="截图保存路径")
    ap.add_argument("--text-limit", type=int, default=6000)
    ap.add_argument("--settle", type=float, default=3.0, help="导航后等待秒数")
    args = ap.parse_args()

    if args.list:
        for t in list_targets(args.port):
            if t.get("type") == "page":
                print(f"[{(t.get('id') or '')[:8]}] {t.get('title')!r}")
                print(f"         {t.get('url')}")
        return 0

    if args.new:
        t = new_tab(args.port, args.new)
    else:
        targets = [x for x in list_targets(args.port) if x.get("type") == "page"]
        if not targets:
            print("ERROR: 没有可用标签页")
            return 1
        if args.pick:
            hit = [x for x in targets if args.pick in (x.get("url") or "")]
            t = hit[0] if hit else targets[0]
        else:
            t = targets[-1]

    c = CDP(t["webSocketDebuggerUrl"])
    try:
        c.call("Page.enable")
        c.call("Runtime.enable")
        c.eval(f"new Promise(r=>setTimeout(r,{int(args.settle*1000)}))")

        info = c.eval("({url: location.href, title: document.title,"
                      " textLen: ((document.body && document.body.innerText) || '').length})")
        if not isinstance(info, dict):
            print(f"页面尚未就绪: {info}")
            return 1
        print(f"标题: {info.get('title')}")
        print(f"地址: {info.get('url')}")
        print(f"文本长度: {info.get('textLen')}")
        print("=" * 60)

        if args.js:
            print(c.eval(args.js))
        else:
            text = c.eval("(document.body && document.body.innerText) || ''") or ""
            print(text[:args.text_limit])

        if args.shot:
            shot = c.call("Page.captureScreenshot", {"format": "png"})
            data = shot.get("result", {}).get("data")
            if data:
                with open(args.shot, "wb") as f:
                    f.write(base64.b64decode(data))
                print(f"\n截图已保存: {args.shot}")
    finally:
        c.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
