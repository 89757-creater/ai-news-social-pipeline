"""用 React 受控 input 的正确注入方式填验证码，再用 trusted 鼠标事件点「验证」。

关键：React 16+ 有 value tracker。直接赋值或 insertText 都可能被忽略，
必须走 HTMLInputElement.prototype 上的原生 value setter + dispatch input 事件。
"""
import sys, os, time, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cdp_read import CDP, list_targets

CODE = sys.argv[1] if len(sys.argv) > 1 else "025027"

t = [x for x in list_targets(9222) if x.get("type") == "page" and "post/article" in (x.get("url") or "")][0]
c = CDP(t["webSocketDebuggerUrl"])
c.call("Page.enable")
c.call("Runtime.enable")
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
  const r = inp.getBoundingClientRect();
  return JSON.stringify({ ok: 1, domValue: inp.value,
    x: Math.round(r.x + r.width / 2), y: Math.round(r.y + r.height / 2) });
})()
""" % json.dumps(CODE)

res = json.loads(c.eval(SET_JS))
print("填入:", res)
if res.get("err"):
    c.close(); sys.exit(1)
time.sleep(0.6)


def click(x, y):
    for et in ("mouseMoved", "mousePressed", "mouseReleased"):
        p = {"type": et, "x": x, "y": y, "modifiers": 0}
        if et != "mouseMoved":
            p.update({"button": "left", "buttons": 1, "clickCount": 1})
        c.call("Input.dispatchMouseEvent", p)


BTN = ('(() => { const e=[].slice.call(document.querySelectorAll("div"))'
       '.filter(function(x){return String(x.className).indexOf("verify_sms-verify_button")>=0;})[0];'
       ' if(!e) return JSON.stringify({err:"BTN_NOT_FOUND"});'
       ' e.scrollIntoView({block:"center",behavior:"instant"});'
       ' const r=e.getBoundingClientRect();'
       ' return JSON.stringify({x:Math.round(r.x+r.width/2),y:Math.round(r.y+r.height/2),'
       ' cls:String(e.className).slice(0,60)}); })()')

b = json.loads(c.eval(BTN))
print("验证按钮:", b)
if b.get("err"):
    c.close(); sys.exit(1)
click(b["x"], b["y"])
print("已点击验证")
time.sleep(6)
print("尾部:", (c.eval("(document.body.innerText||'').slice(-240)") or "").replace("\n", " | "))
c.close()
