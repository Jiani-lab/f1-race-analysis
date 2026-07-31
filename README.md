# F1 直播双流分析

验证"Luci screen(OCR) + audio(ASR) 双流数据 + LLM 分析"这套方法论的试验田。计划文档：
`~/.claude/plans/plan-f1-luci-wild-puffin.md`

## 运行

前提：Luci 正在跑（`screen-memory` MCP 在 `http://127.0.0.1:8765`），且已经打开 ASR。

```bash
uv run uvicorn app:app --app-dir backend --reload --port 8800
```

打开 http://127.0.0.1:8800 。后台每 90 秒检测一次是否在看 B站 F1 直播（`browserUrl` 含
`bilibili.com` 且画面里出现 `LAP n/70` 格式文字），检测到自动开始录 session；结束时手动点
网站上的「结束本场」。

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

- 检测规则目前只认 bilibili.com，换平台看比赛要改 `detect.py`
- 胎况色块图标识别（多模态兜底）还没写，目前靠 audio + 平台字幕覆盖，真的需要时再补
  `vision_read.py`
- 后台检测只在你手动跑起 `uvicorn` 之后才生效，不是开机自启
- 已用 Milestone 0 的真实 8 分钟录制数据跑通全链路（94 条 vision + 81 条 audio 合并，
  `catchup` 输出的赛后小结正确综合了两条流的信息，包括维斯塔潘车辆故障、阿隆索调查这类
  只在音频里出现的细节）——下一步是找一场完整/更长的比赛实测 Milestone 1（真正端到端跑
  一整场，检测自动触发+实时补看+赛后总结+时间轴+图表全部试一遍）
