#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""草稿箱对齐检查：把「本地 social/*/ 的公众号稿」与「公众号草稿箱现状」摆在一起。

用法：
  python draft_status.py                 # 默认：列草稿箱 + 列出草稿箱里没有的本地稿件
  python draft_status.py --all           # 额外列出草稿箱里已有对应稿件的日期
  python draft_status.py --root <工作区>  # 指定工作区根目录（默认取本脚本上两级）

⚠️ 判读须知：**草稿箱是工作台，不是档案柜**。
   稿件一旦被用于发布（或被人手工删除），就会离开草稿箱。
   所以出现在「草稿箱里没有」清单里的稿件，**不一定是遗漏** —— 也可能是已发布过。
   本脚本只做差集比对，不对「该不该补推」下结论。

依赖：同目录的 publish_wenyan.py（复用其凭证加载与 API 封装）。
"""
import argparse
import datetime
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import publish_wenyan as pw  # noqa: E402


def guess_root(start: Path) -> Path:
    """向上查找含 social/ 的目录作为工作区根（脚本在 scripts/ 下，别写死层级）。"""
    for p in [start, *start.parents]:
        if (p / "social").is_dir():
            return p
    return start.parents[3]


def local_articles(root: Path) -> list:
    """扫描 social/YYYY-MM-DD/02_*.md，取 frontmatter 标题。"""
    out = []
    for day in sorted(root.glob("social/20??-??-??")):
        if not day.is_dir():
            continue
        for f in sorted(day.glob("02_*.md")):
            meta = pw.parse_frontmatter(f)
            title = (meta.get("title") or f.stem).strip()
            out.append({"date": day.name, "title": title, "file": f})
    return out


def cloud_drafts() -> list:
    """翻页取草稿箱全部条目（draft/batchget 单次上限 20）。"""
    pw.load_dotenv()
    appid = os.environ.get("WECHAT_APP_ID", "").strip()
    secret = os.environ.get("WECHAT_APP_SECRET", "").strip()
    if not (appid and secret):
        raise SystemExit(
            "ERROR: 凭证缺失，读不到草稿箱。\n"
            "  先跑：python publish_wenyan.py --check-credentials"
        )
    token = pw.get_access_token(appid, secret)
    url = f"{pw.API_BASE}/draft/batchget?access_token={token}"

    out, offset, total = [], 0, None
    while True:
        payload = pw._post_json(url, {"offset": offset, "count": 20, "no_content": 1})
        items = payload.get("item", []) or []
        if total is None:
            total = payload.get("total_count", len(items))
        for it in items:
            for a in (it.get("content", {}) or {}).get("news_item", [{}]):
                out.append({
                    "title": (a.get("title") or "").strip(),
                    "media_id": it.get("media_id", ""),
                    "update_time": a.get("update_time") or it.get("update_time"),
                })
        offset += len(items)
        if not items or offset >= (total or 0):
            break
    return out


def norm(s: str) -> str:
    return "".join(s.split())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, default=None,
                    help="工作区根目录（含 social/）；默认自动向上查找")
    ap.add_argument("--days", type=int, default=7,
                    help="只关注最近 N 天的本地稿件；0 = 不限（默认 7）")
    ap.add_argument("--all", action="store_true", help="同时列出已对齐的日期")
    args = ap.parse_args()

    root = (args.root or guess_root(Path(__file__).resolve())).resolve()
    local = local_articles(root)
    if args.days > 0:
        cutoff = (datetime.date.today() - datetime.timedelta(days=args.days)).isoformat()
        local = [a for a in local if a["date"] >= cutoff]
    cloud = cloud_drafts()

    print(f"工作区: {root}")
    print(f"本地稿件: {len(local)} 篇（近 {args.days or '全部'} 天） | 草稿箱: {len(cloud)} 条\n")

    print(f"── 草稿箱现有 {len(cloud)} 条 ──")
    for c in sorted(cloud, key=lambda x: x.get("update_time") or 0, reverse=True):
        ts = c.get("update_time")
        when = datetime.datetime.fromtimestamp(ts).strftime("%m-%d %H:%M") if ts else "?"
        print(f"  [{when}] {c['title'] or '(无标题)'}")
        print(f"           {c['media_id']}")
    if not cloud:
        print("  （空）")

    cloud_titles = {norm(c["title"]) for c in cloud}
    missing = [a for a in local if norm(a["title"]) not in cloud_titles]
    aligned = [a for a in local if norm(a["title"]) in cloud_titles]

    print(f"\n── 草稿箱里没有的本地稿件（{len(missing)} 篇）──")
    if missing:
        for a in missing:
            print(f"  {a['date']}  {a['title']}")
        print("\n  ⚠️ 不一定是遗漏：已发布的稿件会自动离开草稿箱。"
              "仅当某篇确实没推过、也没发布过时，才需要补推。")
    else:
        print("  （无 —— 本地稿件在草稿箱里都有对应条目）")

    if args.all:
        print(f"\n── 草稿箱里已有对应条目的日期（{len(aligned)} 篇）──")
        for a in aligned or []:
            print(f"  {a['date']}  {a['title']}")


if __name__ == "__main__":
    main()
