#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""长图文发布台账 + 当日配额闸门。

**为什么必须有（2026-09-18 事故）**：
抖音对「长图文」（文章体裁）有 **每账号每日 10 次发布上限**，
超限时服务端返回 `status_code=536 / "今日发布10次长图文，已达上限"`。

危险之处在于「删除 + 重发」是换配乐/换封面的**唯一手段**（文章发布后没有编辑入口），
一旦先删了旧作、重发又被配额拒，就会出现「旧作已删、新作没发出去」的空窗
—— 2026-09-18 的 09-18 那篇就是这么丢的（作品数 5 → 4）。

所以：**删除之前必须先过这道闸门。**

⚠️ 诚实说明本台账的局限：
- 它只记录**本工具**成功发布的次数。手工发的、别的脚本发的，它看不到。
- 因此它是「下界」，不能证明 `10 - used` 还有余量。它能做的只有一件事：
  **当它自己都已经数到 10 时，坚决拦住删除**（这是确定性的）。
- 真正的兜底仍然是 `douyin_post_article.py` 的 rc=4（服务端拒绝）别当成功。

用法：
  python quota_ledger.py --mark 2026-09-18 --note "重发 09-14"   # 记一笔成功
  python quota_ledger.py --used                                  # 今天的已用次数
  python quota_ledger.py --seed 2026-09-18 3                     # 补记历史（事故复盘用）
"""
import argparse
import datetime as dt
import os
import sys

WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LEDGER = os.path.join(WS, "logs", "quota_ledger.txt")

# 抖音「长图文」每日发布上限（2026-09-18 实测，服务端 536 报文原文：
# "今日发布10次长图文，已达上限"）
DAILY_LIMIT = 10


def _lines():
    if not os.path.exists(LEDGER):
        return []
    with open(LEDGER, "r", encoding="utf-8") as f:
        return [ln.rstrip("\n") for ln in f if ln.strip()]


def mark(day=None, note=""):
    day = day or dt.date.today().isoformat()
    os.makedirs(os.path.dirname(LEDGER), exist_ok=True)
    stamp = dt.datetime.now().strftime("%H:%M:%S")
    with open(LEDGER, "a", encoding="utf-8") as f:
        f.write(f"{day}\t{stamp}\t{note}\n")
    return used(day)


def used(day=None):
    day = day or dt.date.today().isoformat()
    return sum(1 for ln in _lines() if ln.split("\t")[0] == day)


def remaining(day=None):
    return max(0, DAILY_LIMIT - used(day))


def gate(day=None, need=1):
    """返回 (是否放行, 说明)。删除前调用。"""
    day = day or dt.date.today().isoformat()
    u = used(day)
    if u + need > DAILY_LIMIT:
        return False, (f"当日长图文配额不足：台账已记 {u}/{DAILY_LIMIT}，本次还需 {need} 次"
                       f" → 拒绝（额度每日 00:00 重置，请次日补发）")
    return True, f"台账已记 {u}/{DAILY_LIMIT}，放行（注意台账只是下界，不保证有余量）"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mark", dest="mark_day", default=None, help="记一笔成功（默认今天）")
    ap.add_argument("--note", default="")
    ap.add_argument("--used", action="store_true", help="打印今天已用次数")
    ap.add_argument("--seed", nargs=2, metavar=("DAY", "N"), help="补记 N 笔历史")
    a = ap.parse_args()

    if a.seed:
        for _ in range(int(a.seed[1])):
            mark(a.seed[0], "seed")
        print(f"已补记 {a.seed[1]} 笔 → {a.seed[0]} 共 {used(a.seed[0])}")
        return 0
    if a.mark_day is not None or a.note:
        print(f"已记一笔 → 今天共 {mark(a.mark_day, a.note)}")
        return 0
    ok, why = gate()
    print(f"今日已用：{used()}/{DAILY_LIMIT}，剩余（下界）{remaining()}")
    print(("放行" if ok else "拦截") + "：" + why)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
