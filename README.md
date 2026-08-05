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

- `backend/mcp_client.py` — 直连 Luci MCP HTTP 端点的最小 JSON-RPC 客户端
- `backend/detect.py` — 直播检测逻辑
- `backend/retrieval.py` — 确定性抓取：分块拉 vision（`aggregate_range`），关键词扫 audio
  （`audio_transcript_search`，用常见字做 sweep 保证覆盖率），合并成按时间排序的 JSONL，
  外加从 vision 文本里抽取的圈速/差距数值序列
- `backend/analysis.py` — A/B/C/D 四个功能调 `claude -p`（headless），E 是纯结构化数据
- `backend/app.py` — FastAPI，含内置后台检测轮询任务（不依赖 openclaw / 云端 cron）
- `frontend/index.html` — 单页前端，状态条 + 补看输入框 + 总结/What-if 按钮 + 可点击时间轴 +
  Chart.js 折线图

## 已知限制 / 下一步

- ~~检测规则目前只认 bilibili.com~~ 已在 Phase 4 放开，只要求画面里出现 `LAP n/70` 格式文字，不
  限定转播平台
- 胎况色块图标识别（多模态兜底）还没写，目前靠 audio + 平台字幕覆盖，真的需要时再补
  `vision_read.py`
- 后台检测只在你手动跑起 `uvicorn` 之后才生效，不是开机自启
- 已用 Milestone 0 的真实 8 分钟录制数据跑通全链路（94 条 vision + 81 条 audio 合并，
  `catchup` 输出的赛后小结正确综合了两条流的信息，包括维斯塔潘车辆故障、阿隆索调查这类
  只在音频里出现的细节）——下一步是找一场完整/更长的比赛实测 Milestone 1（真正端到端跑
  一整场，检测自动触发+实时补看+赛后总结+时间轴+图表全部试一遍）
