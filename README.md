# F1 直播双流分析

验证"Luci screen(OCR) + audio(ASR) 双流数据 + LLM 分析"这套方法论的试验田。计划文档：
`~/.claude/plans/plan-f1-luci-wild-puffin.md`

## 运行

**首次安装**：先确保 [Luci](https://luci.so)（或你自己的 `screen-memory` MCP）已经装好并在跑，
打开了 ASR；然后跑：

```bash
./setup.sh
```

自动装 Python 依赖（`uv sync`）、生成 Web Push 用的 VAPID 密钥对、探测 Luci 是否连得上、引导你
配置 RAG chatbot 的 Voyage key（可选，跳过也能用，只是 chatbot 会退化成纯联网搜索）。装不了的
那几步（Luci 本体、Voyage 账号注册、浏览器通知权限）脚本会打印清楚下一步该做什么，不会假装帮
你做了。具体每个变量是什么、为什么有些能自动填有些不能，见 [`.env.example`](.env.example)。

跑完脚本会提示你启动命令：

```bash
uv run uvicorn app:app --app-dir backend --reload --port 8800
```

打开 http://127.0.0.1:8800 ，首页有个「开启比赛提醒」按钮，点一下授权浏览器通知（只需要做一次，
之后每场比赛都会自动推送，不用再开着标签页）。

**已经装过、只是重开电脑/换目录**：`.env` 还在的话直接跑启动命令就行，不用重新走 `setup.sh`。

后台每 90 秒检测一次画面里是否出现 `LAP n/70` 格式文字（不限定平台，B站/YouTube 等转播源都认），
检测到自动开始录 session；结束时手动点网站上的「结束本场」。

## 目录

后端（`backend/`，FastAPI，一人一进程，无多租户/无鉴权，见 [`CURRENT-STATUS.md`](CURRENT-STATUS.md)）：

- `mcp_client.py` — 直连 Luci MCP HTTP 端点的最小 JSON-RPC 客户端
- `detect.py` — 直播检测逻辑（画面里认 `LAP n/70` 格式文字，不限定转播平台）
- `retrieval.py` — 确定性抓取：分块拉 vision（`aggregate_range`），关键词扫 audio
  （`audio_transcript_search`），合并成按时间排序的 JSONL，外加从 vision 文本里抽取的
  圈速/差距数值序列
- `analysis.py` — 调 `claude -p`（headless）生成事件短评/赛后总结/What-if 等，事件每
  5 分钟刷新一次；RAG 聊天走独立的流式后台任务（`start_chat_run`），支持断线重连续播
- `app.py` — FastAPI 入口，含内置后台检测轮询任务（不依赖 openclaw / 云端 cron）
- `push.py` — 真实浏览器推送（VAPID + Service Worker），零标签页也能收到通知
- `rag.py` — 赛事问答的检索增强层：Voyage embeddings 建索引 + `claude -p` 兜底联网搜索
- `sync_snapshot.py` — 把最新状态同步到 Cloudflare KV，供 `worker/` 的离线兜底页使用
- `watchdog.py` — 独立跑的看门狗，backend/隧道/同步任一挂了就推送报警
- `tests/` — pytest（`uv run pytest`），覆盖日历自动命名、断线去重、事件选手归属这几处
  查出过真 bug 的纯逻辑

前端（`frontend/`，静态 HTML/JS，同源；`module-*.html`/`chat-mockup-*.html`/
`design-directions.html` 是设计预览稿，不是站点本体）：

- `home.html` — 首页，比赛列表 + 直播状态
- `index.html` — 单场比赛页，状态条 + 补看输入框 + 总结/What-if + 可点击时间轴 + 图表
- `chat.html` — RAG 聊天独立页
- `settings.html` — 通知偏好设置

其他：

- `worker/` — 独立的 Cloudflare Worker 子项目，把 f1lightout.com 反代到本机隧道，本机离线
  时改用 `sync_snapshot.py` 同步过去的 KV 快照兜底（详见 `CURRENT-STATUS.md` 架构图）
- `setup.sh` — 一键装依赖/生成 VAPID 密钥/探测 Luci 连通性/引导配置 Voyage key

## 已知限制

（完整、随时更新的版本见 [`CURRENT-STATUS.md`](CURRENT-STATUS.md) 的「Known constraints」——
这里只列几条最容易踩的坑）

- 一个后端进程只有一份全局 `state`，同一时间只能追踪一场比赛，也没有多用户概念——每个人
  跑自己的一整套本地服务（`./setup.sh`），不是共享一个服务器
- `backend/` 所有接口都不带鉴权，默认只信任本机访问
- Luci 的 `app` 字段经常是 null 不可靠，检测/事件逻辑全靠画面 OCR 文字，不依赖它
- 胎况色块图标识别（多模态兜底）还没写，目前靠 audio + 平台字幕覆盖，真的需要时再补
- 多用户 portal（让朋友登录网站看自己的比赛，不用自己搭一整套）还只是设计，没开始写，
  卡在账号机制怎么选，见 [`TODO.md`](TODO.md)
