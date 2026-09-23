#!/usr/bin/env bash
# 常驻保活：端口不通就重拉 Edge（沙箱会收割子进程，故用循环持有 Job）
export PATH="/usr/bin:/bin:/usr/local/bin:$PATH"
EDGE="C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"
PROFILE="C:/Users/suge0/WorkBuddy/automation-2026-09-13-16-27-29/_edge_profile"
URL="https://creator.douyin.com/creator-micro/content/post/article?default-tab=5"

while true; do
  if curl -s --noproxy '*' --max-time 3 http://127.0.0.1:9222/json/version >/dev/null 2>&1; then
    sleep 5
    continue
  fi
  echo "[keepalive] relaunching edge at $(date)"
  "$EDGE" --remote-debugging-port=9222 --user-data-dir="$PROFILE" \
    --no-first-run --no-default-browser-check --disable-extensions "$URL" >/dev/null 2>&1 &
  sleep 12
done
