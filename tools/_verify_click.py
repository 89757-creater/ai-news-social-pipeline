import sys, os, time, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cdp_read import CDP, list_targets

t = [x for x in list_targets(9222) if x.get("type") == "page" and "post/article" in (x.get("url") or "")][0]
c = CDP(t["webSocketDebuggerUrl"])
c.call("Page.enable")
c.call("Runtime.enable")
c.call("Page.bringToFront")

DIAG = r"""
(() => {
  const el = [].slice.call(document.querySelectorAll('div'))
    .filter(function (e) { return String(e.className).indexOf('verify_sms-verify_button') >= 0; })[0];
  if (!el) return JSON.stringify({ err: 'BUTTON_NOT_FOUND' });
  const out = { cls: String(el.className).slice(0, 90) };
  const fk = Object.keys(el).filter(function (k) { return k.indexOf('__reactFiber') === 0; })[0]
          || Object.keys(el).filter(function (k) { return k.indexOf('__reactProps') === 0; })[0];
  out.fiberKeys = Object.keys(el).filter(function (k) { return k.indexOf('__react') === 0; });
  if (fk && fk.indexOf('Props') > 0) {
    const p = el[fk] || {};
    out.propsKeys = Object.keys(p).slice(0, 20);
    out.hasOnClick = typeof p.onClick === 'function';
    out.disabled = !!p.disabled;
  } else if (fk) {
    let n = el[fk], chain = [];
    for (let i = 0; i < 6 && n; i++) {
      const p = n.memoizedProps || {};
      chain.push({ d: i, keys: Object.keys(p).slice(0, 12) });
      if (typeof p.onClick === 'function') { out.onClickDepth = i; break; }
      n = n.return;
    }
    out.chain = chain;
  }
  // 找可能的错误提示
  const toasts = [].slice.call(document.querySelectorAll('[class*=toast],[class*=Toast],[class*=message],[class*=Message],[class*=error],[class*=Error]'))
    .map(function (e) { return (e.innerText || '').trim(); })
    .filter(function (s) { return s && s.length < 80; });
  out.toasts = toasts.slice(0, 6);
  return JSON.stringify(out, null, 1);
})()
"""

print("--- 诊断 ---")
print(c.eval(DIAG))

CLICK_IT = r"""
(() => {
  const el = [].slice.call(document.querySelectorAll('div'))
    .filter(function (e) { return String(e.className).indexOf('verify_sms-verify_button') >= 0; })[0];
  if (!el) return 'NF';
  // 方式 A：fiber 上的 onClick
  const fk = Object.keys(el).filter(function (k) { return k.indexOf('__reactFiber') === 0; })[0];
  if (fk) {
    let n = el[fk];
    for (let i = 0; i < 6 && n; i++) {
      const p = n.memoizedProps || {};
      if (typeof p.onClick === 'function') {
        try { p.onClick({ preventDefault: function () {}, stopPropagation: function () {} }); return 'FIBER_ONCLICK_OK(d=' + i + ')'; }
        catch (e) { return 'FIBER_ONCLICK_ERR: ' + e.message; }
      }
      n = n.return;
    }
  }
  // 方式 B：页面内派发完整指针序列
  const r = el.getBoundingClientRect();
  const base = { bubbles: true, cancelable: true, composed: true,
                 clientX: Math.round(r.x + r.width / 2), clientY: Math.round(r.y + r.height / 2) };
  el.dispatchEvent(new PointerEvent('pointerdown', Object.assign({}, base, { button: 0, buttons: 1 })));
  el.dispatchEvent(new MouseEvent('mousedown', Object.assign({}, base, { button: 0, buttons: 1 })));
  el.dispatchEvent(new PointerEvent('pointerup', Object.assign({}, base, { button: 0, buttons: 0 })));
  el.dispatchEvent(new MouseEvent('mouseup', Object.assign({}, base, { button: 0, buttons: 0 })));
  el.dispatchEvent(new MouseEvent('click', Object.assign({}, base, { button: 0, buttons: 0 })));
  return 'DISPATCHED';
})()
"""

print("--- 触发 ---")
print(c.eval(CLICK_IT))
time.sleep(5)
print("--- 尾部 ---")
print((c.eval("(document.body.innerText||'').slice(-260)") or "").replace("\n", " | "))
c.close()
