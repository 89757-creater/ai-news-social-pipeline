# 抖音发布链路（CDP 直连 Edge，自动发长图文）

## 为什么是 CDP

抖音**没有官方发布 API**。`agent-browser` 在本机**不可用**（装不了 Chromium）。
唯一可行路径：直连**本机已登录的 Edge**——用 Chrome DevTools Protocol 读页面、点真实鼠标、
填受控输入、上传文件。底座是 `tools/cdp_read.py`，细则见技能 `cdp-browser-automation`。

**优势**：复用用户已登录的 profile，不碰账号密码；操作的是真实浏览器，反检测成本低。

## 架构

```
Edge（--remote-debugging-port=9222，用户数据目录 <WS>/_edge_profile）
   ↑ CDP over HTTP/WebSocket
   │
tools/cdp_read.py  ← 所有脚本的底座（标签收敛、元素等待、真实点击、受控输入）
   │
   ├─ 生产链：douyin_fill.py → douyin_upload2.py → douyin_music_pick.py
   │           → douyin_topic.py → douyin_post_article.py → douyin_publish_probe.py
   ├─ 维护链：douyin_delete.py / republish_one.py / quota_ledger.py
   └─ 诊断链：state_check.py / editor_probe.py / dump_manage.py
```

## 启动

```bash
# ★ 必须 run_in_background（前台 msedge 会被沙箱收割）
bash "$WS/tools/edge_keepalive.sh"

# 探活（--noproxy 必须加，否则走代理连不上）
curl -s --noproxy '*' --max-time 3 http://127.0.0.1:9222/json/version
```

`edge_keepalive.sh` 用 `while true` 常驻：端口不通就重拉 Edge，通了就 sleep 5。
入口页 `https://creator.douyin.com/creator-micro/content/post/article?default-tab=5`。

- 账号：本机已登录的抖音创作者账号（**账号 ID 不写入本仓库**）。
  登录态在独立 profile `_edge_profile/` 里——手动登录一次即可，之后脚本复用该会话。
- ⚠️ **浏览器重启后编辑器草稿会丢**（实测变空白）→ 不必慌，
  稿件可信来源是**本地文件** `social/<date>/douyin/抖音版文案.md`，重填一次即通。

## 生产链逐步说明

### 1. douyin_fill.py —— 填标题/摘要/正文

```bash
"$PY" "$WS/tools/douyin_fill.py" --file "$WS/social/<date>/douyin/抖音版文案.md" --clear
```

- **必须加 `--clear`**：脚本默认**末尾追加**，重填会越填越长。
  `--clear` 先 `selectNodeContents` + `execCommand('delete')` 再插入，幂等。
- 已内置清洗：剥 `**`、去 `###`、去 `>` 引用符、`- ` 转圆点、
  **去掉 markdown 水平线 `---`**（不带的话会作为正文文字出现在文章末尾，很显眼）。
- 正文取 `## 正文` 与下一个 `##` 之间的内容 → **分隔线不要紧贴正文段尾**。
- ⚠️ 要求源文件用 `## 标题` / `## 摘要` / `## 正文` 二级标题分节；
  写成 `**标题**` 粗体行会报 `IndexError: list index out of range`。
- 脚本内有硬编码默认路径（`WS`、`DOC`）→ **换工作区要改**，所以默认显式传 `--file`。

### 2. douyin_upload2.py —— 头图 + 封面

```bash
"$PY" "$WS/tools/douyin_upload2.py" --head "$WS/social/<date>/douyin/douyin_head.png" \
                                    --cover "$WS/social/<date>/douyin/douyin_cover.png"
```

改版要点（易踩）：
- 头图入口文案是「**点击替换图片**」（不是「上传头图」）。
- 头图弹窗点「**确定**」；封面弹窗点「**完成**」（两个按钮文案不一样）。
- 成功提示**0.6 秒**就消失，别靠它判断。
- 编辑器右侧「手机预览」会遮挡表单入口 → 脚本统一用 DOM `.click()` 绕过。

### 3. douyin_music_pick.py —— 配乐（唯一入口）

```bash
"$PY" "$WS/tools/douyin_music_pick.py" --search "r&b loop"
```

配乐规则（用户 2026-09-21 指定，长期有效）：
- 原话「不用纯音乐也可以，但风格要求 rnb、爵士、后朋克」
  → ① 不再限定「纯音乐」页签；② 优先级 **R&B / 爵士 / 后朋克**。
- 面板**没有风格类页签** → 只能走 `input[placeholder="搜索音乐"]`。
- 实测存量：**爵士 11 条、R&B 31 条**；⚠️ **后朋克基本不可得**
  （仅 2 条真命中，且均 0 人使用；其余是「蒸汽朋克 / 赛博朋克」误命中）
  —— 这是**曲库问题，缺口如实标注，不拿赛博朋克冒充**。
- 常用曲：`r&b loop`、`乌鸦的爵士咖啡馆`、`夜上海`。

### 4. douyin_topic.py —— 话题（≤5 个）

```bash
"$PY" "$WS/tools/douyin_topic.py" --topics "话题1" "话题2" ...
```

- 上限 **5 个**，加到第 6 个会被拒。
- ⚠️ **重跑前先读 `topicCount`**：若已 5/5，别重跑全链——
  实测第二次运行时「添加话题」弹窗连开 5 次都打不开（幂等性缺陷）。
  这种情况直接用 `douyin_publish_probe.py` 点发布即可。

### 5. douyin_post_article.py —— 全链编排

```bash
"$PY" "$WS/tools/douyin_post_article.py" --file <文案.md> --head <头图> --cover <封面> \
      --topics "..." "..." [--search-music "r&b loop"]
```

**默认停在发布前**——发布是不可逆的公开动作，须显式加开关。

### 6. douyin_publish_probe.py —— 点发布并判定结果

```bash
"$PY" "$WS/tools/douyin_publish_probe.py"
```

- 点「发布」按钮前会 `scrollIntoView`（发布按钮常在视口外，`y=1005 > vpH=809`）。
- **判定成功的唯一依据：读 `create_v2` 接口响应**（`{"status":200,...}` → `status_code=0`）。
  **不要读页面文案**——点发布后编辑器标签会自动跳到 `/content/manage`，
  页面文案会误导成「结果不明」。

## ★ 发布配额：最容易吃大亏的约束

**「长图文」（文章体裁）每账号每日上限 10 次。**

超限时服务端返回 `status_code=536`、报文「今日发布10次长图文，已达上限」，
而**页面只闪 0.6 秒的 toast** —— sleep 后再读什么都读不到，会误判「结果不明」。

与「删旧重发」叠加就是事故：2026-09-18 因先删旧作、重发被配额拒，
**静默丢了一篇**（作品数 5 → 4）。原因是文章发布后**没有编辑入口**，
换配乐/换封面只能删了重发。

### 三条纪律

1. **删前先过闸门**：`"$PY" "$WS/tools/quota_ledger.py"`
2. **发布结果一律读接口响应**，不读页面文案。
3. **见 `rc=4` 立刻停手**（服务端已拒，重试无效），等额度 `00:00` 重置后
   用 `--no-delete` 补发。

### 台账的局限（诚实说明）

`quota_ledger.py` 只记录**本工具**成功发布的次数。手工发的、别的脚本发的，它看不到。
所以它是**下界**，不能证明 `10 - used` 还真有余量。它唯一的确定性作用是：
**当它自己都已经数到 10 时，坚决拦住删除。**

⏳ 已知未实现：「**先发新的、成功后再删旧的**」这个安全顺序**目前没有**。

## 产品边界（改不了的平台设计）

1. 抖音「文章」**正文不支持插图**——只有**头图 + 封面**两个图位。
2. **已发布作品无「编辑」入口** → **配乐、头图、封面必须在发布那一刻设好**，事后补不了。
3. 话题 ≤5 个。

## 风控与降级

点「发布」**可能**触发短信验证风控（2026-09-15 触发、09-16 直接成功，**非必然**）。

处置顺序：
1. 先正常点；真弹框再降级。
2. **不要填验证码**——收不到，乱填会升级为扫码风控。
3. 取消弹窗 → 点「暂存离开」存草稿 → 交付写明「已存草稿，需用户手机端过验证」。
4. **禁止把「已存草稿」说成「已发布」**。
