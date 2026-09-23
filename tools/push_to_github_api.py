#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""通过 GitHub REST API 推送 skill 仓库（绕开被阻断的 github.com 传输通道）。

【为什么需要这个脚本】
本机网络环境实测（2026-09-23）：
    https://api.github.com   -> 200  ✅ 可达
    https://github.com       -> 000  ❌ 代理 CONNECT 隧道被拒（response 502）
所以 `git push`（走 github.com）不可用，但 **Contents API 可用**。
本脚本改用 API 逐文件上传，实现同等效果。

【用法】
    # 1) 先准备 token（二选一）
    #    · 细粒度 PAT：https://github.com/settings/personal-access-tokens/new
    #      权限勾 "Contents: Read and write"，Repository access 选目标仓库
    #    · 经典 PAT：勾 "repo" 范围
    #    ★ 只给本次推送用，用完可撤销；不要写进任何文件

    set GITHUB_TOKEN=github_pat_xxxxxxxx        # Windows CMD
    export GITHUB_TOKEN=github_pat_xxxxxxxx     # Git Bash
    # 或 python push_to_github_api.py --token <...>

    # 2) 首次：创建仓库并推送
    python push_to_github_api.py --repo ai-news-social-pipeline --create

    # 3) 之后：仓库已存在，直接推（会更新变化的文件）
    python push_to_github_api.py --repo ai-news-social-pipeline

【说明】
  · 文件清单取自 `git ls-files`，因此自动尊重 .gitignore（.env 不会被推上去）。
  · 更新已存在的文件需要先取 sha，脚本已自动处理。
  · 逐文件上传，83 个文件约 1-2 分钟；中途失败可重跑（幂等）。
"""
import argparse
import base64
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import quote

API = "https://api.github.com"
DEFAULT_GIT = r"C:/Users/suge0/.workbuddy/binaries/PortableGit/versions/1.2.0/cmd/git.exe"
DEFAULT_ROOT = Path(r"C:/Users/suge0/.workbuddy/skills/ai-news-social-pipeline")


def api(method, path, token, body=None):
    """调 GitHub API，返回 (status, 解析后的 json 或 None)。"""
    url = path if path.startswith("http") else API + path
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    req.add_header("User-Agent", "ai-news-social-pipeline-push")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read().decode("utf-8")
            return r.status, (json.loads(raw) if raw.strip() else None)
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, {"raw": raw[:300]}
    except Exception as e:
        return 0, {"error": repr(e)}


def git_files(git_exe, root):
    """列出仓库内被 git 跟踪的文件（相对路径，正斜杠）。"""
    # core.quotepath=false 让中文路径不被转义成 \xxx
    out = subprocess.run([git_exe, "-c", "core.quotepath=false", "ls-files"],
                         cwd=str(root), capture_output=True, text=True, encoding="utf-8")
    if out.returncode != 0:
        print("✗ 读取 git 文件清单失败：" + (out.stderr or "").strip())
        sys.exit(1)
    files = [ln.strip() for ln in out.stdout.splitlines() if ln.strip()]
    return [f.replace("\\", "/") for f in files]


def push_via_git_api(owner, repo, root, files, token, branch, message, orphan=False):
    """用 Git Data API 一次性提交：blobs -> tree -> commit -> 更新 ref。

    **为什么不用 contents 模式**：Contents API 每个文件一次 PUT，
    每个 PUT 产生一个 commit —— 83 个文件就是 83 个碎 commit，仓库历史没法看。
    本模式只留 1 个 commit，内容是本地 `git ls-files` 的完整快照。
    """
    # 1. 取分支当前 commit（空仓库时不存在）
    st, ref = api("GET", f"/repos/{owner}/{repo}/git/ref/heads/{branch}", token)
    parent_sha = ref["object"]["sha"] if st == 200 and isinstance(ref, dict) else None
    print(f"  当前 {branch} 顶端：{parent_sha[:10]}" if parent_sha
          else f"  {branch} 尚不存在（空仓库）→ 将创建初始提交")

    # 2. 逐文件建 blob
    entries, skipped = [], []
    for i, rel in enumerate(files, 1):
        p = root / rel
        if not p.is_file():
            skipped.append(rel)
            continue
        content = base64.b64encode(p.read_bytes()).decode("ascii")
        st, blob = api("POST", f"/repos/{owner}/{repo}/git/blobs", token,
                       {"content": content, "encoding": "base64"})
        if st not in (200, 201):
            print(f"  ✗ blob 失败 {rel} — HTTP {st}: {(blob or {}).get('message')}")
            return 1
        entries.append({
            "path": rel,
            "mode": "100755" if rel.endswith(".sh") else "100644",
            "type": "blob",
            "sha": blob["sha"],
        })
        if i % 20 == 0 or i == len(files):
            print(f"  已建 blob {i}/{len(files)}")

    # 3. 建 tree（不传 base_tree → 完全替换，与本地清单严格一致）
    st, tree = api("POST", f"/repos/{owner}/{repo}/git/trees", token, {"tree": entries})
    if st not in (200, 201):
        print(f"✗ 建 tree 失败（HTTP {st}）：{(tree or {}).get('message')}")
        return 1

    # 4. 建 commit（orphan 模式不挂父提交 → 覆盖历史为单个提交）
    payload = {"message": message, "tree": tree["sha"]}
    if parent_sha and not orphan:
        payload["parents"] = [parent_sha]
    elif orphan:
        print("  ★ orphan 模式：不挂父提交，历史将被替换为单个提交")
    st, commit = api("POST", f"/repos/{owner}/{repo}/git/commits", token, payload)
    if st not in (200, 201):
        print(f"✗ 建 commit 失败（HTTP {st}）：{(commit or {}).get('message')}")
        return 1

    # 5. 更新（或创建）分支 ref
    if parent_sha:
        st, res = api("PATCH", f"/repos/{owner}/{repo}/git/refs/heads/{branch}", token,
                      {"sha": commit["sha"], "force": True})
    else:
        st, res = api("POST", f"/repos/{owner}/{repo}/git/refs", token,
                      {"ref": f"refs/heads/{branch}", "sha": commit["sha"]})
    if st not in (200, 201):
        print(f"✗ 更新 {branch} 失败（HTTP {st}）：{(res or {}).get('message')}")
        return 1

    print(f"\n=== 完成：1 个 commit 提交 {len(entries)} 个文件"
          f"{f'，跳过 {len(skipped)} 个' if skipped else ''} ===")
    print(f"commit   : {commit['sha']}")
    print(f"仓库地址：https://github.com/{owner}/{repo}")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True, help="仓库名，如 ai-news-social-pipeline")
    ap.add_argument("--owner", default=None, help="默认取当前 token 所属账号")
    ap.add_argument("--token", default=None, help="不传则读环境变量 GITHUB_TOKEN / GITHUB_PAT")
    ap.add_argument("--create", action="store_true", help="仓库不存在时创建（公开）")
    ap.add_argument("--private", action="store_true", help="与 --create 配合，建私有仓库")
    ap.add_argument("--description", default="每日 AI 新闻 → 公众号 / 抖音 内容流水线（skill）")
    ap.add_argument("--branch", default="main")
    ap.add_argument("--git", default=DEFAULT_GIT, help="git.exe 路径")
    ap.add_argument("--root", default=str(DEFAULT_ROOT), help="本地仓库根目录")
    ap.add_argument("--mode", choices=["git-api", "contents"], default="git-api",
                    help="git-api=1 个 commit 提交全部（默认）；contents=逐文件 PUT，各产生一个 commit")
    ap.add_argument("--message", default="chore: 同步 ai-news-social-pipeline skill",
                    help="git-api 模式的提交信息")
    ap.add_argument("--orphan", action="store_true",
                    help="创建一个无父提交的根提交并强制覆盖分支 → 历史重置为单个 commit")
    a = ap.parse_args()
    root = Path(a.root).resolve()

    token = a.token or os.environ.get("GITHUB_TOKEN") or os.environ.get("GITHUB_PAT")
    if not token:
        print("✗ 缺少 token。\n"
              "  1) 新建细粒度 PAT：https://github.com/settings/personal-access-tokens/new\n"
              "     权限勾 'Contents: Read and write'\n"
              "  2) set GITHUB_TOKEN=<token>   然后重跑本脚本\n"
              "  ★ token 只用于本次推送，不要写进任何文件或提交到仓库。")
        return 2

    # 1. 确认身份 + 拿 owner
    st, me = api("GET", "/user", token)
    if st != 200:
        print(f"✗ token 无效或无权限（HTTP {st}）：{me}")
        return 1
    owner = a.owner or me["login"]
    print(f"✓ 身份：{me['login']}  → 目标仓库：{owner}/{a.repo}")

    # 2. 仓库是否存在
    st, repo = api("GET", f"/repos/{owner}/{a.repo}", token)
    if st == 404:
        if not a.create:
            print(f"✗ 仓库 {owner}/{a.repo} 不存在。加 --create 让脚本创建它。")
            return 1
        st, repo = api("POST", "/user/repos", token, {
            "name": a.repo,
            "description": a.description,
            "private": bool(a.private),
            "auto_init": False,
        })
        if st not in (200, 201):
            print(f"✗ 创建仓库失败（HTTP {st}）：{repo}")
            return 1
        print(f"✓ 已创建仓库：{repo['html_url']}")
    elif st != 200:
        print(f"✗ 查询仓库失败（HTTP {st}）：{repo}")
        return 1
    else:
        print(f"✓ 仓库已存在：{repo['html_url']}")

    # 3. 上传
    files = git_files(a.git, root)
    print(f"→ 待上传 {len(files)} 个文件（清单来自 git ls-files，已排除 .env 等）\n")

    if a.mode == "git-api":
        return push_via_git_api(owner, a.repo, root, files, token, a.branch, a.message, a.orphan)

    # ---- contents 模式：逐文件 PUT，每个文件产生一个 commit ----
    ok = skip = fail = 0
    for i, rel in enumerate(files, 1):
        p = root / rel
        if not p.is_file():
            print(f"  [{i}/{len(files)}] 跳过（本地不存在）{rel}")
            skip += 1
            continue
        content = base64.b64encode(p.read_bytes()).decode("ascii")
        body = {"message": f"chore: 同步 {rel}", "content": content, "branch": a.branch}

        # ★ 路径必须 percent-encode：中文路径直接拼进 URL 会让 urllib 抛
        #   UnicodeEncodeError('ascii', 'PUT .../contents/凭证恢复操作流程.md ...')
        enc = quote(rel, safe="/")

        # 已存在则需带 sha 才能更新
        st, cur = api("GET", f"/repos/{owner}/{a.repo}/contents/{enc}?ref={a.branch}", token)
        if st == 200 and isinstance(cur, dict) and cur.get("sha"):
            body["sha"] = cur["sha"]

        st, res = api("PUT", f"/repos/{owner}/{a.repo}/contents/{enc}", token, body)
        if st in (200, 201):
            ok += 1
            print(f"  [{i}/{len(files)}] ✓ {rel}")
        else:
            fail += 1
            msg = (res or {}).get("message", res)
            print(f"  [{i}/{len(files)}] ✗ {rel} — HTTP {st}: {msg}")
            if st == 403 and "rate limit" in str(msg).lower():
                print("     （速率限制，等一会儿重跑即可，脚本幂等）")
                time.sleep(5)
        time.sleep(0.05)  # 轻微限速，避免触发滥用检测

    print(f"\n=== 完成：成功 {ok}，跳过 {skip}，失败 {fail} ===")
    print(f"仓库地址：https://github.com/{owner}/{a.repo}")
    if fail:
        print("有失败项：直接重跑本脚本即可（幂等，已上传的会走更新路径）。")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
