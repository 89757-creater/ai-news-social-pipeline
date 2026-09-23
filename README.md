# ai-news-social-pipeline

> 把「当天 AI 新闻」加工成「可发布的自媒体成品」的**完整可执行流水线**。
> 一条新闻 → 公众号深度稿 + 抖音长图文，**并自动落到平台的草稿箱 / 发布位**。

这不是一份「写作方法论」文档，而是一套**跑通过的工程链路**：
选题评分 → 事实核查 → 排版渲染 → 程序化出图 → 自动发草稿 / 发布 → 合规审查，
每一环都有脚本、有自检、有踩坑记录。

---

## 它能做什么

```
ai-daily-YYYY-MM-DD.html（当日新闻池）
        │
        ▼
   ① 六维选题评分 ──→ 01_选题评分.md（含「疯传抓手」一格）
        │
        ├──────────────────────────────┬──────────────────────────┐
        ▼                              ▼                          ▼
 ② 公众号深度稿                  ③ 抖音口播稿 + 分镜表        ④ Pillow 出图
 02_公众号稿.md/.html            03_抖音口播稿.md             cover.png / assets/
 md2wx.py → check_html.py       04_抖音分镜表.md             douyin_cover.png
 → preflight.py                      │                       douyin_head.png
        │                            ▼                          │
        │                     douyin/抖音版文案.md              │
        ▼                            │                          │
 草稿箱（自动）                 douyin_post_article.py ←────────┘
                                      │
                                      ▼
                              抖音长图文（自动发布）
```

## 能力边界（★ 请先读这段，避免误期）

| 链路 | 能做 | 做不到 |
|---|---|---|
| 微信公众号 | 自动推**草稿箱**（`draft/add`） | **群发**（`freepublish/submit` → `48001`）。微信自 2025-07 起回收个人主体账号发布类接口权限 |
| 抖音 | 自动发布**长图文**（CDP 直连浏览器） | 「文章」正文**不支持插图**（仅头图 + 封面）；**已发布作品无编辑入口**——配乐/头图/封面必须在发布时设好 |
| 抖音配额 | — | 长图文**每账号每日上限 10 次**，超限返回 `status_code=536` |

> **表述纪律**：进草稿箱 ≠ 已发布。交付时不得把「已进草稿箱」写成「已发布 / 已推送」。

## 环境要求

- **Windows**（脚本按 Windows 路径与微软雅黑字体编写；核心逻辑可移植，路径需改）
- **Python 3.11+**，依赖：`Pillow`、`pyyaml`、`websocket-client`
- **Node.js 22+**（仅公众号渲染需要，`@wenyan-md/cli`）
- **Microsoft Edge**（抖音链占用 `--remote-debugging-port=9222` 的独立 profile）
- 可选：`numpy`（出图边缘溢出自检用）

```bash
pip install Pillow pyyaml websocket-client numpy
npm i -g @wenyan-md/cli
```

## 快速开始

### 1. 铺开工具链

```bash
# 把 skill 内的工具链复制到你的工作区（★ 运行时只用工作区副本）
cp -r <this-repo>/tools  <YOUR_WORKSPACE>/tools
```

**为什么要复制**：本仓库所在的 skill 目录会被 marketplace 更新覆盖，
本地补进去的文件会静默消失（实测过一次）。所以运行时的唯一入口是工作区副本，
本仓库承担的是**可移植分发 + 归档**的角色。

### 2. 配凭证（★ 绝不提交到任何仓库）

```bash
cp tools/wechat/.env.example tools/wechat/.env
# 填入 WECHAT_APP_ID / WECHAT_APP_SECRET
# 还要把调用方出口 IP 加进公众号后台白名单（见 references/wechat-publish.md）
```

抖音不需要密钥文件——登录态存在浏览器 profile `_edge_profile/` 里，手动登录一次即可。

### 3. 跑一轮

```bash
export PATH="/usr/bin:/bin:/usr/local/bin:$PATH"
export PYTHONUTF8=1
PY="<python>"

# 出图
"$PY" scripts/gen_assets_example.py

# 公众号：排版 → 自检 → 推草稿箱
"$PY" scripts/md2wx.py <稿.md> -o <稿.html> --accent "#34527A"
"$PY" scripts/check_html.py <稿.html> --title "<标题>"
"$PY" tools/wechat/scripts/preflight.py <稿.md>
"$PY" tools/wechat/scripts/publish_wenyan.py <稿.md> --theme redwhite --verify

# 抖音：起浏览器 → 填表 → 发布
bash tools/edge_keepalive.sh &          # 用后台常驻方式启动
"$PY" tools/quota_ledger.py             # ★ 发布前查配额
"$PY" tools/douyin_post_article.py --file <抖音版文案.md> --head <头图> --cover <封面>
"$PY" tools/douyin_publish_probe.py     # 点发布并读接口响应
```

## 目录结构

```
├── SKILL.md                      # 主流程（五阶段 + 能力边界 + 红线）
├── references/
│   ├── controversy-scoring.md    # 六维评分细则
│   ├── fact-check-rules.md       # 事实核查 8 条硬规则
│   ├── platform-specs.md         # 平台格式硬约束
│   ├── writing-calibration.md    # 疯传六原则落地写法
│   ├── wechat-publish.md         # 公众号链路 + 错误码 + 凭证恢复
│   ├── douyin-publish.md         # 抖音 CDP 链路 + 配额 + 配乐
│   ├── troubleshooting.md        # 故障排查速查表
│   └── pitfalls.md               # 已踩坑清单（设计教训）
├── scripts/                      # 通用脚本（跨选题复用）
│   ├── md2wx.py                  # Markdown → 微信兼容 HTML
│   ├── check_html.py             # HTML 排版自检
│   ├── check_douyin_sensitive.py # 敏感词检测（带阳性对照）
│   ├── gen_assets_example.py     # Pillow 出图模板（含双自检）
│   ├── gen_cover_pillow.py       # 公众号封面
│   └── gen_diagrams_pillow.py    # 正文配图
├── tools/                        # 平台链路工具（可移植副本）
│   ├── edge_keepalive.sh         # 保活拉起带调试端口的 Edge
│   ├── cdp_read.py               # CDP 底座
│   ├── douyin_*.py               # 抖音生产/维护/诊断链
│   ├── quota_ledger.py           # 发布配额台账 + 删前闸门
│   └── wechat/                   # 公众号链（preflight / publish_wenyan / themes）
└── examples/2026-09-23/          # 一份完整实跑产出，可直接对照格式
```

## 设计原则

1. **读接口，不读页面。** 发布类动作的成败只以接口响应为准——页面文案会骗你（配额 toast 只闪 0.6 秒）。
2. **空跑比报错更危险。** 任何检测器的「0 命中」结论都必须先证明它没空跑（阳性对照）。
3. **人脑估算不可靠。** 色相、字节数、字数、像素一律信脚本输出。
4. **硬编码是便携性的敌人。** 凡是「明天早上还会变」的东西都必须参数化。
5. **降级要明说。** 缺凭证、缺额度、缺信源时降级交付并讲清落到哪一步——静默跳过才是失败。
6. **真实比热闹重要。** 素材撑不起来就标注缺口，不换选题、不编案例凑。

## 已知局限

- 「抖音先发新的、成功后再删旧的」安全顺序**尚未实现**。
- `quota_ledger.py` 只记录本工具的成功次数，手工发布看不到 → 余量只是**下界**。
- 后朋克配乐在抖音曲库里基本不可得（存量 2 条、均 0 人使用）。
- `tools/douyin_fill.py` 等脚本内有硬编码工作区路径，换机器需改。
- 抖音链依赖页面结构，平台改版时需要修选择器。

## License

MIT
