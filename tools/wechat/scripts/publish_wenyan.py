#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""一键：markdown → wenyan 自定义主题渲染 → 直连微信 API → 公众号草稿 →（可选）核实

用法：
  python3 publish_wenyan.py article.md [--theme redwhite|green|blue|gray] [--title X]
      [--summary Y] [--author NAME] [--cover cover.png] [--dry-run] [--verify] [--no-footnote]
  python3 publish_wenyan.py --check-credentials   # 只查凭证就绪情况，不发请求

凭证（必须由用户提供，本脚本不内置）：
  优先读环境变量 WECHAT_APP_ID / WECHAT_APP_SECRET；
  两者不全时，自动兜底加载 .env（查找顺序：CWD/.env → scripts/.env → tools/wechat/.env）。
  且调用方 IP 需在公众号后台「安全中心」白名单内，否则 API 返回 40164。

说明：
  - 正文图片先经 media/uploadimg 换成微信链接（外链图在正文里不可靠）
  - 封面经 material/add_material 上传为永久素材拿 thumb_media_id
  - 最后 draft/add 建草稿；--verify 用 draft/get 核实图数与字数
  - API 调用全部用标准库 urllib，零第三方依赖
"""
import argparse
import json
import mimetypes
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

API_BASE = "https://api.weixin.qq.com/cgi-bin"
VALID_THEMES = ["redwhite", "green", "blue", "gray"]


# ──────────────────────────────────────────────
#  wenyan CLI 定位（跨平台；Windows 的 .cmd 包装需经 cmd /c）
# ──────────────────────────────────────────────
def resolve_wenyan() -> str:
    """定位 wenyan 可执行文件。

    顺序：WENYAN_BIN 环境变量 → PATH 查找 → 托管 node 全局 bin 兜底。
    Windows 下优先取 .cmd 包装（CreateProcess 无法直接执行 shell 脚本）。
    """
    env_bin = os.environ.get("WENYAN_BIN", "").strip()
    if env_bin and Path(env_bin).is_file():
        return env_bin
    names = (["wenyan", "wenyan.cmd", "wenyan.exe", "wenyan.bat"]
             if os.name == "nt" else ["wenyan"])
    for n in names:
        exe = shutil.which(n)
        if exe:
            return exe
    # 兜底：WorkBuddy 托管 node 的全局 bin（npm prefix = node 安装目录）
    versions = Path.home() / ".workbuddy" / "binaries" / "node" / "versions"
    if versions.is_dir():
        for d in sorted(versions.iterdir(), reverse=True):
            for n in ("wenyan.cmd", "wenyan"):
                cand = d / n
                if cand.is_file():
                    return str(cand)
    raise SystemExit(
        "ERROR: 未找到 wenyan CLI（@wenyan-md/cli）。\n"
        "  安装：npm install -g @wenyan-md/cli\n"
        "  若已安装仍找不到，请设 WENYAN_BIN 指向 wenyan(.cmd) 的绝对路径。"
    )


def wenyan_argv(sub_args: list) -> list:
    """构造可跨平台执行的 wenyan 命令。"""
    exe = resolve_wenyan()
    cmd = [exe, *sub_args]
    if os.name == "nt" and exe.lower().endswith((".cmd", ".bat")):
        comspec = os.environ.get("COMSPEC") or r"C:\Windows\System32\cmd.exe"
        cmd = [comspec, "/c", *cmd]
    return cmd


# ──────────────────────────────────────────────
#  HTTP helpers（标准库 multipart）
# ──────────────────────────────────────────────
class ApiError(SystemExit):
    def __init__(self, where: str, payload: dict):
        code = payload.get("errcode", "?")
        msg = payload.get("errmsg", "unknown")
        hint = ""
        if code in (40164, 61004):
            hint = ("\n[提示] %s = 调用方 IP 不在公众号白名单（官方文档记 61004，实测 40164 亦常见）。\n"
                    "  修复：打开 https://developers.weixin.qq.com/platform/ 扫码登录\n"
                    "        → 我的业务 → 公众号/服务号 → 基础信息 → 开发密钥 → IP 白名单「编辑」；\n"
                    "  ⚠️ 必须是 /platform/ 路径：裸域名 developers.weixin.qq.com 会落到\n"
                    "     「微信开放社区」资讯站，那里没有「我的业务」。\n"
                    "  已有 IP 不要删，另起一行加上当前出口 IP。\n"
                    "  当前出口 IP 查询：python publish_wenyan.py --check-credentials") % code
        elif code == 40013:
            hint = "\n[提示] 40013 = AppID 无效。核对 WECHAT_APP_ID 是否为该公众号的原始 ID（wx 开头）。"
        elif code == 40001:
            hint = ("\n[提示] 40001 = 凭证无效。核对 WECHAT_APP_SECRET；"
                    "若刚重置过 AppSecret，旧值已立即失效。")
        elif code == 40125:
            hint = ("\n[提示] 40125 = AppSecret 无效（invalid appsecret）。\n"
                    "  与 40164/61004 不同：这不是 IP 白名单问题，是密钥本身对不上。\n"
                    "  常见成因：① 在平台上重置过 AppSecret（旧值立即失效）；\n"
                    "            ② .env 里的值被改过 / 复制时漏字符。\n"
                    "  修复：https://developers.weixin.qq.com/platform/ 扫码登录\n"
                    "        → 我的业务 → 公众号/服务号 → 基础信息 → 开发密钥 → 重置 AppSecret，\n"
                    "        把新值写入 tools/wechat/.env 的 WECHAT_APP_SECRET，再跑 --check-credentials。\n"
                    "  注意：本错误发生时 AppID 是有效的（否则会返回 40013），所以只需换 Secret。")
        elif code == 40243:
            hint = ("\n[提示] 40243 = AppSecret 被冻结。\n"
                    "  修复：微信开发者平台 → 我的业务 → 公众号 → 开发密钥 → 解冻（约 10 分钟生效）。")
        elif code == 40007:
            hint = "\n[提示] 40007 = media_id 非法。封面必须先经 material/add_material 上传。"
        elif code == 48001:
            hint = ("\n[提示] 48001 = 该接口无权限。个人主体账号的 freepublish/submit（群发）"
                    "自 2025-07 起被回收——draft/* 可用，群发必须账号主手动点。")
        super().__init__(f"{where} 失败 errcode={code}: {msg}{hint}")


def _post_multipart(url: str, file_field: str, file_path: Path) -> dict:
    boundary = uuid.uuid4().hex
    mime = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
    with open(file_path, "rb") as f:
        data = f.read()
    body = b"".join([
        f"--{boundary}\r\n".encode(),
        f'Content-Disposition: form-data; name="{file_field}"; filename="{file_path.name}"\r\n'.encode(),
        f"Content-Type: {mime}\r\n\r\n".encode(),
        data,
        f"\r\n--{boundary}--\r\n".encode(),
    ])
    req = urllib.request.Request(
        url, data=body, method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    if "errcode" in payload and payload["errcode"]:
        raise ApiError(f"POST {url.split('?')[0]}", payload)
    return payload


def _post_json(url: str, payload: dict) -> dict:
    req = urllib.request.Request(
        url, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"), method="POST",
        headers={"Content-Type": "application/json; charset=utf-8"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        result = json.loads(resp.read().decode("utf-8"))
    if "errcode" in result and result["errcode"]:
        raise ApiError(f"POST {url.split('?')[0]}", result)
    return result


# ──────────────────────────────────────────────
#  WeChat API steps
# ──────────────────────────────────────────────
def get_access_token(appid: str, secret: str) -> str:
    qs = urllib.parse.urlencode({"grant_type": "client_credential", "appid": appid, "secret": secret})
    with urllib.request.urlopen(f"{API_BASE}/token?{qs}", timeout=30) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    if "access_token" not in payload:
        raise ApiError("获取 access_token", payload)
    return payload["access_token"]


def upload_content_image(token: str, img: Path) -> str:
    """正文图片 → 微信临时链接（uploadimg，图文消息内用）"""
    payload = _post_multipart(f"{API_BASE}/media/uploadimg?access_token={token}", "media", img)
    return payload["url"]


def upload_cover_material(token: str, cover: Path) -> str:
    """封面 → 永久图片素材（add_material），返回 media_id 供草稿 thumb 用"""
    payload = _post_multipart(f"{API_BASE}/material/add_material?type=image&access_token={token}", "media", cover)
    return payload["media_id"]


def add_draft(token: str, article: dict) -> str:
    payload = _post_json(f"{API_BASE}/draft/add?access_token={token}", {"articles": [article]})
    return payload["media_id"]


def get_draft(token: str, media_id: str) -> dict:
    return _post_json(f"{API_BASE}/draft/get?access_token={token}", {"media_id": media_id})


# ──────────────────────────────────────────────
#  凭证来源：环境变量优先，其次 .env 兜底
#  （脚本不内置任何凭证；.env 只是让「写一次、长期免 export」成为可能）
# ──────────────────────────────────────────────
CRED_KEYS = ("WECHAT_APP_ID", "WECHAT_APP_SECRET")


def candidate_env_files() -> list:
    """按优先级列出可能存放凭证的 .env 路径。"""
    here = Path(__file__).resolve()
    return [
        Path.cwd() / ".env",          # 当前工作目录
        here.parent / ".env",         # scripts/.env
        here.parent.parent / ".env",  # tools/wechat/.env  ← 推荐位置
    ]


def load_dotenv() -> str:
    """从 .env 载入 WECHAT_* 到 os.environ；已设置的环境变量优先、不被覆盖。

    返回实际载入的 .env 路径；未载入任何文件则返回空串。
    """
    if all(os.environ.get(k, "").strip() for k in CRED_KEYS):
        return ""  # 环境变量已齐，无需读文件
    for p in candidate_env_files():
        if not p.is_file():
            continue
        for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k, v = k.strip(), v.strip().strip('"').strip("'")
            if k in CRED_KEYS and v and not os.environ.get(k, "").strip():
                os.environ[k] = v
        return str(p)
    return ""


def _mask(s: str) -> str:
    if not s:
        return "(空)"
    return (s[:4] + "…" + "*" * 4) if len(s) > 8 else "*" * len(s)


def public_ip() -> str:
    """查当前出口 IP（直连、绕过系统代理）。失败返回空串，不抛异常。"""
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    for url in ("https://ipinfo.io/ip", "https://api.ipify.org"):
        try:
            with opener.open(url, timeout=6) as r:
                ip = r.read().decode("utf-8", "ignore").strip()
            if ip and len(ip) <= 45:
                return ip
        except Exception:
            continue
    return ""


def report_credentials(env_file: str) -> None:
    """报告凭证就绪情况；只对外查一次出口 IP，不触碰任何微信接口。"""
    appid = os.environ.get("WECHAT_APP_ID", "").strip()
    secret = os.environ.get("WECHAT_APP_SECRET", "").strip()
    print("凭证自检：")
    print(f"  WECHAT_APP_ID     = {_mask(appid)}")
    print(f"  WECHAT_APP_SECRET = {_mask(secret)}")
    print(f"  .env 载入         = {env_file or '（无）'}")
    ip = public_ip()
    if ip:
        print(f"  当前出口 IP       = {ip}   ← 必须在公众号 IP 白名单内")
    else:
        print("  当前出口 IP       = （查询失败，可浏览器访问 https://ipinfo.io/ip 自查）")
    if appid and secret:
        print("  → 凭证就绪，可执行发布")
        print("    （若报 40164 / 61004，就是上面这个 IP 不在白名单）")
    else:
        print("  → 凭证缺失，发布不可用；--dry-run 仍可只渲染 HTML。")
        print("    修复：把 WECHAT_APP_ID / WECHAT_APP_SECRET 写入 "
              f"{Path(__file__).resolve().parent.parent / '.env'}")


# ──────────────────────────────────────────────
#  Pipeline
# ──────────────────────────────────────────────
def parse_frontmatter(md: Path):
    """粗解析 frontmatter：title/cover/author/description"""
    text = md.read_text(encoding="utf-8")
    meta = {}
    m = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
    if m:
        for line in m.group(1).splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                meta[k.strip().lower()] = v.strip().strip('"').strip("'")
    return meta


def rewrite_body_images(token: str, html: str, base_dir: Path) -> tuple[str, int]:
    """把正文里的本地图片经 uploadimg 换成微信链接，返回 (新html, 上传数)"""
    count = 0

    def repl(m: re.Match) -> str:
        nonlocal count
        src = m.group(1)
        if src.startswith(("http://", "https://")):
            return m.group(0)
        local = (base_dir / src).resolve()
        if not local.is_file():
            raise SystemExit(f"ERROR: 正文图片不存在: {src}")
        url = upload_content_image(token, local)
        count += 1
        return f'src="{url}"'

    html = re.sub(r'src="([^"]+\.(?:png|jpe?g|webp|gif))"', repl, html, flags=re.IGNORECASE)
    return html, count


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("md", type=Path, nargs="?",
                    help="稿件 markdown 路径（--check-credentials 时可省略）")
    ap.add_argument("--theme", default="redwhite", choices=VALID_THEMES)
    ap.add_argument("--title")
    ap.add_argument("--summary")
    ap.add_argument("--author", default="")
    ap.add_argument("--cover")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--no-footnote", action="store_true")
    ap.add_argument("--check-credentials", action="store_true",
                    help="只报告凭证来源与掩码，不发任何请求，随后退出")
    args = ap.parse_args()

    # 凭证来源：环境变量优先，其次 .env 兜底
    env_file = load_dotenv()
    if args.check_credentials:
        report_credentials(env_file)
        return

    if args.md is None:
        raise SystemExit("ERROR: 缺少稿件路径（仅 --check-credentials 可省略）。")
    md = args.md.resolve()
    meta = parse_frontmatter(md)

    title = args.title or meta.get("title") or md.stem
    # 修正（2026-09-19）：原先 Path(...).resolve() 以 CWD 为基准，工作目录不是稿件目录时
    # 会把相对 cover 解析到错误位置并误报「cover 不存在」。改为优先相对 md 所在目录解析。
    _raw_cover = args.cover or meta.get("cover") or ""
    cover = Path(_raw_cover)
    if not cover.is_absolute():
        cover = md.parent / cover
    cover = cover.resolve()
    if not cover.is_file():
        raise SystemExit(f"ERROR: cover 不存在: {cover}")
    author = args.author or meta.get("author") or ""
    summary = args.summary or meta.get("description") or meta.get("summary") or ""

    # 0) 发布需要凭证；dry-run 不需要（凭证可来自环境变量或 .env，脚本不内置）
    if not args.dry_run:
        appid = os.environ.get("WECHAT_APP_ID", "").strip()
        secret = os.environ.get("WECHAT_APP_SECRET", "").strip()
        if not (appid and secret):
            raise SystemExit(
                "ERROR: 未设置 WECHAT_APP_ID / WECHAT_APP_SECRET（环境变量与 .env 均无）。\n"
                "  本脚本不内置任何凭证。修复任选其一：\n"
                f"  ① 写入 {(Path(__file__).resolve().parent.parent / '.env')}（推荐，脚本会自动加载）\n"
                "  ② 调用前 export 这两个环境变量\n"
                "  → 本次未生成草稿，仅本地渲染可用（加 --dry-run）。"
            )
        print("  获取 access_token ...")
        token = get_access_token(appid, secret)

    # 1) wenyan 渲染
    cmd = wenyan_argv(["render", "-f", str(md), "-t", args.theme, "-h", "github"])
    if args.no_footnote:
        cmd.append("--no-footnote")
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    if proc.returncode != 0:
        raise SystemExit(f"wenyan render 失败: {proc.stderr[:500]}")
    html = proc.stdout
    print(f"  渲染完成：theme={args.theme}, {len(html)} 字符")

    if args.dry_run:
        with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8") as f:
            f.write(html)
            print(f"  dry-run 输出: {f.name}（未发布）")
        return

    # 2) 正文图片上传换取微信链接
    html, n_imgs = rewrite_body_images(token, html, md.parent)
    print(f"  正文图片已上传 {n_imgs} 张")

    # 3) 封面上传为永久素材
    thumb_media_id = upload_cover_material(token, cover)
    print(f"  封面已上传: thumb_media_id={thumb_media_id}")

    # 4) 建草稿
    media_id = add_draft(token, {
        "title": title,
        "author": author,
        "digest": summary,
        "content": html,
        "thumb_media_id": thumb_media_id,
        "need_open_comment": 0,
        "only_fans_can_comment": 0,
    })
    print(f"media_id={media_id}")

    # 5) 可选：核实
    if args.verify:
        d = get_draft(token, media_id)
        item = (d.get("news_item") or [{}])[0]
        content = item.get("content", "")
        img_count = len(re.findall(r"<img\b", content))
        cn_chars = len(re.findall(r"[\u4e00-\u9fff]", re.sub(r"<[^>]+>", "", content)))
        print(f"核实 ✓ {item.get('title', title)} | 图: {img_count} | 中文字: {cn_chars}")


if __name__ == "__main__":
    main()
