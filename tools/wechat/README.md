# tools/wechat —— 公众号发布脚本（自有副本）

## 为什么有这个目录

原先发布链路依赖 skill 目录 `~/.workbuddy/skills/wechat-deep-article/scripts/`
（技能文档与历史记录都指向该路径）。**2026-09-19 实测该路径下已不存在发布脚本**，
`wechat-deep-article` 现为 marketplace 安装版（v2.3.0），只含
`article_colors.json / check_env.py / init.py / validate_article.py`，**不含 preflight 与 publish**。

发布脚本的真实落点只剩归档目录：
`~/.workbuddy/skills_archived_2026-09-14/wechat-wenyan-publish/scripts/`

为免再次被 skill 更新覆盖，把脚本 + themes 复制到工作区自有目录，**以本目录为准**。

## 目录内容

```
tools/wechat/
├── scripts/
│   ├── preflight.py        # 发布前自检（frontmatter 字节数 / 封面 / 正文图数）
│   ├── publish_wenyan.py   # 渲染 + 上传素材 + 推草稿箱（含 --check-credentials 自检）
│   ├── gen_cover_pillow.py # 封面（Pillow 版，无 cairosvg 依赖）
│   └── gen_diagrams.py     # 正文配图（内容写死为 2026-09-14 选题，换题需另写）
├── themes/                 # redwhite / green / blue / gray
├── .env                    # 凭证（值为空 = 未配置；填法见操作流程文档）
├── .env.example            # 凭证模板（填坏 .env 时对照用）
├── 凭证恢复操作流程.md      # ★ 从零恢复凭证的完整步骤（后台点击路径 / 错误码对照）
└── SKILL_ref.md            # 归档版的 SKILL.md，留作参考
```

## 依赖

- Python：`C:/Users/suge0/.workbuddy/binaries/python/envs/default/Scripts/python.exe`
- 渲染：`@wenyan-md/cli`（本机已装，v2.0.11，位于 node 版本目录下）

## 两处已修复的 bug（2026-09-19）

`preflight.py` 与 `publish_wenyan.py` 原先都用 **CWD（当前工作目录）** 解析 frontmatter 里的
`cover: ./cover.png`，而正文图却用 `md.parent`。结果：只要不是站在稿件目录里执行，
必然误报 `cover 缺失或文件不存在` / `ERROR: cover 不存在`——**稿件其实没问题**。

已改为与正文图同一基准（相对稿件所在目录解析）。

## ✅ 凭证状态：已配置（2026-09-21）

`tools/wechat/.env` 已填入 AppID 与 Secret，**实测打通**：

- 取到 access_token（137 字符）→ 凭证有效 **且** 出口 IP 已在白名单
- 09-21 那篇已推进草稿箱（`--theme redwhite --verify` 一次通过，核实图 2 张 / 中文字 2087）

> ⚠️ `.env` 里的 Secret 不要外传，也别把文件内容贴进聊天或提交到仓库。
> 本工作区**没有 git 仓库**，不存在误提交风险。

### ⚠️ 唯一易失点：IP 白名单

脚本用**本机出口 IP** 调微信接口（当前 `112.10.130.200`，浙江电信）。
**家庭宽带 IP 会漂移**（重启光猫/路由器即可能变），漂移后接口报 `40164` / `61004`。

```bash
# 1) 看一眼当前出口 IP（同时确认凭证还在）
python tools/wechat/scripts/publish_wenyan.py --check-credentials

# 2) 把新 IP 加进白名单
#    https://developers.weixin.qq.com/platform/ → 扫码登录 → 我的业务 → 公众号/服务号
#    → 基础信息 → 开发密钥 → IP 白名单「编辑」（原有 IP 不要删，另起一行加）
```

**凭证本身不用动** —— 白名单更新后立即恢复。

### 凭证失效时怎么重新配

> 📖 完整流程见 [`凭证恢复操作流程.md`](./凭证恢复操作流程.md)
> （后台点击路径 / 风险提示 / 错误码对照），约 5 分钟。

凭证来源优先级：**环境变量 > `.env`**；查找顺序 `CWD/.env` → `scripts/.env` → `tools/wechat/.env`。

```bash
python tools/wechat/scripts/publish_wenyan.py --check-credentials   # 自检：掩码 + 出口 IP，不碰微信接口

export WECHAT_APP_ID=wx................      # 临时覆盖（不落盘，安全性更好）
export WECHAT_APP_SECRET=................
python tools/wechat/scripts/publish_wenyan.py <稿件.md> --theme redwhite --verify
```

**缺凭证时的行为**：脚本立刻报错退出（rc=1），**不渲染、不建草稿** ——
"没进草稿箱"这类问题，第一步跑 `--check-credentials` 就能定位。

凭证之外还有一个前置条件：公众号需为**已认证账号**。

## 权限天花板（不变）

本账号 `freepublish/submit`（群发）返回 **48001** —— 微信自 2025-07 起回收个人主体账号的发布类接口。
**自动化的终点就是草稿箱**，粉丝可见的群发必须由账号主在订阅号助手 App / 后台手动点。
**任何交付都不得把「已进草稿箱」写成「已发布 / 已推送」。**
