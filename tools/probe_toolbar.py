import sys, time, json, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cdp_read import CDP, list_targets

t = [x for x in list_targets(9222) if x.get("type") == "page" and "post/article" in (x.get("url") or "")][0]
c = CDP(t["webSocketDebuggerUrl"])
c.call("Page.enable")
c.call("Runtime.enable")
ic = c.eval('JSON.stringify([].slice.call(document.querySelectorAll("svg")).filter(function(e){var b=e.getBoundingClientRect();return b.width>0&&b.width<44;}).map(function(e){var b=e.getBoundingClientRect();return {x:Math.round(b.x+b.width/2),y:Math.round(b.y+b.height/2)};}))')
icons = [i for i in json.loads(ic) if 330 < i["y"] < 390]
print("图标数:", len(icons))


def click(x, y):
    for et in ("mouseMoved", "mousePressed", "mouseReleased"):
        p = {"type": et, "x": x, "y": y, "modifiers": 0}
        if et != "mouseMoved":
            p.update({"button": "left", "buttons": 1, "clickCount": 1})
        c.call("Input.dispatchMouseEvent", p)


def esc():
    for kt in ("keyDown", "keyUp"):
        c.call("Input.dispatchKeyEvent", {"type": kt, "key": "Escape", "code": "Escape",
                                          "windowsVirtualKeyCode": 27, "nativeVirtualKeyCode": 27})


base = c.eval("(window.__probe||[]).length") or 0
hit = None
for idx, it in enumerate(icons):
    before = c.eval("document.body.innerText") or ""
    click(it["x"], it["y"])
    time.sleep(1.1)
    newp = json.loads(c.eval("JSON.stringify((window.__probe||[]).slice(" + str(base) + "))") or "[]")
    after = c.eval("document.body.innerText") or ""
    diff = ""
    if len(after) != len(before):
        diff = " 文本变化 " + str(len(after) - len(before))
    mark = ""
    if any("FILE_INPUT" in p for p in newp):
        mark = "  <<< 触发文件选择!"
        hit = it
    print("图标%d (%d,%d): probe=%s%s%s" % (idx, it["x"], it["y"], newp[-2:], diff, mark))
    if mark:
        break
    esc()
    time.sleep(0.4)

print("命中:", hit)
c.close()
