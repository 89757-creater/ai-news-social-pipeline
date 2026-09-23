# tools/ —— 平台链路工具链

> ⚠️ **运行时应使用工作区副本 `<WS>/tools/`，不是这里。**
> 本目录是**可移植分发版与归档**（换新工作区时把整个 `tools/` 复制过去即可）。
> 原因：skill 目录会被 marketplace 更新覆盖，本地补进去的文件会静默消失
> （2026-09-19 实测：`wechat-deep-article/scripts/preflight.py` 就是这样没的）。
>
> 改动请**两边都落**，并同步到 Git 仓库。

所有抖音脚本共用底座 `cdp_read.py`（CDP 直连本机 Edge），细则见
`../references/douyin-publish.md` 与技能 `cdp-browser-automation`。

---

## 0. 元工具

| 脚本 | 用途 |
|---|---|
| `push_to_github_api.py` | **把本 skill 仓库推到 GitHub**（走 REST API，绕开被阻断的 `github.com` 传输通道）。见下方说明。 |

### 什么时候需要 push_to_github_api.py

2026-09-23 实测本机网络：

| 目标 | 结果 |
|---|---|
| `api.github.com` | ✅ 200（稳定） |
| `github.com` 主站 | ❌ 000（代理 `CONNECT tunnel failed, 502`，偶发可通） |

`git push` 走的是 `github.com`，因此不可用；Contents / Git Data API 走 `api.github.com`，可用。

```bash
# 1) 取凭据（本机已有：Windows 凭据管理器 git:https://github.com）
PB="C:/Users/suge0/.workbuddy/binaries/PortableGit/versions/1.2.0/mingw64/bin"
TOKEN=$(printf "protocol=https\nhost=github.com\n\n" | "$PB/git-credential-wincred.exe" get | sed -n 's/^password=//p')

# 2) 同步（默认 git-api 模式：1 个 commit 提交全部文件）
GITHUB_TOKEN="$TOKEN" python push_to_github_api.py --repo ai-news-social-pipeline

# 首次初始化 / 需要把历史重置为单个提交时
GITHUB_TOKEN="$TOKEN" python push_to_github_api.py --repo ai-news-social-pipeline \
    --create --orphan --message "feat: ..."
```

要点：
- 文件清单取自 `git ls-files` → 自动排除 `.env` 等 gitignore 内容。
- **默认 `--mode git-api`**：blobs → tree → commit → 更新 ref，只产生 **1 个 commit**。
  `--mode contents` 是逐文件 PUT，每个文件一个 commit，历史会很乱，仅作兜底。
- **`--orphan`**：建无父提交的根提交并强制覆盖分支 → 把历史重置为单个 commit
  （用于修正"已被逐文件上传污染"的仓库，不需要 `delete_repo` 权限）。
- 中文路径必须 percent-encode（脚本已处理）；漏了会报
  `UnicodeEncodeError('ascii', 'PUT .../contents/凭证恢复操作流程.md ...')`。
- 脚本**不落盘任何 token**，只从环境变量读。

---

## 1. 生产链（发一条抖音长图文）

| 步 | 脚本 | 要点 |
|---|---|---|
| 1 | `douyin_fill.py` | 填标题/摘要/正文。**重填必须 `--clear`**（默认追加，会越填越长）。源文件须用 `## 标题 / ## 摘要 / ## 正文` |
| 2 | `douyin_upload2.py` | 头图 + 封面。头图入口文案是「点击替换图片」；头图点「确定」、封面点「完成」 |
| 3 | `douyin_music_pick.py` | **配乐唯一入口**（`--search`）。优先级 R&B → 爵士 → 后朋克 |
| 4 | `douyin_topic.py` | 话题 **≤5 个**。重跑前先读 `topicCount`，已是 5/5 就别重跑 |
| 5 | `douyin_post_article.py` | 全链编排，**默认停在发布前** |
| 6 | `douyin_publish_probe.py` | 点发布 + **读 `create_v2` 接口响应**判定结果（别读页面文案） |

## 2. 维护链（改已发布的稿）

| 脚本 | 用途 |
|---|---|
| `quota_ledger.py` | **删前闸门**。长图文每日上限 10 次，超限 `status_code=536`。台账只是下界 |
| `douyin_delete.py` | 删除作品。**必须先过 quota_ledger** |
| `republish_one.py` | 删旧 + 重发单篇。⚠️ 已知未实现「先发新的、成功后再删旧的」安全顺序 |
| `republish_all.py` | 批量重发 |

⚠️ 抖音「文章」发布后**没有编辑入口** → 配乐/头图/封面只能在发布那一刻设好。

## 3. 资产链（出图与校验）

| 脚本 | 用途 |
|---|---|
| `gen_douyin_cover_illu.py` | 抖音竖版封面 + 头图（1080×1440，Pillow） |
| `gen_douyin_cover.py` | 早期封面版（被上者取代，保留参考） |
| `gen_quote_card.py` | 金句卡 |
| `make_cover_sheet.py` | 把多张封面拼成对照表（挑图用） |
| `make_bgm_sheet.py` | 把候选配乐拼成对照表 |
| `verify_cover_color.py` | 封面配色校验（色相间隔 / RGB 距离 / 底色亮度） |

## 4. 诊断链（页面改版或卡住时用）

| 脚本 | 用途 |
|---|---|
| `cdp_read.py` | **CDP 底座**：标签收敛、元素等待、真实点击、受控输入。其他脚本都 import 它 |
| `edge_keepalive.sh` | 常驻保活：端口不通就重拉带 9222 调试端口的 Edge |
| `state_check.py` | 一次性体检当前编辑器状态（标题/正文/图位/话题计数） |
| `editor_probe.py` | 探测编辑器可用元素与选择器 |
| `dump_manage.py` / `dump_manage_tabs.py` | 导出管理页结构与标签页 |
| `verify_manage.py` | 核对管理页作品数与状态 |
| `check_music_picks.py` / `probe_music_search.py` / `probe_music_tabs.py` | 配乐面板与搜索探测 |
| `probe_toolbar.py` | 工具栏结构探测 |
| `shot_clip.py` | 区域截图存证 |

## 5. 早期版本（**不要用**，保留仅为追溯）

`douyin_upload.py`（被 `douyin_upload2.py` 取代）、`douyin_music.py`（被 `douyin_music_pick.py` 取代）、
`douyin_click.py`、`douyin_type.py`、`_verify_*.py`（一次性验证脚本）。

## 6. wechat/ —— 公众号链

| 文件 | 用途 |
|---|---|
| `scripts/preflight.py` | 发布前自检（title ≤64B / description ≤120B / cover 存在 / 正文图 ≥2） |
| `scripts/publish_wenyan.py` | 渲染 + 推草稿箱。`--check-credentials` 一步分清密钥问题还是 IP 问题 |
| `scripts/draft_status.py` | 查草稿状态 |
| `scripts/gen_cover_pillow.py` | 封面（900×383，Pillow） |
| `.env.example` | 凭证模板（复制为 `.env` 填真值；**`.env` 不入库**） |
| `themes/*.css` | 四套主题：`redwhite`（默认）/ `green` / `blue` / `gray` |
| `凭证恢复操作流程.md` | AppSecret 重置 / IP 白名单的完整操作步骤 |
| `README.md` / `SKILL_ref.md` | 历史文档（含 wenyan 渲染链说明） |

⚠️ 公众号天花板是**草稿箱**：`freepublish/submit`（群发）返回 `48001`。
硬性表述纪律见 `../SKILL.md` 第 0 节。
