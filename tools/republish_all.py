#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""批量「删旧 + 重发」：按 PLAN 表把若干篇抖音文章重发一遍。

何时用：改了封面 / 配乐这类**只能在发布那一刻写入**的东西之后，
要把已发布的几篇统一刷成新版。抖音「文章」没有编辑入口，只能删旧重发。

纪律：
  · 每篇独立串行，**一篇失败不影响下一篇**（互不相干），但最后汇总退出码非 0；
  · 单篇仍然走 `republish_one.py`，它自带「数量守恒闸门」——
    没删掉就绝不再发，避免发出重复作品。

用法：
  python republish_all.py                # 按下面 PLAN 全跑
  python republish_all.py --only 2026-09-14
  python republish_all.py --dry          # 只打印计划
"""
import argparse
import io
import subprocess
import sys
import time
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

PY = r"C:/Users/suge0/.workbuddy/binaries/python/envs/default/Scripts/python.exe"
WS = Path(r"C:/Users/suge0/WorkBuddy/automation-2026-09-13-16-27-29")
TOOLS = WS / "tools"

# (日期, 旧作标题关键词, 话题)
PLAN = [
    ("2026-09-14", "AI 写了 7.5 万行代码", ["AI", "人工智能", "程序员", "AI编程", "科技"]),
    ("2026-09-16", "AI 装个依赖包", ["AI编程", "程序员", "AIAgent", "科技观察", "ClaudeCode"]),
    ("2026-09-17", "机器人抖，真不怪它笨", ["具身智能", "机器人", "人工智能", "VLA", "中国移动"]),
    ("2026-09-18", "机器人能走下产线", ["具身智能", "人形机器人", "机器人", "人工智能", "新能源汽车"]),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*", default=None, help="只跑指定日期")
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()

    plan = [p for p in PLAN if not a.only or p[0] in a.only]
    if not plan:
        print("没有匹配的篇目")
        return 1

    print(f"计划重发 {len(plan)} 篇：")
    for d, t, tp in plan:
        print(f"  {d}  {t}  话题={len(tp)}")
    if a.dry:
        return 0

    ok_days, bad_days = [], []
    for i, (d, title, topics) in enumerate(plan, 1):
        print(f"\n{'='*70}\n[{i}/{len(plan)}] {d}  {title}\n{'='*70}")
        log = WS / "logs" / f"repub_all_{d}.log"
        cmd = [PY, str(TOOLS / "republish_one.py"), "--date", d, "--title", title,
               "--topics"] + list(topics)
        t0 = time.time()
        with open(log, "w", encoding="utf-8") as f:
            r = subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT,
                               text=True, encoding="utf-8", errors="replace")
        dur = time.time() - t0
        tail = "\n".join(log.read_text(encoding="utf-8", errors="replace").splitlines()[-14:])
        print(tail)
        print(f"--- rc={r.returncode}  用时 {dur:.0f}s  日志 {log}")
        (ok_days if r.returncode == 0 else bad_days).append(d)

    print(f"\n{'='*70}")
    print(f"成功 {len(ok_days)} 篇：{ok_days}")
    if bad_days:
        print(f"失败 {len(bad_days)} 篇：{bad_days}（看对应 logs/repub_all_<date>.log）")
        return 1
    print("全部成功")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
