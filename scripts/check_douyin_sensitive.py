# -*- coding: utf-8 -*-
"""抖音稿件敏感词检测（含阳性对照），避免"空跑返回通过"的假阴性。

用法：
  python check_douyin_sensitive.py <md路径> [--cut "## 留人点清单"] [--cjk-only]

行为：
  1. 从 md 中截取正文段（默认截到 `## 留人点清单` 之前，并剥掉 frontmatter/引用行）；
  2. 调 douyin-transcript-imitation 的 sensitive_check.scan 扫描；
  3. **阳性对照**：另用一段已知含雷词的测试文本喂同一 scan，
     若对照未命中则判定为脚本异常（不是"通过"）；
  4. 输出 CJK 字数（口播稿按中文字计）。
"""
import argparse
import io
import os
import re
import sys

sys.path.insert(0, os.path.expanduser(r"~/.workbuddy/skills/douyin-transcript-imitation/scripts"))
import sensitive_check  # noqa: E402

CONTROL = "这是最强的一款，第一轮就绝对领先，最后付费扫码关注我。"  # 预期命中多处


def extract(path, cut):
    s = io.open(path, encoding="utf-8").read()
    # 剥 frontmatter
    if s.startswith("---"):
        parts = s.split("---", 2)
        if len(parts) == 3:
            s = parts[2]
    if cut and cut in s:
        s = s.split(cut)[0]
    # 去掉 markdown 标记行与引用行
    lines = []
    for ln in s.splitlines():
        t = ln.strip()
        if t.startswith(">") or t.startswith("|") or t.startswith("#"):
            continue
        if t in ("---", "***"):
            continue
        lines.append(ln)
    return "\n".join(lines).strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--cut", default="## 留人点清单")
    ap.add_argument("--cjk-only", action="store_true")
    a = ap.parse_args()

    text = extract(a.path, a.cut)
    cjk = len(re.findall(r"[\u4e00-\u9fff]", text))

    # --- 阳性对照：必须命中，否则脚本本身不可信 ---
    ctrl_hits = sensitive_check.scan(CONTROL)
    print(f"[对照] 阳性样本命中 {len(ctrl_hits)} 处：{[h[1] for h in ctrl_hits]}")
    if not ctrl_hits:
        print("[FAIL] 阳性对照未命中 —— 检测器异常，本次结果不可信")
        return 2

    print(f"[正文] 抽取 {len(text)} 字符 / 中文 {cjk} 字（判据标记：{a.cut}）")
    if cjk == 0:
        print("[FAIL] 正文抽取为 0 字 —— 截断标记有误，结果不可信")
        return 2

    hits = sensitive_check.scan(text)
    if not hits:
        print("[PASS] 未命中敏感词（阳性对照正常，结果可信）")
        return 0

    print(f"[HIT] 命中 {len(hits)} 处：")
    for cat, w, ctx in hits:
        print(f"  - [{cat}] {w}  …{ctx}…")
    return 1


if __name__ == "__main__":
    sys.exit(main())
