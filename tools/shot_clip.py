#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""区域截图（clip + 放大），用于看清小图标 / 局部 UI。

用法：
  python shot_clip.py --x 240 --y 338 --w 400 --h 42 --scale 3 --out toolbar.png
"""
import argparse
import base64
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cdp_read import CDP, list_targets  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=9222)
    ap.add_argument("--pick", default="post/article")
    ap.add_argument("--x", type=float, required=True)
    ap.add_argument("--y", type=float, required=True)
    ap.add_argument("--w", type=float, required=True)
    ap.add_argument("--h", type=float, required=True)
    ap.add_argument("--scale", type=float, default=3.0)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    targets = [x for x in list_targets(args.port) if x.get("type") == "page"]
    hit = [x for x in targets if args.pick in (x.get("url") or "")]
    if not hit:
        print("ERROR: 找不到标签页")
        return 1

    c = CDP(hit[0]["webSocketDebuggerUrl"])
    try:
        c.call("Page.enable")
        r = c.call("Page.captureScreenshot", {
            "format": "png",
            "clip": {"x": args.x, "y": args.y, "width": args.w, "height": args.h, "scale": args.scale},
        })
        data = r.get("result", {}).get("data")
        if not data:
            print("ERROR:", r)
            return 1
        with open(args.out, "wb") as f:
            f.write(base64.b64decode(data))
        print("已保存:", args.out, os.path.getsize(args.out), "bytes")
    finally:
        c.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
