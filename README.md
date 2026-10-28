# zhufeng-data

「珠峰工作台」的数据仓：GitHub 热榜的每日抓取、中文简介、30 天历史。
公开仓库 —— 工作台（`Zfeng08/work-buddy`）的前端直接读这里的 raw 文件。

```
data/trends.json          当日榜单 + 纵向指标（streak / is_new / stars_7d）
data/trends_history.json  最近 30 天快照，供 30 天曲线与「连续在榜」
scripts/fetch_trends.py   抓取 + 翻译 + 历史累积
glossary.json             翻译术语白名单
.github/workflows/        每天 09:30（北京时间）自动跑
```

## 数据从哪来

- 榜单：`https://github.com/trending`（顺带抓 python / typescript / javascript / rust / go 五个语言榜）
- 简介翻译：Google 翻译 → MyMemory 兜底，都失败就保留英文原文
- 历史：每天追加一条快照，滚动保留 30 天

## 术语白名单

`glossary.json` 里 `keep` 列表中的词，在翻译前会被替换成占位符、翻完再还原，
避免 ElevenLabs、Claude Code、Cursor 这类专有名词被机器翻译揉碎。
加词直接改这个文件，下一次采集生效。

```json
{ "keep": ["ElevenLabs", "Claude Code", "MCP", "RAG"] }
```

匹配规则：纯 ASCII 词按「整词 + 忽略大小写」匹配（`Agent` 不会命中 `agentic` 里的片段），
含空格或符号的词按整串匹配。

## 手动跑

```bash
pip install requests
python scripts/fetch_trends.py
```

或者 Actions → fetch-trends → Run workflow。

## 工作台怎么读

```js
https://raw.githubusercontent.com/Zfeng08/zhufeng-data/main/data/trends.json
https://raw.githubusercontent.com/Zfeng08/zhufeng-data/main/data/trends_history.json
```

raw 地址带 `Access-Control-Allow-Origin: *`，静态页面可以直接 fetch，不需要 token。
