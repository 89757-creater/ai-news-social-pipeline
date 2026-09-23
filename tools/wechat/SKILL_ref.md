---
name: wechat-wenyan-publish
display_name: 公众号全流程发布
display_name_en: WeChat Article Full-Pipeline Publisher
description: 微信公众号全流程发布技能：写稿规范 → 封面生成（900×383 无署名）→ SVG 转 PNG 配图 → wenyan 自定义主题排版（redwhite/green/blue/gray 四套）→ 发布前字节自检 → 直连微信 API 发布草稿 → 发布后核实。一键脚本从 markdown 直发草稿箱，需要用户自备公众号 AppID/AppSecret（环境变量 WECHAT_APP_ID / WECHAT_APP_SECRET，且调用 IP 须在公众号后台白名单内）。用于公众号发文、写公众号、发布文章、排版发布、发草稿、微信公众号全流程等需求。
description_zh: 公众号全流程：写稿规范→封面→配图→wenyan 四主题排版→字节自检→直连微信 API 发草稿→核实
description_en: "Full WeChat article pipeline: writing standards, cover and diagram generation, wenyan theme formatting, byte-limit preflight, direct WeChat API draft publishing, and post-publish verification"
category: 内容创作
version: 1.0.0
---

# wechat-wenyan-publish：微信公众号全流程发布

把成熟的公众号发布链路固化成一步到位流程：
**写稿 → 自检 → 封面 → 配图 → 排版 → 发布 → 核实**。

## 何时使用

用户要写公众号文章 / 发草稿 / 排版发布 / 给公众号配图封面（不是简单排版，是完整发布流程）。

## 技能结构

```
wechat-wenyan-publish/
├── SKILL.md                  # 本文件（全流程说明）
├── scripts/
│   ├── preflight.py          # 发布前自检（字节/图片/元数据）
│   ├── gen_cover.py          # 编辑风封面（900×383，无署名）— 需 cairosvg
│   ├── gen_cover_pillow.py   # 同形参数，纯 Pillow 版（无 cairo 环境用这个）
│   ├── gen_diagrams.py       # SVG→PNG 配图（白底中文标签）— 需 cairosvg
│   └── publish_wenyan.py     # 一键渲染+直连 API 发布（--verify 自动核实）
├── themes/                   # 4 套自定义主题（redwhite/green/blue/gray）
└── references/
    ├── wechat-api-limits.md        # 微信 API 硬约束
    ├── cover-and-image-style.md    # 封面/配图风格规范
    ├── workflow-checklist.md       # 逐项清单与常见坑
    └── theme-tuning.md             # 主题色板映射与调优
```

## 凭证与前置条件（执行前必读）

- **必须由用户提供自己的公众号 AppID / AppSecret**，通过环境变量传入：
  `export WECHAT_APP_ID=wx...` / `export WECHAT_APP_SECRET=...`
- 本技能**不内置、不落盘任何凭证**；没有凭证时只执行到自检/封面/配图/渲染为止，如实告知用户无法发布。
- **IP 白名单**：微信 API 要求调用方服务器 IP 在公众号后台「设置与开发 → 安全中心」白名单内；在沙箱/容器环境运行时若报 40164（IP 不在白名单），如实转告用户，不要重试硬闯。

## 环境准备（首次使用一次即可）

### 1) 安装 wenyan CLI 并注册本技能主题

```bash
npm install -g @wenyan-md/cli        # 依赖树较大（mermaid / jsdom / mathjax 等），npm cache 约 600MB
wenyan --version                     # 期望输出版本号，如 2.0.11

# 关键一步：本技能的 4 套主题是自定义 CSS，装完必须注册，否则 -t redwhite 会取不到
TDIR="<本技能目录>/themes"
for t in redwhite green blue gray; do
  wenyan theme --add --name "$t" --path "$TDIR/$t.css"
done
wenyan theme -l                      # 「自定义主题」下应能看到红白/绿/蓝/灰 4 项
```

- **主题注册命令易错**：完整形式是 `wenyan theme --add --name <名> --path <css绝对路径>`；只写 `wenyan theme --add <css>` 会报参数错误。Windows 下 `--path` 必须传 `C:/...` 或 `C:\...` 形式的**Windows 路径**，传 MSYS 风格 `/c/...` 会被当成相对路径而报 ENOENT。
- **Windows 注意**：npm 全局 bin 是 `wenyan.cmd`。若当前 shell 的 PATH 里没有它，可把 node 安装目录加入用户 PATH，或设环境变量 `WENYAN_BIN` 指向 `...\node\versions\<ver>\wenyan.cmd`。`publish_wenyan.py` 已内置三级定位（`WENYAN_BIN` → `PATH` → 托管 node 目录兜底）并会在 Windows 下自动经 `cmd /c` 调用 `.cmd`，无需手工改写命令。

### 2) 图片依赖

- 封面/配图需要 **Pillow**：`pip install Pillow`。
- `gen_cover.py` / `gen_diagrams.py` 额外依赖 **cairosvg**（SVG 光栅化）。**Windows 默认没有 libcairo，会直接报 `libcairo-2.dll` 加载失败**。
- 无 cairo 环境请改用 **`gen_cover_pillow.py`**（参数与 gen_cover.py 同形，纯 Pillow 实现，无需 cairo）；正文配图直接用 Pillow 绘制即可，不必绕 SVG→PNG。

## 执行流程

### 第 0 步：写稿（联网核实事实）
- 写前核实关键事实，标注来源意识；观点性判断按观点处理，不要写成硬事实。
- 用全角标点；不用「本文看点」；章节标题 4-5 字为宜；工具类文章文末附可复制安装命令。
- 文末落款按用户账号的惯用风格，没有则给一个简洁的中性落款。

### 第 1 步：frontmatter（微信 API 硬约束）
```yaml
---
title: 标题（≤64 字节，中文≈3B/字，先数后写）
cover: /绝对路径/cover.png
author: 作者名（≤8 字节）
description: 摘要（≤120 字节，会渲染成文首导语引用块，写一句有钩子的）
---
```
正文图片引用一律 `![](assets/xx.png)`（PNG/JPG，**严禁 SVG**）。

### 第 2 步：自检 + 封面 + 配图
```bash
python scripts/preflight.py article.md              # 字节与图片校验，不过就先修

# 封面（二选一，看环境）
python scripts/gen_cover.py --out cover.png \        # 有 cairo 时
    --eyebrow "栏目 · 日期" \
    --title "主标题" --subtitle "副标题" \
    --pills "卖点1,卖点2,卖点3" [--right-svg 自定义.svg]

python scripts/gen_cover_pillow.py --out cover.png \ # Windows / 无 cairo 时用这个（参数同上）
    --eyebrow "栏目 · 日期" \
    --title "主标题" --subtitle "副标题" \
    --pills "卖点1,卖点2,卖点3"

python scripts/gen_diagrams.py 图1.svg 图2.svg       # 配图（有 cairo）；无 cairo 用 Pillow 直接画
```
- **封面一律不加作者署名**（不放"作者名·"式水印，保持版面干净）。
- 配图统一白底、中文标签、#10a37f 主色，几何要素（箭头/对齐）用坐标算清楚，别写死估数。
- 字体：优先 Noto Sans CJK；脚本内置多路径查找（Linux/macOS/Windows），容器无 CJK 字体时安装 `fonts-noto-cjk`。

### 第 3 步：一键发布（wenyan 主题渲染 → 直连微信 API）
```bash
python scripts/publish_wenyan.py article.md --theme redwhite --dry-run   # 先试跑
python scripts/publish_wenyan.py article.md --theme redwhite --verify    # 正式发+核实
```
- 主题：`redwhite`(红白 #DC2626)、`green`(摸鱼绿 #059669)、`blue`(科技蓝 #2563EB)、`gray`(石墨灰 #52525B)。**使用前必须先注册**（命令见「环境准备」）。
- 先看效果不必发布：`wenyan render -f article.md -t redwhite -h github --no-footnote > body.html`；输出是纯内联样式的 `<section id="wenyan">` 片段（无 `<style>` 标签），正是微信要求的形态，可直接进草稿。同一篇稿件四套主题渲染结果约 17.6KB，彼此仅颜色不同。
- 脚本自动：wenyan render → 正文图片经 `media/uploadimg` 换成微信链接 → 封面经 `material/add_material` 上传 → `draft/add` 建草稿；`--verify` 再调 `draft/get` 核实。
- 零第三方依赖：API 调用用 Python 标准库 urllib 实现。

### 第 4 步：核实
- `--verify` 自动调用 `draft/get`，核对图数、中文字数、标题/摘要字节。
- 也可以用 `--dry-run` 只渲染不发布，把 HTML 交给用户手动粘贴。

## 常见坑（详见 references/workflow-checklist.md）

1. title/summary 超字节 → 微信 API 直接拒；用 preflight.py 先把关。
2. wenyan 输出正文图为相对路径 → publish_wenyan.py 已自动处理并上传换取微信链接。
3. SVG 进正文 → 微信拒收，一律转 PNG。
4. 40164 IP 不在白名单 → 让用户把当前出口 IP 加进公众号后台白名单，不要反复重试。
5. 40001 invalid credential → access_token 过期或 secret 错误，重取 token 或核对凭证。
6. `-t redwhite` 报主题不存在 → 四套自定义主题没注册，按「环境准备」第 1 步补注册。
7. Windows 下 `FileNotFoundError: [WinError 2]` 且指向 wenyan → 子进程没定位到 `wenyan.cmd`。设 `WENYAN_BIN` 或把 node 安装目录加入 PATH（本版 `publish_wenyan.py` 已内置兜底与 `cmd /c` 包装）。
8. `libcairo-2.dll` / cairosvg 加载失败 → Windows 无 cairo，封面改用 `gen_cover_pillow.py`，配图改用 Pillow 直接绘制。
9. npm 安装 wenyan 卡住或超时 → 依赖树很大（mermaid/jsdom/mathjax），用后台任务跑或加长超时；重复执行是增量的，会续传已完成的部分。

## 能力边界

- 只支持**公众号草稿箱**链路（建草稿、查草稿、删草稿）；不负责群发、评论管理、素材库整理。
- 需要**已认证的公众号账号**（个人订阅号即可调 draft API）；测试号无草稿箱能力。
- 排版主题基于 wenyan 渲染器；对 `<style>` 支持有限，复杂交互组件不支持。
