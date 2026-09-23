"""开 Network 监听，点「验证」，看是否真的发出了请求 —— 用于区分
「点击没生效」与「请求被拒」。"""
import sys, os, time, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cdp_read import CDP, list_targets

CODE = sys.argv[1] if len(sys.argv) > 1 else "634732"

t = [x for x in list_targets(9222) if x.get("type") == "page" and "post/article" in (x.get("url") or "")][0]
c = CDP(t["webSocketDebuggerUrl"])
c.call("Page.enable")
c.call("Runtime.enable")
c.call("Network.enable")
c.call("Page.bringToFront")

SET_JS = r"""
(() => {
  const codes = %s;
  const inp = [].slice.call(document.querySelectorAll('input'))
    .filter(function (e) { return (e.placeholder || '').indexOf('验证码') >= 0; })[0];
  if (!inp) return JSON.stringify({ err: 'INPUT_NOT_FOUND' });
  inp.focus();
  const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
  setter.call(inp, '');
  inp.dispatchEvent(new Event('input', { bubbles: true }));
  setter.call(inp, codes);
  inp.dispatchEvent(new Event('input', { bubbles: true }));
  inp.dispatchEvent(new Event('change', { bubbles: true }));
  return JSON.stringify({ ok: 1, domValue: inp.value });
})()
""" % json.dumps(CODE)

print("填入:", c.eval(SET_JS))
time.sleep(0.6)

BTN = ('(() => { const e=[].slice.call(document.querySelectorAll("div"))'
       '.filter(function(x){return String(x.className).indexOf("verify_sms-verify_button")>=0;})[0];'
       ' if(!e) return JSON.stringify({err:"BTN_NOT_FOUND"});'
       ' const r=e.getBoundingClientRect();'
       ' return JSON.stringify({x:Math.round(r.x+r.width/2),y:Math.round(r.y+r.height/2)}); })()')

b = json.loads(c.eval(BTN))
print("按钮:", b)

# 清空已收集事件，再从此刻开始监听
c.events = []


def click(x, y):
    for et in ("mouseMoved", "mousePressed", "mouseReleased"):
        p = {"type": et, "x": x, "y": y, "modifiers": 0}
        if et != "mouseMoved":
            p.update({"button": "left", "buttons": 1, "clickCount": 1})
        c.call("Input.dispatchMouseEvent", p)


click(b["x"], b["y"])
print("已点击，开始收集请求...")

# 持续 recv 6 秒，把事件都收进 c.events
c.ws.settimeout(6)
try:
    deadline = time.time() + 6
    while time.time() < deadline:
        try:
            msg = json.loads(c.ws.recv())
        except Exception:
            break
        if "method" in msg:
            c.events.append(msg)
except Exception as e:
    print("recv 结束:", e)
finally:
    try:
        c.ws.settimeout(90)
    except Exception:
        pass

reqs = [e for e in c.events if e.get("method") == "Network.requestWillBeSent"]
hits = []
for r in reqs:
    p = r.get("params", {})
    url = p.get("request", {}).get("url", "")
    if any(k in url for k in ("verify", "sms", "code", "passport", "login", "publish", "article", "commit")):
        hits.append({"method": p.get("request", {}).get("method"), "url": url[:170],
                     "post": (p.get("request", {}).get("postData") or "")[:130]})
print("总请求数:", len(reqs), " 关注命中:", len(hits))
for h in hits[-12:]:
    print("  ->", h["method"], h["url"])
    if h["post"]:
        print("     body:", h["post"])

# 响应
resps = [e for e in c.events if e.get("method") == "Network.responseReceived"]
for r in resps[-12:]:
    p = r.get("params", {})
    url = p.get("response", {}).get("url", "")
    if any(k in url for k in ("verify", "sms", "code", "passport")):
        print("  <-", p.get("response", {}).get("status"), url[:150])

print("尾部:", (c.eval("(document.body.innerText||'').slice(-170)") or "").replace("\n", " | "))
c.close()
