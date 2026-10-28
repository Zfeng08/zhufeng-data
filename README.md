# work-buddy-trends

`Zfeng08/work-buddy` 的 **GitHub 热榜长期存档**。私有仓库，只存数据，不跑站点。

## 为什么单独一个仓库

公开站点的历史数据必须放在公开仓库里才能被浏览器读到（静态站点拿不到私有仓库的读权限，
除非把 token 塞进前端，那是泄露）。所以这里的分工是：

- **公开仓库** `work-buddy/data/trends*.json` —— 站点实际读取的镜像，保留最近 30 天
- **本仓库** —— 长期存档，按天保留快照，`history.json` 滚动 365 天

## 结构

```
snapshots/2026-10-28.json   # 当日完整榜单（含中文简介）
history.json                # 汇总历史：日期 + 每个仓库的 stars / stars_today
```

`history.json` 里一天的形状：

```json
{
  "days": [
    {
      "date": "2026-10-28",
      "repos": [
        { "full_name": "hmjz100/LinkSwift", "stars": 33477, "stars_today": 3209,
          "language": "JavaScript", "description_zh": "…" }
      ]
    }
  ]
}
```

## 工作流

`.github/workflows/archive.yml` 每天 10:20（北京时间）拉取公开仓库的
`data/trends.json`，写入当日快照并更新 `history.json`，然后提交。
公开仓库是 public，读它不需要任何 token，所以这里**没有配置任何 secret**。

也可以手动触发：Actions → archive → Run workflow。

## 和站点指标的关系

站点的「连续在榜 N 天 / 新上榜」用的是公开仓库里的 `data/trends_history.json`（30 天窗口），
不是本仓库。本仓库的价值是把窗口拉长到一年，方便以后回看某一周到底什么在涨。
