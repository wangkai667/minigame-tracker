# minigame-tracker

每天抓取小游戏榜单存进 SQLite，计算排名变化和品类份额，再通过 Server酱或 PushPlus 推送到个人微信。
只用 Python 标准库（3.9+），Windows、macOS、Linux 通用。

## 数据源

| key | 榜单 | 来源 |
|---|---|---|
| `wx_bestsell` | 微信畅销榜 | sj.qq.com（应用宝网页版），前 20 |
| `wx_popular` | 微信人气榜 | 同上 |
| `wx_new` | 微信新游榜 | 同上 |
| `wx_hot` | 微信热门榜 | 同上；目前与人气榜相同，默认不抓 |
| `dy_bestsell` | 抖音畅销榜 | momorank.com（第三方，按广告消耗与付费综合排名，每日更新），前 10 |
| `dy_popular` | 抖音热门榜 | 同上 |
| `dy_new` | 抖音新游榜 | 同上 |

应用宝每个榜只渲染前 20 名。MomoRank 免费公开前 10 名，完整 200 名需付费；这里只抓公开部分，
抖音榜单的品类份额因此只反映最头部的 10 款。新增数据源时，在 `tracker/sources.py` 的 `LISTS` 里登记并实现解析，
返回 `{rank, game_id, name, developer, tags}` 列表即可。

## 快速开始

```bash
cp config.example.json config.json   # 填推送 key
python3 -m tracker test-push         # 微信应收到测试消息
python3 -m tracker run               # 抓取 + 日报（周报日再加发周报）
python3 -m tracker --dry-run daily   # 只打印不推送
python3 -m tracker --date 2026-10-29 --dry-run weekly
```

推送 key：
- **Server酱**（默认）：https://sct.ftqq.com 用微信扫码登录，拿到 SendKey（Turbo 版 `SCT...`，Server酱³ 版 `sctp...` 都支持）。免费额度每天 5 条，本工具每天 1～2 条。
- **PushPlus**：https://www.pushplus.plus 拿到 token，把 `provider` 改为 `pushplus`。

也可以不写进文件，改用环境变量 `TRACKER_PUSH_KEY` 提供。

## 定时部署

| 系统 | 命令 | 机制 |
|---|---|---|
| macOS | `./deploy/macos/install.sh 09:30` | launchd LaunchAgent；睡眠时错过的任务在唤醒后补跑 |
| Linux | `./deploy/linux/install.sh 09:30` | systemd 用户定时器，`Persistent=true` |
| Windows | `powershell -ExecutionPolicy Bypass -File deploy\windows\install.ps1 -Time 09:30` | 任务计划程序 |

在闲置的 Mac 上常驻运行：
1. 把整个目录拷到 Mac 上（比如 `~/minigame-tracker`），确认 `python3 --version` 不低于 3.9。
2. 复制并填写 `config.json`，运行 `python3 -m tracker test-push` 确认能收到消息。
3. 运行 `chmod +x deploy/macos/*.sh && ./deploy/macos/install.sh 09:30`。
4. 防止睡眠：`sudo pmset -a sleep 0 disksleep 0`（或在系统设置中关闭自动睡眠）。LaunchAgent 需要该用户处于登录状态，建议开启自动登录。
5. 立即试跑：`launchctl kickstart gui/$(id -u)/com.minigame-tracker`；日志在 `logs/`。
6. 卸载：`./deploy/macos/uninstall.sh`。

没有 systemd 的 Linux 可以改用 crontab：`30 9 * * * cd /path/to/minigame-tracker && python3 -m tracker run`。

## 报告内容

- **日报**：各榜单的新进榜、上升（≥ `rise_threshold` 名）、下降和跌出，以及微信、抖音畅销榜的品类份额。
- **周报**（`weekly_weekday`，1 表示周一）：
  - 微信畅销/人气榜、抖音畅销/热门榜的品类份额周变化（名次加权：榜单共 N 名时，第 1 名记 N 分，最后一名记 1 分）；
  - 本周上升最多的产品；
  - 本周首次出现的游戏，按品类分组；
  - 需要标注品类的游戏。
- 抓取失败时，日报标题会加上"部分抓取失败"并列出原因；页面结构变化也会通过这条推送暴露出来。

## 品类口径

平台标签很粗，比如很多割草、塔防产品只标"休闲益智"，所以品类按以下顺序确定：
`genres.csv` 人工标注 > 同名游戏的抖音品类（MomoRank 给的是单一细分品类，比微信标签准）> 平台标签规则 > 名称关键词规则 > 未分类。
周报会列出未分类的游戏，以及本周新出现、只靠规则分类的游戏。把它们补进 `genres.csv`
（列：`name,genre,theme,note`）后，之后的份额统计就一直按人工标注计算。规则在 `tracker/genres.py`。

## 数据

- `data/tracker.db`：`games` 表（游戏维表、首次和最近上榜日期）、`snapshots` 表（日期 × 榜单 × 名次）。
- 日期按北京时间记录；同一天重复运行会覆盖当天的快照。
- 换机器时，把 `data/` 一起拷过去就能保留历史。
