#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把本 skill 打包成 WorkBuddy 开放平台可上传的 ZIP。

官方规范（https://open.workbuddy.cn/docs/skill）：
  · 结构：{skill-name}/SKILL.md + references/ + scripts/ + templates/
  · frontmatter 必填：description / description_zh / description_en / version / author
  · ZIP ≤ 3MB
  · 不得夹带 API Key / 密码 / Cookie

本脚本做三件事：
  1. **结构收敛**：只保留官方列举的四个位置。
     - references/*.md            → 原样
     - scripts/*.py + tools/**/*.py → 拍平进 scripts/（重名且内容不同则加前缀消歧）
     - tools/wechat/themes/*.css  → templates/
     - tools/wechat/*.md（凭证恢复流程等）→ references/
     不进包：README.md、LICENSE、.gitignore/.gitattributes、agents/、examples/、
             tools/README.md（那是仓库内索引，不是技能资产）
  2. **校验**：frontmatter 必填字段 / 路径层级 / 体积 / 密钥扫描（3 类红灯）
  3. **打包** + 打印上传清单

用法：
    python package_for_market.py                 # 输出到 skill 同级目录
    python package_for_market.py -o D:/out.zip   # 指定输出
    python package_for_market.py --check-only    # 只校验不打包
"""
import argparse
import hashlib
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent      # skill 根目录
SKILL_NAME = ROOT.name

# frontmatter 必填字段（官方文档）
REQUIRED = ["description", "description_zh", "description_en", "version", "author"]

# 密钥红灯：命中即中止打包（宁可误报也不要把凭证发出去）
SECRET_PATTERNS = [
    (r"\b(?:gho|ghp|ghu|ghs|github_pat)_[A-Za-z0-9_]{10,}", "GitHub token"),
    (r"\bsk-[A-Za-z0-9]{20,}", "OpenAI 风格 API Key"),
    (r"AKIA[0-9A-Z]{16}", "AWS Access Key"),
    (r"\bwx[0-9a-f]{16}\b", "疑似微信 AppID"),
    (r"\b[0-9a-f]{32}\b", "32 位十六进制串（疑似 AppSecret / 密钥）"),
    (r"(?i)(api[_-]?key|app[_-]?secret|password|access[_-]?token)\s*[:=]\s*[\"']?[A-Za-z0-9_\-]{16,}",
     "键值形式的密钥赋值"),
]

MAX_BYTES = 3 * 1024 * 1024   # 官方限制 3MB
MAX_DEPTH = 2                 # {skill}/dir/file → 2 个斜杠


def collect():
    """返回 {包内相对路径: 本地 Path}，已做拍平与消歧。"""
    out = {}
    dupe_notes = []

    def add(arc, src: Path):
        if arc in out:
            if hashlib.sha256(out[arc].read_bytes()).digest() == hashlib.sha256(src.read_bytes()).digest():
                dupe_notes.append(f"  同名且内容相同，去重：{arc}（来自 {src.relative_to(ROOT)}）")
                return
            stem, suf = Path(arc).stem, Path(arc).suffix
            new = f"scripts/wechat_{stem}{suf}"
            dupe_notes.append(f"  同名但内容不同，改名消歧：{arc} → {new}")
            arc = new
            if arc in out:
                raise SystemExit(f"✗ 消歧后仍冲突：{arc}")
        out[arc] = src

    # SKILL.md
    add("SKILL.md", ROOT / "SKILL.md")

    # references：原有 + wechat 文档
    for p in sorted((ROOT / "references").glob("*.md")):
        add(f"references/{p.name}", p)
    for p in sorted((ROOT / "tools" / "wechat").glob("*.md")):
        if p.name == "README.md":
            continue
        add(f"references/{p.name}", p)

    # scripts：通用脚本 + tools 全部脚本 + wechat 脚本（拍平）
    for base in [ROOT / "scripts", ROOT / "tools", ROOT / "tools" / "wechat" / "scripts"]:
        if not base.is_dir():
            continue
        for p in sorted(base.iterdir()):
            if p.is_file() and p.suffix in (".py", ".sh"):
                add(f"scripts/{p.name}", p)

    # templates：主题 CSS
    themes = ROOT / "tools" / "wechat" / "themes"
    if themes.is_dir():
        for p in sorted(themes.glob("*.css")):
            add(f"templates/{p.name}", p)

    return out, dupe_notes


def parse_frontmatter(text):
    m = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
    if not m:
        return None
    meta = {}
    for line in m.group(1).splitlines():
        if ":" in line and not line.strip().startswith("#"):
            k, v = line.split(":", 1)
            meta[k.strip().lower()] = v.strip().strip('"').strip("'")
    return meta


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-o", "--out", default=None)
    ap.add_argument("--check-only", action="store_true")
    a = ap.parse_args()

    problems, warns = [], []
    print(f"技能目录：{ROOT}")
    print(f"技能包名：{SKILL_NAME}/\n")

    # ---- 收集 ----
    files, dupes = collect()
    if dupes:
        print("结构收敛：")
        print("\n".join(dupes))
        print()

    # ---- 校验 1：frontmatter ----
    print("【1/4】frontmatter 必填字段")
    skill_md = ROOT / "SKILL.md"
    meta = parse_frontmatter(skill_md.read_text(encoding="utf-8"))
    if not meta:
        problems.append("SKILL.md 缺少 YAML frontmatter")
    else:
        for k in REQUIRED:
            v = meta.get(k, "")
            if v:
                print(f"  ✓ {k}: {v[:60]}{'…' if len(v) > 60 else ''}")
            else:
                problems.append(f"frontmatter 缺必填字段：{k}")
                print(f"  ✗ {k}: 缺失")
        for k in ("display_name", "category", "name"):
            if meta.get(k):
                print(f"  · {k}: {meta[k]}")

    # ---- 校验 2：路径层级 ----
    print("\n【2/4】包内路径层级")
    deep = [p for p in files if p.count("/") > MAX_DEPTH]
    print(f"  条目 {len(files)} 个；最深 {max((p.count('/') for p in files), default=0)} 层（上限 {MAX_DEPTH}）")
    if deep:
        problems.append(f"超出层级上限的文件：{deep[:5]}")

    # ---- 校验 3：密钥扫描 ----
    print("\n【3/4】密钥扫描")
    hits = []
    for arc, src in files.items():
        if src.suffix in (".png", ".jpg", ".zip"):
            continue
        try:
            text = src.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for pat, label in SECRET_PATTERNS:
            for m in re.finditer(pat, text):
                seg = m.group(0)
                # .env.example 里的全 0 占位不算
                if set(seg) <= {"0"}:
                    continue
                hits.append(f"{arc}: {label} → {seg[:14]}…")
    if hits:
        problems.append("疑似密钥：" + "; ".join(hits[:5]))
        print("  ✗ 命中：")
        for h in hits[:10]:
            print("    " + h)
    else:
        print("  ✓ 未发现密钥（token / API Key / AppSecret / 键值赋值）")

    # ---- 校验 4：体积 ----
    print("\n【4/4】体积")
    total = sum(s.stat().st_size for s in files.values())
    print(f"  未压缩 {total / 1024:.0f} KB / 上限 {MAX_BYTES / 1024:.0f} KB")
    if total > MAX_BYTES:
        problems.append("未压缩体积已超 3MB")

    if problems:
        print("\n❌ 校验未通过，未打包：")
        for p in problems:
            print("  - " + p)
        return 1
    if warns:
        for w in warns:
            print("  ⚠ " + w)

    if a.check_only:
        print("\n✅ 校验通过（--check-only，未打包）")
        return 0

    # ---- 打包 ----
    out = Path(a.out) if a.out else ROOT.parent / f"{SKILL_NAME}-market.zip"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for arc, src in sorted(files.items()):
            z.write(src, f"{SKILL_NAME}/{arc}")

    size = out.stat().st_size
    print(f"\n✅ 已打包：{out}")
    print(f"   压缩后 {size / 1024:.0f} KB（{len(files)} 个文件）")
    if size > MAX_BYTES:
        print("   ✗ 压缩后仍超 3MB —— 请剔除大图或改用外链")
        return 1

    print("\n上传清单（WorkBuddy 开放平台 → 发布技能）：")
    print(f"  包名      : {SKILL_NAME}")
    print(f"  展示名    : {meta.get('display_name', '')}")
    print(f"  分类      : {meta.get('category', '')}")
    print(f"  版本      : {meta.get('version', '')}")
    print(f"  作者      : {meta.get('author', '')}")
    print(f"  技能包    : {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
