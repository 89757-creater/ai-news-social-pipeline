#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""抖音文章 · 一键发稿（填稿 → 头图 → 封面 → 配乐 → 发布/暂存）

把 2026-09-15/16/17/18 四次手工跑出来的顺序固化下来，可一键重跑。

顺序（每一步都有成功判据，失败即停）：
  1. 打开文章编辑器（content/post/article）
  2. 填 标题 / 摘要 / 正文            → tools/douyin_fill.py --clear
  3. 上传文章头图 + 点「确定」        → tools/douyin_upload2.py + douyin_click.py
     判据：页面出现「图片上传成功」
  4. 上传封面 + 点「完成」           → 同上
     判据：页面出现「保存成功」
  5. 选配乐                          → tools/douyin_music.py（DOM 点击，见该脚本注释）
     判据：配乐区回读出现曲名
  6. 加话题（可选）                  → tools/douyin_topic.py + 点 "N/5"
  7. 发布 / 暂存                     → tools/douyin_click.py

⚠️ 发布是不可逆的公开动作。**默认只做 1–6 步，不点发布**；
   要真正发布必须显式加 --publish。遇到短信/扫码风控时按技能预案降级为「暂存离开」。

退出码（2026-09-18 新增 4，供上层编排区分「配额拒绝」与「结果不明」）：
  0 = 成功   1 = 某步失败   2 = 风控，已降级存草稿
  3 = 结果不明（没捕到接口、也无成功文案）
  4 = **服务端明确拒绝**（如 536「今日发布10次长图文，已达上限」）
      —— 这类拒绝页面上只闪一个 0.6s 的 toast，必须靠接口取证才看得到；
      上层脚本见到 4 应视为「旧作可能已删」，不要重试，等额度重置后补发。

用法：
  python douyin_post_article.py --date 2026-09-14                       # 只准备，不发布
  python douyin_post_article.py --date 2026-09-14 --publish             # 配乐按日期表自动选
  python douyin_post_article.py --date 2026-09-14 --music "太清" --publish  # 手动指定配乐
"""
import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

PY = r"C:/Users/suge0/.workbuddy/binaries/python/envs/default/Scripts/python.exe"
WS = Path(r"C:/Users/suge0/WorkBuddy/automation-2026-09-13-16-27-29")
TOOLS = WS / "tools"

sys.path.insert(0, str(TOOLS))
from cdp_read import CDP, list_targets, NEUTRALIZE_JS, new_tab  # noqa: E402
import quota_ledger  # noqa: E402

EDITOR_URL = "https://creator.douyin.com/creator-micro/content/post/article?default-tab=5"

# ── 上传入口文案：抖音 2026-09-18 改版，头图从「点击上传图片」改为「点击替换图片」 ──
HEAD_KWS = ["点击替换图片", "点击上传图片"]
COVER_KWS = ["点击上传封面图", "点击替换封面图"]

# ── 按篇配乐（2026-09-18 用户要求：每篇选中不同的「轻松忧郁」纯音乐） ──
# ⚠️ 2026-09-18 用户先后追加两条硬约束，本表已按此重排：
#    ① **不要选太清 TaiQing**；
#    ② **全部改成现代风格的纯音乐，不要古风歌**
#       → 剔除《葬花吟》（红楼梦古风）、柔情似水（国风命名）等。
#
# 为什么每条要带 `tab`：抖音配乐面板是「页签 + 首屏候选」的结构，
# `douyin_music.py --tab X --keyword Y` 只在 **X 页签的首屏**里找 Y。
# 实测扫全部 12 个页签（`tools/probe_music_tabs.py`）：
#   「纯音乐」页签共 18 首，但大半是蒋龙喜庆系列与古风曲，
#   **真正现代风格且可用的只有 3 首**：Batmirtt Zarell / Betkol NATEN / Meyjan。
#   不够 4 篇 → 必须允许从「飙升榜」这类页签取曲，所以曲目条目自带页签。
MUSIC_BY_DATE = {
    "2026-09-14": {"tab": "飙升榜", "name": "无人的旷野"},        # Matrix Tone｜空旷冷寂，配「没创造任何东西」的虚无
    "2026-09-16": {"tab": "纯音乐", "name": "Batmirtt Zarell"},    # jony｜现代氛围，配「装个依赖包却开了整栋楼的门」的失控
    "2026-09-17": {"tab": "纯音乐", "name": "Meyjan"},             # T3NZU｜电子凉感，配「机器人抖」的毫秒级循环
    "2026-09-18": {"tab": "纯音乐", "name": "Betkol NATEN"},       # jony｜低沉行进感，配「能走下产线但还赚不了钱」
    "2026-09-19": {"tab": "热门榜", "name": "轻音乐（释怀）"},        # 冷静克制，配「加密了但钥匙不在你手上」的取证复盘
    # ⚠️ 2026-09-20 首选「一个普通的下午」（probe 在飙升榜/热门榜都看到过）在脚本按页签
    #    匹配时**未命中** → 兜底池已全部用完，降级成 09-16 用过的 Batmirtt Zarell（重复）。
    #    已发布文章无编辑入口 → 未做删旧重发（不可逆风险 > 配乐重复的收益）。
    "2026-09-20": {"tab": "纯音乐", "name": "Batmirtt Zarell"},    # 降级兜底（与 09-16 重复，见上）
    # 2026-09-21：改用 `douyin_music_pick.py`（滚动加载后匹配）后，首屏之外的曲目也能选中，
    #            兜底池就此补上 3 首从未用过的现代风格纯音乐（jony / Faik 系列）。
    "2026-09-21": {"tab": "纯音乐", "name": "Midnight Drift"},     # jony｜冷感氛围（**当日实际发布所用**）
}
DEFAULT_MUSIC = {"search": "爵士", "name": "乌鸦的爵士咖啡馆"}

# ── 配乐风格新规（2026-09-21 用户指定，长期有效）────────────────────────────
# 用户原话：「不用纯音乐也可以，但风格要求 rnb，爵士，后朋克」
#   → ① 不再限定「纯音乐」页签；② 风格优先级 = **R&B / 爵士 / 后朋克**。
#
# 为什么必须走搜索框：配乐面板 12 个页签（推荐/热门榜/飙升榜/原创榜/卡点/纯音乐/旅行/
#   DJ/搞笑/流行/伤感…）**没有「爵士」「R&B」这类风格页签**。面板顶部有一个
#   `input[placeholder="搜索音乐"]`，只能靠它按风格词检索（`douyin_music_pick.py --search`）。
#
# 实测曲库存量（2026-09-21 搜索）：
#   · 爵士 —— 11 条，可用；例：乌鸦的爵士咖啡馆 / 春天的爵士樂 / 夜上海 / 午夜蓝调
#   · R&B  —— 31 条，可用；例：r&b loop（纯器乐循环）/ Nothin' On Me / 不得不爱
#   · 后朋克 —— **基本不可得**：「后朋克」只搜到 9 条，其中名字真带「后朋克」的仅 2 条，
#     且**均为 0 人使用**；其余全是「蒸汽朋克 / 赛博朋克」这类**视觉风格词**误命中。
#     → 这是曲库的客观存量问题，不是选曲手法问题。**缺口如实记录，不拿赛博朋克冒充。**
MUSIC_POOL = [
    {"search": "R&B", "name": "r&b loop"},              # BCD Studio｜纯器乐循环，时长稳、无歌词，最适合长文垫底
    {"search": "爵士", "name": "乌鸦的爵士咖啡馆"},        # 木子｜冷调爵士钢琴
    {"search": "爵士", "name": "春天的爵士樂"},            # 散步貓
    {"search": "爵士", "name": "夜上海"},                 # 上海老百乐门爵士
    {"search": "R&B", "name": "Nothin' On Me"},          # W phonker｜氛围 R&B
    {"search": "R&B", "name": "不得不爱"},                # CatchMoon｜R&B 版
    {"search": "爵士", "name": "爵士的梦"},                # 匿名情书
    # 兜底：以上都搜不到时，才退回纯音乐页签（用户已放宽限制，但风格优先级仍在前面）
    {"tab": "纯音乐", "name": "Midnight Drift"},
    {"tab": "纯音乐", "name": "Gundup Zamir"},
]

# 首选匹配不到时的兜底顺序（2026-09-21 起按风格优先级排）
# 用户新规：风格要求 R&B / 爵士 / 后朋克（后朋克在曲库中基本不可得，见上方说明），
#          不再限定「纯音乐」页签。条目带 `search` 走搜索框，带 `tab` 走页签。
MUSIC_POOL = [
    {"search": "R&B", "name": "r&b loop"},              # BCD Studio｜纯器乐循环，时长稳、无歌词，最适合长文垫底
    {"search": "爵士", "name": "乌鸦的爵士咖啡馆"},        # 木子｜冷调爵士钢琴
    {"search": "爵士", "name": "春天的爵士樂"},            # 散步貓
    {"search": "爵士", "name": "夜上海"},                 # 上海老百乐门爵士
    {"search": "R&B", "name": "Nothin' On Me"},          # W phonker｜氛围 R&B
    {"search": "R&B", "name": "不得不爱"},                # CatchMoon｜R&B 版
    {"search": "爵士", "name": "爵士的梦"},                # 匿名情书
    # 兜底：以上都搜不到时，才退回纯音乐页签（用户已放宽限制，但风格优先级仍在前面）
    {"tab": "纯音乐", "name": "Midnight Drift"},
    {"tab": "纯音乐", "name": "Gundup Zamir"},
]

# 点击「确定/完成」后，成功提示是**一闪而过的 toast**（实测 0.6s 内即消失），
# 因此必须在点击前挂 MutationObserver 把 toast 文本记下来，事后回读。
TOAST_HOOK = r"""(()=>{
  window.__toasts = window.__toasts || [];
  if (window.__toastOn) return 'EXIST';
  window.__toastOn = true;
  const KEYS = ['图片上传成功','保存成功','上传失败','图片格式','上传中','尺寸'];
  const scan = function(){
    const t = document.body.innerText || '';
    for (let i=0;i<KEYS.length;i++){
      if (t.indexOf(KEYS[i]) >= 0){
        const a = window.__toasts;
        if (a[a.length-1] !== KEYS[i]) a.push(KEYS[i]);
      }
    }
  };
  new MutationObserver(scan).observe(document.body, {subtree:true, childList:true, characterData:true});
  scan();
  return 'HOOKED';
})()"""

# ── 发布结果取证钩子（2026-09-18 新增，**必读**）────────────────────────────
# 为什么必须装：`create_v2` 的**失败完全不体现在页面上** —— 只弹一个
# 0.6s 就消失的 toast（"今日发布10次长图文，已达上限"），点完 6s 再读页面文本
# 什么都读不到 → 脚本只能报 rc=3「结果不明」。
#
# **2026-09-18 实打实吃过这个亏**：09-18 那篇删掉后重发，被判「结果不明」，
# 真实原因是服务端 536 拒绝（当日长图文配额 10 次已满）——
# 结果是旧作已删、新作没发出去，作品数从 5 掉到 4，白丢一篇。
# 装钩子后从**接口响应**取证，不再靠猜。
NET_HOOK_JS = r"""(()=>{
  if (window.__pubNet) return 'ALREADY';
  window.__pubNet = { pub: null, all: [] };
  const of = window.fetch;
  window.fetch = function(...a){
    let url = ''; try { url = (typeof a[0] === 'string') ? a[0] : (a[0] && a[0].url) || ''; } catch(e){}
    const rec = { url: String(url).slice(0, 160), status: null, body: '' };
    if (/create_v2|create\//.test(url)) { window.__pubNet.pub = rec; }
    window.__pubNet.all.push(rec);
    if (window.__pubNet.all.length > 80) window.__pubNet.all.shift();
    return of.apply(this, a).then(function(resp){
      rec.status = resp.status;
      try { resp.clone().text().then(function(t){ rec.body = String(t).slice(0, 500); }); } catch(e){}
      return resp;
    });
  };
  const oo = XMLHttpRequest.prototype.open, os = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open = function(m, u){
    this.__rec = { url: String(u).slice(0, 160), status: null, body: '' };
    if (/create_v2|create\//.test(String(u))) { window.__pubNet.pub = this.__rec; }
    window.__pubNet.all.push(this.__rec);
    return oo.apply(this, arguments);
  };
  XMLHttpRequest.prototype.send = function(){
    const self = this;
    this.addEventListener('load', function(){
      try { self.__rec.status = self.status; self.__rec.body = String(self.responseText || '').slice(0, 500); } catch(e){}
    });
    return os.apply(this, arguments);
  };
  return 'HOOKED';
})()"""

NET_READ_JS = r"""(()=>{
  const n = window.__pubNet || {};
  return JSON.stringify({ href: location.href, pub: n.pub || null,
                          tail: ((document.body && document.body.innerText) || '').slice(-300) });
})()"""

# 找弹窗主按钮：视口内可见、最靠下的「确定/完成」。
# 头图弹窗（图片编辑）主按钮 = 确定；封面弹窗（编辑封面）主按钮 = 完成。
JS_MODAL_BTN = r"""(()=>{
  const all = [].slice.call(document.querySelectorAll('*')).filter(function(e){return e.children.length===0;});
  const cands = [];
  all.forEach(function(e){
    const s = (e.innerText||'').trim();
    if (s !== '确定' && s !== '完成') return;
    const r = e.getBoundingClientRect();
    if (r.width <= 0 || r.height <= 0) return;
    if (r.bottom < 0 || r.top > window.innerHeight) return;
    if (r.x < 0 || r.x > window.innerWidth) return;
    cands.push({t:s, x:Math.round(r.x+r.width/2), y:Math.round(r.y+r.height/2),
                bottom:r.bottom, cls:String(e.className).slice(0,40)});
  });
  if (!cands.length) return JSON.stringify({ok:false, why:'NO_BTN'});
  cands.sort(function(a,b){return b.bottom - a.bottom;});
  return JSON.stringify({ok:true, x:cands[0].x, y:cands[0].y, t:cands[0].t, n:cands.length});
})()"""

JS_IMG_SRCS = "JSON.stringify([].slice.call(document.querySelectorAll('img')).map(function(i){return i.src;}))"

# 「抽屉是否真的开着」——只看**内容层**是否在视口内。
# 抽屉关闭后外层容器仍在（全屏 + pointer-events:auto），用容器尺寸判断会永远为"开着"。
JS_SHEET_OPEN = r"""(()=>{
  const W = window.innerWidth, H = window.innerHeight;
  let open = 0;
  [].slice.call(document.querySelectorAll('[class*=semi-sidesheet]')).forEach(function(el){
    const cs = getComputedStyle(el);
    if (parseFloat(cs.opacity || '1') === 0) return;
    const inner = el.querySelector('[class*=semi-sidesheet-inner]');
    const r = (inner || el).getBoundingClientRect();
    if (r.width > 1 && r.height > 1 && r.left < W - 2 && r.top < H - 2) open++;
  });
  return open;
})()"""


def run(*args, quiet=False, keep=None):
    """跑子进程。keep 为关键词列表时，只打印命中的行。"""
    cmd = [PY] + [str(a) for a in args]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    out = (r.stdout or "") + (r.stderr or "")
    if not quiet:
        if keep:
            for ln in out.splitlines():
                if any(k in ln for k in keep):
                    print("   " + ln.strip()[:200])
        else:
            print("   " + out.strip().replace("\n", "\n   ")[:1200])
    return r.returncode, out


def connect():
    pages = [t for t in list_targets(9222)
             if t.get("type") == "page" and "post/article" in (t.get("url") or "")]
    if not pages:
        # ⚠️ 抖音发布成功后会把编辑器标签跳去内容管理页，于是这里就找不到页面了。
        # 不补一个的话，下一次重发会直接以「编辑器页面未打开」失败（2026-09-18 实测）。
        print("   未找到编辑器标签页，新建一个：", EDITOR_URL)
        new_tab(EDITOR_URL, wait=9)
        pages = [t for t in list_targets(9222)
                 if t.get("type") == "page" and "post/article" in (t.get("url") or "")]
        if not pages:
            return None
    c = CDP(pages[0]["webSocketDebuggerUrl"])
    c.call("Runtime.enable")
    c.call("Page.enable")
    # ⚠️ 必须置前：页面不在前台时 Input.dispatchMouseEvent 会被静默丢弃
    #（2026-09-18 实测：少了这一句，弹窗上的「确定」怎么点都关不掉，且不报任何错）
    c.call("Page.bringToFront")
    # 让页面相信自己有焦点：后台标签会被浏览器节流，定时器/XHR 都可能被拖到很慢，
    # 表现为「图片上传迟迟不完成、弹窗 20 秒都不出现」
    try:
        c.call("Emulation.setFocusEmulationEnabled", {"enabled": True})
    except Exception:
        pass
    return c


def page_text(c):
    return c.eval("(()=>{const b=document.body; return b?b.innerText:'';})()") or ""


def step_fill(date):
    doc = WS / "social" / date / "douyin" / "抖音版文案.md"
    if not doc.exists():
        return False, f"找不到文案：{doc}"
    print(f"[2/7] 填稿 {doc.name}")
    rc, out = run(TOOLS / "douyin_fill.py", "--doc", doc, "--clear")
    ok = rc == 0 and "回读校验" in out
    return ok, out.strip().splitlines()[-1][:160] if out else ""


def shot(c, path):
    """失败时留证截图。"""
    try:
        import base64
        data = (c.call("Page.captureScreenshot", {"format": "png"}) or {}).get("result", {}).get("data")
        if data:
            with open(path, "wb") as f:
                f.write(base64.b64decode(data))
            print("   截图:", path)
    except Exception as e:
        print("   截图失败:", e)


def dispatch_click(c, x, y):
    for et in ("mouseMoved", "mousePressed", "mouseReleased"):
        p = {"type": et, "x": x, "y": y, "modifiers": 0}
        if et != "mouseMoved":
            p.update({"button": "left", "buttons": 1, "clickCount": 1})
        c.call("Input.dispatchMouseEvent", p)


def find_entry(c, kws):
    """在页面上找存在的上传入口文案（新版 → 旧版依次尝试）。"""
    for k in kws:
        hit = c.eval("(()=>{return [].slice.call(document.querySelectorAll('*'))"
                     ".some(function(e){return e.children.length===0 && (e.innerText||'').trim()===%s;});})()"
                     % json.dumps(k, ensure_ascii=False))
        if hit:
            return k
    return None


def wait_modal_click(c, timeout=25.0):
    """等弹窗主按钮（确定/完成）出现并真实点击。"""
    t0 = time.time()
    last = ""
    while time.time() - t0 < timeout:
        raw = c.eval(JS_MODAL_BTN)
        try:
            d = json.loads(raw or "{}")
        except Exception:
            d = {}
        if d.get("ok"):
            c.call("Page.bringToFront")
            try:
                c.eval(NEUTRALIZE_JS)   # 隐形抽屉会吃掉这次点击
            except Exception:
                pass
            dispatch_click(c, d["x"], d["y"])
            return True, "点击「%s」@ %d,%d（候选%d）" % (d["t"], d["x"], d["y"], d.get("n", 0))
        last = d.get("why", "?")
        time.sleep(0.4)
    return False, "等弹窗按钮超时（%s）" % last


# 弹窗主按钮的 DOM click 兜底：按文案找到按钮本体（不是里面的文字 span），
# 派发原生 click。抖音用 React 事件委托，`.click()` 冒泡到 root 即可触发。
JS_MODAL_DOM_CLICK = r"""(()=>{
  const all = [].slice.call(document.querySelectorAll('*')).filter(function(e){
    return e.children.length === 0 && ['确定','完成'].indexOf((e.innerText||'').trim()) >= 0;
  }).filter(function(e){
    const r = e.getBoundingClientRect();
    return r.width > 0 && r.height > 0 && r.bottom > 0 && r.top < window.innerHeight
           && r.x >= 0 && r.x < window.innerWidth;
  });
  if (!all.length) return 'NO_BTN';
  all.sort(function(a,b){ return b.getBoundingClientRect().bottom - a.getBoundingClientRect().bottom; });
  let el = all[0];
  for (let i = 0; i < 4 && el.parentElement; i++) {      // 上升到按钮本体
    const cls = String(el.className);
    if (cls.indexOf('semi-button') >= 0 && cls.indexOf('content') < 0) break;
    el = el.parentElement;
  }
  el.click();
  return 'DOM_CLICKED:' + String(el.className).slice(0, 40);
})()"""


def click_modal_until_closed(c, timeout=110.0, appear=70.0):
    """点弹窗主按钮并**确认弹窗真的关了**；关不掉就换手法重试。

    ⚠️ 2026-09-18 教训一：按钮已经渲染出来 ≠ 可以点了。
    图片编辑弹窗刚出现时，`Input.dispatchMouseEvent` 打在「确定」上会被静默吞掉
    （坐标正确、elementFromPoint 也对，就是不生效）；隔一两秒再点同样的坐标就成功了。
    所以不能「点一次 → 等它自己关」，必须点击与验证成对出现，并准备第二手法。

    ⚠️ 教训二：弹窗出现得**很看运气**。同一段代码，快的时候 3 秒内就出按钮，
    慢的时候 20 秒还没影（上传接口在服务器侧）。所以等待要放宽，并且期间打印
    页面图片数量，好区分「只是慢」与「上传挂了」。
    """
    t0 = time.time()
    d, tick, n0 = {}, 0, len(img_srcs(c))
    while time.time() - t0 < appear:          # 先等按钮出现
        try:
            d = json.loads(c.eval(JS_MODAL_BTN) or "{}")
        except Exception:
            d = {}
        if d.get("ok"):
            print("   弹窗按钮出现（等待 %.1fs）" % (time.time() - t0))
            break
        tick += 1
        if tick % 12 == 0:                    # 每 ~4.8s 报一次
            print("   等待弹窗按钮… %.0fs（%s｜页面图 %d 张，起始 %d）"
                  % (time.time() - t0, d.get("why", "?"), len(img_srcs(c)), n0))
        time.sleep(0.4)
    if not d.get("ok"):
        return True, "等待 %.0fs 未见弹窗按钮（无需点击）" % appear

    tries, last_msg = 0, ""
    while time.time() - t0 < timeout:
        if not d.get("ok"):
            if tries == 0:
                return True, "弹窗已自行关闭（无需点击）"
            return True, "%s（第 %d 次生效）" % (last_msg, tries)
        c.call("Page.bringToFront")
        try:
            c.eval(NEUTRALIZE_JS)
        except Exception:
            pass
        tries += 1
        if tries <= 2:
            dispatch_click(c, d["x"], d["y"])
            last_msg = "点击「%s」@ %d,%d" % (d["t"], d["x"], d["y"])
        else:
            r = c.eval(JS_MODAL_DOM_CLICK)
            last_msg = "DOM click 「%s」(第 %d 次)" % (d["t"], tries)
            if r == "NO_BTN":
                return False, "按钮消失了但弹窗仍在（异常状态）"
        time.sleep(1.3)
        try:
            d = json.loads(c.eval(JS_MODAL_BTN) or "{}")
        except Exception:
            d = {}
    return False, "点了 %d 次仍未关（%s）" % (tries, last_msg)


def img_srcs(c):
    try:
        return set(json.loads(c.eval(JS_IMG_SRCS) or "[]"))
    except Exception:
        return set()


def read_toasts(c):
    try:
        return json.loads(c.eval("JSON.stringify(window.__toasts||[])") or "[]")
    except Exception:
        return []


def wait_modal_closed(c, timeout=8.0):
    """弹窗是否已关闭：主按钮（确定/完成）从视口里消失即视为关闭。

    ⚠️ 2026-09-18 教训：只验「图片新增」不够——图片传上去了但弹窗没关，
    后续步骤会全部落在弹窗后面，一路错到发布。必须单独验这一步。
    """
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            d = json.loads(c.eval(JS_MODAL_BTN) or "{}")
        except Exception:
            d = {}
        if not d.get("ok"):
            return True
        time.sleep(0.4)
    return False


def clear_overlays(c):
    """起点清场：关掉残留弹窗**和右侧抽屉**；返回页面是否已经干净。

    ⚠️ 2026-09-18 教训一：只按「确定/完成」按钮判断是不够的——
    音乐选择面板（`.semi-sidesheet` 抽屉，标题「选择音乐」）没有这两个按钮，
    单靠旧判据会被认为"页面干净"，于是它一直盖着右侧，
    把「编辑封面」弹窗的「完成」挤到面板底下，点不到又报不出原因。

    ⚠️ 2026-09-18 教训二：抽屉**关掉之后**外层容器不会消失，而是变成一个铺满视口、
    `pointer-events:auto` 的**看不见的全屏遮罩**——鼠标事件全被它吃掉。
    所以判「抽屉是否还开着」必须看**内容层**（`-inner`）在不在视口里，
    并且收尾时统一调 `NEUTRALIZE_JS` 把残留容器解绑。
    """
    for i in range(4):
        dirty = False
        try:
            d = json.loads(c.eval(JS_MODAL_BTN) or "{}")
        except Exception:
            d = {}
        if d.get("ok"):
            dirty = True
        try:
            if int(c.eval(JS_SHEET_OPEN) or 0) > 0:
                dirty = True
        except Exception:
            pass
        if not dirty:
            try:
                c.eval(NEUTRALIZE_JS)
            except Exception:
                pass
            return True
        for et in ("keyDown", "keyUp"):
            c.call("Input.dispatchKeyEvent", {"type": et, "key": "Escape", "code": "Escape",
                                              "windowsVirtualKeyCode": 27, "nativeVirtualKeyCode": 27})
        print("   清场：Esc 关闭残留弹窗/抽屉（第 %d 次）" % (i + 1))
        time.sleep(1.0)
    try:
        c.eval(NEUTRALIZE_JS)
    except Exception:
        pass
    return False


def reset_editor(c):
    """把编辑器整页重置为空白态（残留弹窗关不掉时的兜底）。"""
    print("   → 重置编辑器页面")
    c.call("Page.navigate", {"url": EDITOR_URL})
    time.sleep(7)


def step_image(c, kind, img, entry_kws, which):
    """上传头图（which='head'）或封面（which='cover'）。"""
    print(f"[{kind}] 上传 {img.name}")
    if not img.exists():
        return False, f"图片不存在：{img}"

    if not clear_overlays(c):
        return False, "起点就有弹窗关不掉（建议重置编辑器）"

    kw = find_entry(c, entry_kws)
    if not kw:
        return False, f"找不到上传入口文案（候选 {entry_kws}）"
    print(f"   入口文案：「{kw}」")

    c.eval(TOAST_HOOK)
    c.eval("window.__toasts=[];")
    before = img_srcs(c)

    rc, out = run(TOOLS / "douyin_upload2.py", "--keyword", kw, "--file", img,
                  keep=("DOC_CHANGE", "Page.fileChooserOpened", "按引用注入", "定位:",
                        "DOM click", "已点击", "未触发", "ERROR"))
    if "DOC_CHANGE :: INPUT/file files=1" not in out:
        return False, "文件未注入（无 DOC_CHANGE files=1）"

    # 点弹窗主按钮，并确认弹窗真的关掉（关不掉就换手法重试，仍不行则中止——
    # 别让后续操作全部落在弹窗后面，一路错到发布）
    ok_click, msg = click_modal_until_closed(c)
    if not ok_click:
        return False, msg

    # 成功判据：图片集合新增（结构，持久） 或 toast 命中（瞬时，已由 observer 落账）
    t0, added, toasts = time.time(), set(), []
    while time.time() - t0 < 16:
        time.sleep(0.5)
        added = {s for s in (img_srcs(c) - before) if s and not s.startswith("data:")}
        toasts = read_toasts(c)
        if added or any("成功" in t for t in toasts):
            break

    hit_toast = [t for t in toasts if "成功" in t]
    ok = bool(added) or bool(hit_toast)
    detail = "%s｜新增图 %d 张｜toast=%s｜弹窗已关" % (msg, len(added), toasts)
    return ok, detail


def step_music(tab, kw, idx, search=None):
    print(f"[5/7] 配乐 {('搜索:' + search + ' / ') if search else (tab + ' / ')}{kw or idx}")
    if kw:
        # 2026-09-21：按曲名选曲改用 `douyin_music_pick.py` —— 它会先滚到底触发懒加载，
        # 把候选池从**首屏 18 条**扩到 **70+ 条**再匹配。
        # 原因：`douyin_music.py --keyword` 只在首屏的渲染 DOM 里找，
        # 而「纯音乐」页签真正可用的现代风格曲目大量落在首屏之后，
        # 会被误判成「这首不在这个页签里」，逼着人往下降级、结果反复用同一首。
        #
        # `--search`（2026-09-21 追加）：走面板顶部的搜索框按**风格词**检索
        # （「爵士」「R&B」这类风格在 12 个页签里都没有对应页签），
        # 检索结果里再按曲名匹配。见 douyin_music_pick.py 的 --search。
        args = [TOOLS / "douyin_music_pick.py"]
        if search:
            args += ["--search", search]
        else:
            args += ["--tab", tab]
        args += ["--keyword", kw]
    elif idx is not None:
        args = [TOOLS / "douyin_music.py", "--tab", tab, "--index", str(idx)]
    else:
        return False, "未指定曲目"
    rc, out = run(*args)
    return rc == 0 and "已选择:" in out, out.strip().replace("\n", " ")[-200:]


def count_topics(c):
    """读话题弹窗的计数（N/5）。"""
    s = c.eval("[].slice.call(document.querySelectorAll('[class*=topicButtonCount]'))"
               ".map(function(e){return e.innerText;}).join(',')") or ""
    m = re.search(r"(\d+)\s*/\s*5", s)
    return int(m.group(1)) if m else 0


# 话题弹窗**是否真的开着**：唯一可靠的判据是「话题输入框在视口内可见且能聚焦」。
# ⚠️ 2026-09-18 教训：`topicsModal` 容器的高度**开关时都是 0**（内容走 absolute 定位），
# 用它判空必然误判；正文区入口在未打开时也会显示「添加话题 / 选择想要添加的话题」，
# 按文本判同样会误判。
JS_TOPIC_MODAL = r"""(()=>{
  const W = window.innerWidth, H = window.innerHeight;
  const l = [].slice.call(document.querySelectorAll('input,textarea')).filter(function(e){
    const ph = (e.placeholder || '') + (e.getAttribute('data-placeholder') || '');
    if (ph.indexOf('话题') < 0) return false;
    const r = e.getBoundingClientRect();
    const cs = getComputedStyle(e);
    return r.width > 40 && r.height > 10 && r.left >= 0 && r.left < W
           && r.top >= 0 && r.top < H && cs.visibility !== 'hidden' && cs.display !== 'none';
  });
  return l.length > 0;
})()"""

# 开话题弹窗的兜底手法：直接对入口派发**完整指针事件序列**。
# Semi/React 组件常把逻辑挂在 pointerdown/mousedown 上，只派发 click 是无效的。
JS_OPEN_TOPIC_DOM = r"""(()=>{
  const el = document.querySelector('[class*=topicSelector]') || document.querySelector('[class*=topicContent]');
  if (!el) return 'NO_ENTRY';
  const r = el.getBoundingClientRect();
  const x = Math.round(r.left + r.width / 2), y = Math.round(r.top + r.height / 2);
  const fire = function(type, Ctor){
    try {
      el.dispatchEvent(new Ctor(type, {bubbles: true, cancelable: true, view: window,
        clientX: x, clientY: y, button: 0, buttons: 1, pointerId: 1, pointerType: 'mouse', isPrimary: true}));
    } catch (_) {}
  };
  fire('pointerdown', MouseEvent); fire('mousedown', MouseEvent);
  fire('pointerup', MouseEvent);   fire('mouseup', MouseEvent);
  fire('click', MouseEvent);
  return 'DOM_SEQ@' + x + ',' + y;
})()"""


def open_topic_modal(c, tries=4):
    """把话题弹窗打开（真实点击与 DOM 事件序列轮换，直到输入框真的出现）。"""
    for i in range(1, tries + 1):
        try:
            c.eval(NEUTRALIZE_JS)          # 每次点击前先解绑隐形遮挡
        except Exception:
            pass
        if c.eval(JS_TOPIC_MODAL):
            return True
        run(TOOLS / "douyin_click.py", "--text", "点击添加话题", quiet=True)
        time.sleep(1.5)
        if c.eval(JS_TOPIC_MODAL):
            return True
        r = c.eval(JS_OPEN_TOPIC_DOM)
        print(f"   开窗尝试 {i}：真实点击未开，DOM 事件序列 → {r}")
        time.sleep(1.5)
        if c.eval(JS_TOPIC_MODAL):
            print(f"   开窗尝试 {i}：DOM 事件序列生效")
            return True
    return False


def step_topics(c, topics):
    """逐词添加并**校验计数**——连续快发时前一个词可能还没落定，
    2026-09-18 实测 5 个词只进去 4 个（不多报错，只在最后计数暴露）。"""
    print(f"[6/7] 话题 ×{len(topics)}")
    try:
        c.eval(NEUTRALIZE_JS)
    except Exception:
        pass
    if not open_topic_modal(c):
        return False, "话题弹窗打不开（真实点击与 DOM 事件序列均无效）"

    n_got = count_topics(c)
    for t in topics:
        for attempt in range(1, 4):
            run(TOOLS / "douyin_topic.py", "--text", t, quiet=True)
            time.sleep(1.6)
            now = count_topics(c)
            if now > n_got:
                n_got = now
                print(f"   「{t}」→ {now}/5")
                break
            print(f"   「{t}」第 {attempt} 次未生效（仍 {now}/5），重试")
    ok = n_got >= len(topics)
    tag = f"{n_got}/5"
    run(TOOLS / "douyin_click.py", "--text", tag, quiet=True)
    time.sleep(2)
    return ok, f"最终计数={tag}（期望 {len(topics)}/5）"


def preflight_check(c, music_expect=None):
    """发布前的最后一道闸：确认封面与配乐真的生效了，别把残缺稿发出去。

    ⚠️ 2026-09-18 追加：配乐不但要「有」，还要是**这一篇该用的那首**。
    统一用一首时只验「修改音乐」存在即可；改成按篇分配后，必须验曲名一致，
    否则一旦选歌步骤静默失败（面板点到了别的行），发出去就是错的。
    """
    t = page_text(c)
    issues = []
    if "没有选择封面" in t:
        issues.append("封面未设置")
    i = t.find("选择配乐")
    if i >= 0:
        seg = t[i:i + 90]
        if "修改音乐" not in seg:
            issues.append("配乐未设置")
        elif music_expect and not music_matches(music_expect, seg):
            issues.append(f"配乐不是预期的「{music_expect}」（配乐区：{seg[:40]}）")
    return issues


def music_matches(expect, text):
    """曲名比对：抖音会把曲名截断/补全（如「柔情似水(纯音乐)」），故用前缀近似匹配。"""
    key = expect.split("(")[0].split("（")[0].strip()
    if len(key) >= 4 and key.isascii():
        key = key[:4]
    elif len(key) > 3:
        key = key[:3]
    return key.lower() in (text or "").lower()


def _as_track(v, default_tab="纯音乐"):
    """把配乐条目规范成 (tab, name, search)。

    三种写法都支持：
      · {"tab": "纯音乐", "name": "Midnight Drift"}         —— 在指定页签里找（会滚动）
      · {"search": "爵士", "name": "乌鸦的爵士咖啡馆"}        —— 先在搜索框搜风格词，再按曲名匹配
      · "曲名"                                             —— 旧写法，落到 default_tab
    `search` 是 2026-09-21 用户把配乐风格定为 R&B / 爵士 / 后朋克 之后加的：
    这三种风格在 12 个页签里都**没有对应页签**，只能走面板顶部的搜索框。
    """
    if isinstance(v, dict):
        return v.get("tab", default_tab), v.get("name", ""), v.get("search")
    return default_tab, str(v), None


def resolve_music(date, explicit=None, tab="纯音乐"):
    """决定本篇用哪首配乐：显式 --music 优先，否则按日期表，最后落到默认。

    返回 (页签, 曲名, 来源说明) —— 页签是必需的，
    因为候选池里的曲子可能分布在不同的页签下（见 MUSIC_BY_DATE 上方注释）。
    """
    if explicit:
        return tab, explicit, "命令行指定"
    if date in MUSIC_BY_DATE:
        t, n, _ = _as_track(MUSIC_BY_DATE[date], tab)
        return t, n, "按日期表"
    t, n, _ = _as_track(DEFAULT_MUSIC, tab)
    return t, n, "默认"


def step_music_retry(primary_tab, kw, exclude=(), search=None):
    """选配乐；关键词可能在曲库里搜不到，失败则按 MUSIC_POOL 顺次兜底。

    ⚠️ 抖音曲库是**动态**的（同一页签每次返回的推荐可能不同），
    所以按曲名匹配必须允许失败并降级，不能一次失败就整篇中止。
    ⚠️ 每个候选**带自己的页签（或搜索词）**：首选在「纯音乐」找不到时，
    兜底可能要切到「飙升榜」、或改走搜索框才搜得到，不能一直用 primary_tab。
    """
    tried = []
    order = [{"tab": primary_tab, "name": kw, "search": search}]
    for m in MUSIC_POOL:
        t, n, s = _as_track(m)
        if n and n != kw and n not in exclude:
            order.append({"tab": t, "name": n, "search": s})
    for cand in order:
        if not cand["name"]:
            continue
        ok, msg = step_music(cand["tab"], cand["name"], None, cand.get("search"))
        tried.append((cand["name"], ok))
        if ok:
            where = ("搜索:" + cand["search"]) if cand.get("search") else ("页签 " + cand["tab"])
            if cand["name"] != kw:
                print(f"   !! 「{kw}」未命中，降级为「{cand['name']}」（{where}）")
            return True, cand["name"], msg
        print(f"   !! 「{cand['name']}」未命中，试下一首")
    return False, None, "兜底全部失败：" + ", ".join(f"{c}={'OK' if o else 'NO'}" for c, o in tried)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True, help="如 2026-09-14")
    ap.add_argument("--tab", default="纯音乐", help="配乐分类页签")
    ap.add_argument("--music", default=None, help="配乐曲名关键词（默认按 MUSIC_BY_DATE 日期表分配）")
    ap.add_argument("--search", default=None, help="按风格词走搜索框选曲（如 爵士 / R&B），配合 --music 用")
    ap.add_argument("--music-index", type=int, default=None, help="配乐序号")
    ap.add_argument("--no-music", action="store_true", help="跳过配乐")
    ap.add_argument("--no-image", action="store_true", help="跳过头图/封面")
    ap.add_argument("--topics", nargs="*", default=[], help="话题词（≤5）")
    ap.add_argument("--publish", action="store_true", help="真正点「发布」（默认不点）")
    a = ap.parse_args()

    day = WS / "social" / a.date / "douyin"
    head, cover = day / "douyin_head.png", day / "douyin_cover.png"

    c = connect()
    if c is None:
        print("ERROR: 编辑器页面未打开。先打开：", EDITOR_URL)
        return 1
    try:
        print(f"[1/7] 编辑器就绪 (post/article)")
        if not clear_overlays(c):
            reset_editor(c)
        ok, msg = step_fill(a.date)
        print("   →", "OK" if ok else "FAIL", msg)
        if not ok:
            return 1

        if not a.no_image:
            for kind, img, kws, which in (("3/7 头图", head, HEAD_KWS, "head"),
                                          ("4/7 封面", cover, COVER_KWS, "cover")):
                ok, msg = step_image(c, kind, img, kws, which)
                print("   →", "OK" if ok else "FAIL", msg)
                if not ok:
                    shot(c, WS / f"_fail_{which}.png")
                    return 1

        music_expect = None
        if not a.no_music:
            mtab, mname, why = resolve_music(a.date, a.music, a.tab)
            msearch = a.search
            if msearch is None and a.date in MUSIC_BY_DATE:
                msearch = _as_track(MUSIC_BY_DATE[a.date], a.tab)[2]
            if a.music_index is not None:
                ok, msg = step_music(mtab, None, a.music_index, msearch)
                print("   →", "OK" if ok else "FAIL", msg)
                if not ok:
                    return 1
            else:
                print(f"[5/7] 配乐 {('搜索:' + msearch + ' / ') if msearch else (mtab + ' / ')}{mname}（{why}）")
                ok, chosen, msg = step_music_retry(mtab, mname, search=msearch)
                print("   →", "OK" if ok else "FAIL", msg)
                if not ok:
                    return 1
                music_expect = chosen
                print(f"   实际选用：{chosen}")

        if a.topics:
            ok, msg = step_topics(c, a.topics)
            print("   →", "OK" if ok else "FAIL", msg)
            if not ok:
                return 1

        if not a.publish:
            print("\n[7/7] 已停在发布前（未点「发布」）。加 --publish 才真正提交。")
            print("   配乐区:", c.eval("""(()=>{const t=document.body.innerText;const i=t.indexOf('选择配乐');
                 return i>=0?t.slice(i,i+60).replace(/\\n/g,' | '):'NO_BLOCK';})()"""))
            return 0

        issues = preflight_check(c, music_expect)
        if issues:
            print("\n[7/7] 发布前检查未通过：", "；".join(issues))
            shot(c, WS / "_preflight_fail.png")
            return 1
        print("\n[7/7] 发布前检查: 通过（封面/配乐均已生效）")

        print("点「发布」")
        c.eval(NET_HOOK_JS)            # 装接口取证钩子——必须在点击之前
        run(TOOLS / "douyin_click.py", "--text", "发布")

        # 轮询等 create_v2 的响应落地。不要用固定 sleep：接口常在点击后 1–8s 才回，
        # 读早了就是空 → 正是「结果不明」误判的直接原因。
        res, href, tail = None, "", ""
        for _ in range(22):
            time.sleep(0.8)
            try:
                o = json.loads(c.eval(NET_READ_JS))
            except Exception:  # noqa: BLE001
                continue
            href, tail = o.get("href") or "", o.get("tail") or ""
            if o.get("pub") and o["pub"].get("status"):
                res = o["pub"]
                if res.get("body"):    # body 是异步回填的，等它真有内容
                    break
        print("   发布接口：", (json.dumps(res, ensure_ascii=False)[:280]
                              if res else "未捕获到 create 请求（可能未发出）"))

        code, msg = None, ""
        if res and res.get("body"):
            try:
                b = json.loads(res["body"])
                code, msg = b.get("status_code"), b.get("status_msg") or ""
            except Exception:  # noqa: BLE001
                pass

        if code is not None:
            if code == 0:
                print("   → 发布成功（接口 status_code=0）")
                quota_ledger.mark(None, f"publish {a.date}")
                return 0
            if code == 536 or "上限" in msg:
                print(f"   → !! 服务端拒绝：{msg or '已达当日发布上限'}")
                print("      ⚠️ 旧作可能已删、新作未发出；稿子仍在编辑器里。"
                      "额度次日 00:00 重置后补发：")
                print("      republish_one.py --date <D> --title <T> --no-delete ...")
                return 4
            print(f"   → !! 服务端拒绝：status_code={code} {msg}")
            return 4

        # 没捕到接口 → 退回页面文本判据（原逻辑）
        if "发布成功" in tail or "content/manage" in href:
            print("   → 发布成功")
            quota_ledger.mark(None, f"publish {a.date}")
            return 0
        if "验证" in tail or "验证码" in tail:
            print("   → 触发风控验证，降级为存草稿")
            run(TOOLS / "douyin_click.py", "--text", "取消", quiet=True)
            time.sleep(1)
            run(TOOLS / "douyin_click.py", "--text", "暂存离开", quiet=True)
            print("   已存草稿，发布需用户在手机端过一次短信/扫码验证")
            return 2
        print("   → 结果不明，页面尾部：", tail[-200:])
        return 3
    finally:
        c.close()


if __name__ == "__main__":
    raise SystemExit(main())
