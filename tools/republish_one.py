#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""抖音文章「删旧 + 按当日配乐重发」一键编排。

背景：抖音「文章」体裁发布后**没有编辑入口**（只有 设置权限/作品置顶/删除作品），
所以「换配乐 / 换封面」只能删除后重发。本项目 2026-09-18 用户要求
「每篇不同配乐」时就是这么做的。

编排的四步：
  1. 刷新内容管理页 → 2. 按标题(+可选时间)精确删除旧作
  3. 打开文章编辑器 → 4. douyin_post_article.py 重发（配乐按 MUSIC_BY_DATE）

用法：
  python republish_one.py --date 2026-09-18 --title "机器人能走下产线" \
      --topics 具身智能 人形机器人 机器人 人工智能 新能源汽车
  # 同名多条时用 --time 指定：--time "19:10"
  # 只删不发：--no-post    只发不删：--no-delete
"""
import argparse
import re
import subprocess
import sys
import time
from pathlib import Path

PY = r"C:/Users/suge0/.workbuddy/binaries/python/envs/default/Scripts/python.exe"
WS = Path(r"C:/Users/suge0/WorkBuddy/automation-2026-09-13-16-27-29")
TOOLS = WS / "tools"
sys.path.insert(0, str(TOOLS))
from cdp_read import (CDP, JS_MANAGE_READY, connect_retry, dedupe_tabs,  # noqa: E402
                      new_tab, pages, wait_until)
import quota_ledger  # noqa: E402

EDITOR_URL = "https://creator.douyin.com/creator-micro/content/post/article?default-tab=5"
MANAGE_URL = "https://creator.douyin.com/creator-micro/content/manage?enter_from=publish"


def run(*args, keep=()):
    cmd = [PY] + [str(a) for a in args]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    out = (r.stdout or "") + (r.stderr or "")
    for ln in out.splitlines():
        if not keep or any(k in ln for k in keep):
            print("   " + ln.strip()[:220])
    return r.returncode, out


def page_ws(match):
    for t in pages(9222, match):
        return t["webSocketDebuggerUrl"]
    return None


def goto(match, url, wait=8, create=True, ready_js=None, ready_timeout=30.0):
    """导航到 url，并（可选）等到 ready_js 为真。返回 True/False。

    为什么不能只靠 `wait` 固定秒数：慢加载时页面还是白屏，sleep 结束就往下走，
    后续定位全部落空且**不报错**（表现为 NO_TITLE / 作品数 None）。
    """
    if not page_ws(match):
        if not create:
            print(f"ERROR: 找不到含 {match} 的标签页")
            return False
        # 抖音发布成功后会把这个标签跳去管理页，所以「编辑器标签」会消失——补一个
        print(f"   没有含 {match} 的标签页，新建一个")
        new_tab(url, wait=6)

    ws = page_ws(match)
    if not ws:
        print(f"ERROR: 新建标签后仍找不到含 {match} 的标签页")
        return False
    try:
        # ⚠️ 用 connect_retry：上一步若刚关过标签，`page_ws` 可能挑中一个正在关闭的 target，
        # 直接连会立刻断（报错落在 Runtime.enable 上，离真实原因很远）
        c = connect_retry(ws)
    except Exception as e:  # noqa: BLE001
        print(f"ERROR: 连接 {match} 标签失败：{e}")
        return False
    try:
        c.call("Page.enable")
        c.call("Page.bringToFront")
        c.call("Page.navigate", {"url": url})
        time.sleep(wait)
        if ready_js:
            ok, val, waited_t = wait_until(c, ready_js, timeout=ready_timeout)
            print(f"   就绪等待：{'OK' if ok else '超时'}（{waited_t:.1f}s，值={val}）")
            if not ok:
                return False
    finally:
        c.close()
    return True


def count_posts():
    """读作品数。先等列表渲染出来，避免读到空白页。"""
    ws = page_ws("content/manage")
    if not ws:
        return None
    c = connect_retry(ws)
    try:
        wait_until(c, JS_MANAGE_READY, timeout=20.0)
        t = c.eval("document.body.innerText") or ""
        m = re.search(r"作品 \((\d+)\)", t)
        return int(m.group(1)) if m else None
    finally:
        c.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    ap.add_argument("--title", required=True, help="要删除的旧作标题关键词")
    ap.add_argument("--time", default=None, help="发布时间片段（同名多条时必填）")
    ap.add_argument("--topics", nargs="*", default=[])
    ap.add_argument("--no-delete", action="store_true")
    ap.add_argument("--no-post", action="store_true")
    ap.add_argument("--force", action="store_true",
                    help="无视配额闸门强行删除（危险：可能删了发不出去）")
    a = ap.parse_args()

    # ── 配额闸门（2026-09-18 事故后新增）────────────────────────────────────
    # 文章发布后没有编辑入口 → 换配乐/封面只能「删旧 + 重发」。
    # 而抖音长图文每日上限 10 次，先删后发一旦被服务端 536 拒绝，
    # 就是「旧作已删、新作没发出去」。所以删除前先过这道闸门。
    if not a.no_delete and not a.force:
        ok, why = quota_ledger.gate()
        if not ok:
            print(f"!! 配额闸门拦截：{why}")
            print("   如确认还有余量（台账只记本工具的成功发布，是下界），"
                  "可加 --force 继续；否则请次日补发。")
            return 5
        print(f"   配额闸门：{why}")

    before = None
    if not a.no_delete:
        print("[1/4] 刷新内容管理页")
        # 每发一次就多一个管理页标签（发布成功后编辑器标签会跳去管理页），
        # 残留标签会让「第一个标签」指向过期快照 → 先收敛成一个
        killed = dedupe_tabs("content/manage", keep=1)
        if killed:
            print(f"   清理了 {killed} 个残留管理页标签")
        if not goto("content/manage", MANAGE_URL, wait=8,
                    ready_js=JS_MANAGE_READY, ready_timeout=30.0):
            print("   !! 内容管理页未就绪，中止")
            return 1
        before = count_posts()
        print(f"   当前作品数：{before}")
        if before is None:
            print("   !! 读不到作品数，判定页面不可信，中止")
            return 1

        print(f"[2/4] 删除「{a.title}」" + (f"（时间 {a.time}）" if a.time else ""))
        args = [TOOLS / "douyin_delete.py", "--title", a.title]
        if a.time:
            args += ["--time", a.time]
        rc, _ = run(*args, keep=("ERROR", "按时间", "删除确认", "标题:", "作品数", "就绪", "清理"))
        if rc != 0:
            print("   !! 删除未成功，中止（不继续重发，避免出现重复作品）")
            return 1

        # 删除是异步的，等列表刷新后再数一次，确认真的少了一条
        if not goto("content/manage", MANAGE_URL, wait=7,
                    ready_js=JS_MANAGE_READY, ready_timeout=30.0):
            return 1
        after = count_posts()
        print(f"   删除后作品数：{after}")
        if after is None:
            print("   !! 读不到删除后的作品数，无法确认删除生效，中止（避免发出重复作品）")
            return 1
        if after >= before:
            print("   !! 作品数没有减少，判定删除未生效，中止")
            return 1
    else:
        # 没删过：也要有基准数，才能用「数量守恒」终检（见下）
        if goto("content/manage", MANAGE_URL, wait=7,
                ready_js=JS_MANAGE_READY, ready_timeout=30.0):
            before = count_posts()
            print(f"   （未删旧作）当前作品数基准：{before}")

    if a.no_post:
        print("[跳过重发]")
        return 0

    print("[3/4] 打开文章编辑器")
    if not goto("post/article", EDITOR_URL, wait=9):
        return 1

    print("[4/4] 重发（配乐按日期表自动选）")
    args = [TOOLS / "douyin_post_article.py", "--date", a.date, "--publish"]
    if a.topics:
        args += ["--topics"] + list(a.topics)
    rc, out = run(*args)
    if rc == 0:
        print("   → 重发成功（台账已在 douyin_post_article.py 内记一笔）")
    elif rc == 2:
        print("   → 触发风控，已降级存草稿（需用户手机端验证）")
    elif rc == 4:
        print("   → !! 服务端拒绝（配额/风控）：旧作可能已删、新作未发出")
        print("      稿子仍在编辑器里；额度每日 00:00 重置后补发：")
        print(f"      republish_one.py --date {a.date} --title \"{a.title}\" --no-delete")
    else:
        print(f"   → 重发结果不明（rc={rc}），见上方日志")

    # ── 终检：数量守恒 ─────────────────────────────────────────────────────
    # 为什么不能信 rc：点「发布」后页面可能跳到「文章阅读/预览」页而不是内容管理页，
    # `douyin_post_article.py` 的文案判据会判成 undefined（rc=3）。
    # **2026-09-18 实测吃过亏**：09-18 那篇被判「结果不明」，实际是
    # 「旧作已删、新作没发出去」——作品数从 5 掉到 4，白丢一篇。
    # 唯一权威的判据是回内容管理页数一遍：
    #   · 删过旧作 → 期望 final == before
    #   · 没删旧作 → 期望 final == before + 1
    expect = None if before is None else (before if not a.no_delete else before + 1)
    if expect is not None:
        if goto("content/manage", MANAGE_URL, wait=7,
                ready_js=JS_MANAGE_READY, ready_timeout=30.0):
            final = count_posts()
            print(f"[终检] 作品数：{final}（期望 {expect}）")
            if final == expect:
                print("   → 数量守恒成立，确认重发已生效")
                return 0
            print(f"   !! 数量不符：期望 {expect} 实际 {final}"
                  f"{'（旧作已删、新作未发出，需补发：加 --no-delete）' if final < expect else '（可能重复发布，请人工核查）'}")
            # 明确的服务端拒绝优先按 4 上报，别被「结果不明(3)」盖掉真实原因
            return 4 if rc == 4 else 3
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
