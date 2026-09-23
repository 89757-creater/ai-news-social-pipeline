import sys, os, time, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cdp_read import CDP, list_targets

CODE = "025027"

t = [x for x in list_targets(9222) if x.get("type") == "page" and "post/article" in (x.get("url") or "")][0]
c = CDP(t["webSocketDebuggerUrl"])
c.call("Page.enable")
c.call("Runtime.enable")
c.call("Page.bringToFront")


def click(x, y):
    for et in ("mouseMoved", "mousePressed", "mouseReleased"):
        p = {"type": et, "x": x, "y": y, "modifiers": 0}
        if et != "mouseMoved":
            p.update({"button": "left", "buttons": 1, "clickCount": 1})
        c.call("Input.dispatchMouseEvent", p)


def key(k, code, vk, mods=0):
    for kt in ("keyDown", "keyUp"):
        c.call("Input.dispatchKeyEvent", {"type": kt, "key": k, "code": code,
                                          "modifiers": mods,
                                          "windowsVirtualKeyCode": vk, "nativeVirtualKeyCode": vk})


FIND = ('(() => { const e=[].slice.call(document.querySelectorAll("input"))'
        '.filter(function(x){return (x.placeholder||"").indexOf("验证码")>=0;})[0];'
        ' if(!e) return JSON.stringify({err:"NF"});'
        ' const r=e.getBoundingClientRect();'
        ' return JSON.stringify({x:Math.round(r.x+r.width/2),y:Math.round(r.y+r.height/2)}); })()')

d = json.loads(c.eval(FIND))
print("输入框:", d)
if d.get("err"):
    c.close(); sys.exit(1)

click(d["x"], d["y"])
time.sleep(0.3)
key("a", "KeyA", 65, 2)          # Ctrl+A 全选
time.sleep(0.2)
key("Backspace", "Backspace", 8)  # 清空
time.sleep(0.3)
for ch in CODE:                   # 逐字符真实键盘输入
    c.call("Input.dispatchKeyEvent", {"type": "char", "text": ch})
    time.sleep(0.12)
time.sleep(0.5)

print("value:", c.eval('JSON.stringify([].slice.call(document.querySelectorAll("input"))'
                       '.filter(function(x){return (x.placeholder||"").indexOf("验证码")>=0;})'
                       '.map(function(x){return x.value;}))'))
c.close()
