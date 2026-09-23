# 公众号发布链路（自动进草稿箱）

## 链路总览

```
02_公众号稿.md
   ├─ cover.png ──────────┐
   └─ assets/*.png ───┐   │
                      ↓   ↓
        preflight.py（字节/图数/文件校验）
                      ↓
        publish_wenyan.py --theme redwhite --verify
                      ↓
        ① 上传封面 → 得 thumb_media_id
        ② 上传正文图 → 替换为微信 CDN 链接
        ③ wenyan render（md → 微信 HTML）
        ④ draft/add  ← ★ 天花板在这里
        ⑤ --verify 回读草稿，核对图数与中文字数
                      ↓
                  草稿箱（粉丝不可见）
```

## 三条件（缺一都发不出去）

| 条件 | 本机状态 | 缺失时的表现 |
|---|---|---|
| 已认证公众号 | ✅ | — |
| `WECHAT_APP_ID` / `WECHAT_APP_SECRET` | ✅ 在 `<WS>/tools/wechat/.env` | 脚本在**渲染之前**就 rc=1 退出 → **没生成草稿** |
| 出口 IP 在后台白名单内 | ✅（会漂移） | API 返回 `40164` |

> ⚠️ 凭证缺失时准确说法是「**没生成草稿**」，不是「生成了但没进草稿箱」——
> 脚本第一步查环境变量，缺失即退出，根本没走到渲染。

## 脚本

### 1. preflight.py —— 发布前自检

```bash
"$PY" "$WS/tools/wechat/scripts/preflight.py" <稿.md> [--min-images 2]
```

校验项：`title ≤64B`、`description ≤120B`、`author ≤8B`、
封面存在、正文图 ≥2 张、图片引用文件真实存在、无 SVG。

**cover 路径按「稿件所在目录」解析**（2026-09-19 修正）。
旧版按 **CWD** 解析，不在稿件目录执行就必然误报「cover 不存在」——
**症状极像稿件缺封面，实际是脚本 bug**。现在统一 `md.parent` 为基准。

### 2. publish_wenyan.py —— 渲染 + 发布

```bash
# 正式发 + 回读核实（打印 media_id）
"$PY" "$WS/tools/wechat/scripts/publish_wenyan.py" <稿.md> --theme redwhite --verify

# 诊断（★ 降级时的第一动作）
"$PY" "$WS/tools/wechat/scripts/publish_wenyan.py" --check-credentials

# 删草稿（发错了清掉，别让后台堆同名稿）
"$PY" "$WS/tools/wechat/scripts/publish_wenyan.py" --delete-draft <media_id>

# 试跑不提交
"$PY" "$WS/tools/wechat/scripts/publish_wenyan.py" <稿.md> --theme redwhite --dry-run
```

`--check-credentials` **不碰微信接口**，只打印：掩码后的 AppID/Secret、`.env` 载入路径、
就绪状态、以及**实时出口 IP**。一条命令就能把「密钥问题」和「IP 问题」分开——
这是最省时间的诊断入口，降级时先跑它，别猜。

本机已注册主题：`redwhite`（默认）/ `green` / `blue` / `gray`。
渲染依赖全局 `@wenyan-md/cli`（本机 v2.0.11 已装）。

## 错误码对照

| 码 | 含义 | 处置 |
|---|---|---|
| `40164` / `61004` | 出口 IP 不在白名单 | 查 `https://ipinfo.io/ip`，让用户加白；**本轮只交付 HTML**，不要反复重试 |
| `40125` | **AppSecret 无效**（平台侧重置即旧值作废） | 去 `/platform/` 重置 Secret → 写回 `.env` → 重跑。**本地 `.env` 看不出任何异常** |
| `40243` | AppSecret 被冻结 | 平台后台解冻 |
| `40013` | AppID 无效 | 核对 AppID |
| `48001` | 无权限 | 群发类接口已回收，改不了；降级为交付 HTML |
| `45009` | 接口调用频次超限 | 等额度重置 |

⚠️ **两个易失点别搞混**（2026-09-22 更新，此前只记了 IP 一个）：
① IP 白名单（家庭宽带出口 IP 会漂移）→ `40164` / `61004`；
② AppSecret 失效 → `40125`。
**用 `--check-credentials` 一次分清**：报 40125 是密钥问题，报 40164/61004 是 IP 问题。

## 凭证恢复步骤

去 **`https://developers.weixin.qq.com/platform/`**（路径**必须带 `/platform/`**）：
我的业务 → 公众号 → 基础信息 → 开发密钥 → 此处可**同时**改 AppSecret 与 IP 白名单。

**别走这两条错路**（2026-09-21 已踩）：
- 裸域名 `developers.weixin.qq.com` 是开放社区资讯站，没有「我的业务」；
- 老后台 `mp.weixin.qq.com → 设置与开发`，官方已整体迁移。

## 权限天花板（硬约束，不是配置问题）

2026-09-14 实测：

| 接口 | 状态 |
|---|---|
| `draft/add`、`draft/delete`、`draft/batchget` | ✅ 可用 |
| `material/*` | ✅ 可用 |
| `freepublish/submit`（群发） | ❌ `48001` |
| `freepublish/batchget` | ❌ `48001` |
| `user/get` | ❌ `48001` |
| 客服消息 | ❌ `48001` |

微信自 **2025-07** 起回收了**个人主体**账号的「发布类」接口权限。
**所以自动化的天花板就是草稿箱**，粉丝可见的群发必须由用户在订阅号助手 App
或公众号后台手点一下。

**禁止**把「已进草稿箱」表述为「已发布 / 已推送」。

## 其它实操细节

- **一稿只推一次**。要改封面就改完再推，否则后台堆同名草稿，用户会以为「封面没换上」。
- 后台**封面预览有缓存**：用户反馈「没换上」先让其强刷（Ctrl+Shift+R）或开隐身模式。
- 每次推送记录**草稿 media_id 与封面 media_id**，写进当日 memory。
- 正文图必须 **PNG/JPG**；**SVG 会被微信拒收**（且本机出不来 SVG，见 `pitfalls.md`）。
