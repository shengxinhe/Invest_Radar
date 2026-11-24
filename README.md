# 投资雷达 · README

个人 AI 投研终端。本地抓数据 → SQLite → API 服务 → PWA / 微信推送。

> **当前状态：1.0 全功能交付完毕，2.0 升级已启动。**
> 2.0 施工单：[PLAN-2.0.md](PLAN-2.0.md) ｜ 审计报告：[audit.md](audit.md)

---

## 当前进度（2.0）

| 阶段 | 状态 | 说明 |
|---|---|---|
| **M0 审计与备份** | ✅ | 8 项问题全部属实并留证；DB 回滚点 `radar_M0_20261117_190829.db`；功能基线冻结 |
| **M1 安全与关键 Bug** | ✅ | 认证+登录页 / CORS 收敛 / 127.0.0.1 监听 / feed 复合 keyset 分页(7测试) / FTS trigram+6触发器 / 新鲜度体系 / 备份恢复演练 ｜ [报告](M1-REPORT.md) |
| **M2 AI 架构** | ✅ | httpx 异步(并发验证) / 缓存版本化(thesis+prompt) / 七段结构 / 取消强制概率 / 注入防护 / SSE 统一协议 / 降噪改口径 ｜ [报告](M2-REPORT.md) |
| **M3 移动端设计系统** | ✅ | CSS 三层拆分(去 11 个重复变量) / 首页驾驶舱(真实大盘+今日重点+AI研究建议) / 组件库 / 搜索竞态保护 / FeedList 重写 / Session 落库 ｜ [报告](M3-REPORT.md) |
| **M4 详情与资讯管理** | ✅ | 详情五区重构(行业/市场/四源状态) / 资讯六态管理 / thesis 历史版本(diff+原因) ｜ [报告](M4-REPORT.md) |
| **M5 实时行情与推送** | ✅ | 共享轮询(3连接仍1次) / SSE 生命周期+退避重连 / 三级通知(P1即刻·P2汇总·P3入库)+72h去重+配额 ｜ [报告](M5-REPORT.md) |
| **M6 长期研究** | ✅ | 研究笔记CRUD+搜索 / 报告归档(晨报·复盘·Markdown导出) / 月度复盘(严格时间序) ｜ [报告](M6-REPORT.md) |
| **M7 最终验收** | ✅ | 全链路 31 项检查全过 / 兼容端点 / 个股复盘入口 / 辩论归档 / 运维修复 ｜ [OPTIMIZATION_REPORT](OPTIMIZATION_REPORT.md) · [CHANGELOG](CHANGELOG.md) |

**2.0 升级完成。** 审计 8 项问题全部闭环，最终验收 31/31 通过。

## 日常运维

```powershell
# 一键体检（31 项：安全/数据库/API/分页/行情/AI/备份/PWA/运维）
python tests/test_acceptance.py
```

| 项 | 机制 |
|---|---|
登录口令 | `**（已移除）**`（存 .env 的 scrypt 哈希，可改） |
行情明细 | 保留 7 天，每 6 小时自动清理；每日收盘快照永久保留（仅工作日） |
WAL | 随清理自动 checkpoint，防膨胀 |
备份 | 系统计划任务每日 20:00，保留 14 份，含完整性校验 |
启动 | `启动服务.bat`（已含端口占用自动清理） |

### 1.0 历史里程碑（全部完成）

| 里程碑 | 说明 |
|---|---|
| 1.0-M0 重构为库 | store.py + sync.py + CLI 走 DB，回归通过 |
| 1.0-M1 服务化+手机 | FastAPI + PWA + Tailscale HTTPS 固定域名 |
| 1.0-M2 全市场搜索 | 5580 只，三路搜索，懒抓取 ~1s |
| 1.0-M3 词条 AI 解读 | DeepSeek 流式 + 缓存 + 追问 + 批量 |
| 1.0-M4 微信推送 | watcher + DSH schedule 双向同步（盘中告警 + 晨报） |
| 1.0-UI-KLINE | 液态玻璃 4 tab + klinecharts 9 周期 |
| 1.0-M5 打磨 | 全局 RAG / 在线改 thesis / 成本面板 |

详见 [PLAN.md](PLAN.md)、[PLAN-UI-KLINE.md]（UI 与 K线施工单）。

### 接入方式

```
https://rancho.duiker-ling.ts.net   （Tailnet 内，手机装 Tailscale App）
http://127.0.0.1:8000               （本机）
```

微信推送通道：DSH Desktop「IM 机器人」→ 微信机器人私聊目标 → 会话双向同步开关。
定时任务：交易日 9:35–14:35 每小时风险轮询；交易日 8:30 AI 晨报。

### K线数据源（全部前复权）

| 周期 | 源 | 缓存 TTL |
|---|---|---|
分时 / 5日 | 腾讯 minute/query | 60s / 30min |
日 / 周 / 月 | 腾讯 fqkline | 6h |
5/15/30/60分 | 东财 push2his（em_get 节流） | 5min |

---

## 快速开始

```powershell
# 装依赖
pip install akshare requests pandas mootdx stockstats pypinyin

# 生成看板
python -m invest_radar --board

# 打开
start out\dashboard.html
```

或双击 `更新看板.bat`。

---

## 目录结构

```
money/
├── PLAN.md                   设计文档 + 施工单
├── 使用说明.md                看板使用教程
├── 更新看板.bat
├── invest_radar/
│   ├── config.py             配置（监控清单、关键词、阈值）
│   ├── fetcher.py            数据抓取（多源降级 + 限流）
│   ├── analyzer.py           分析打分（趋势/估值/风险标记）
│   ├── store.py      ← M0    SQLite 存储层
│   ├── sync.py       ← M0    抓取 → 入库（适配层）
│   ├── pyutil.py     ← M0    拼音
│   ├── dashboard.py          静态看板生成
│   ├── reporter.py           文本报告 + 推送
│   └── __main__.py           CLI 入口
├── out/
│   ├── dashboard.html        看板（双击打开）
│   └── radar_*.md            历史报告
└── data/
    ├── radar.db      ← M0    主库
    └── radar_*.json          结构化快照
```

---

## M0 做了什么

### 1. 存储层 `store.py`

SQLite + FTS5，8 张表（`stock` / `watch` / `entry` / `entry_ai` / `chat` / `quote` / `fetch_log` / `meta`）。

关键 API：
```python
store.init()                          # 建表 + 首次导入 WATCHLIST
store.search_stock("zjln")            # 代码/名称/拼音 三路搜索
store.upsert_entry(...)               # 词条去重靠 id=sha1(code|type|source_id)
store.list_entries(code, "notice")    # 按类型取词条
store.need_refresh("notice:000060")   # TTL 判断
store.stats()                         # 库统计
```

**TTL 策略**：

| 数据 | TTL |
|---|---|
| 全市场股票列表 | 24h |
| 行情 | 交易时段 30s / 非交易 1h |
| 公告、互动易 | 15min |
| 新闻 | 30min |
| 研报、筹码 | 6h |

### 2. 适配层 `sync.py`

把 `fetcher` 的原始数据转成 `entry` 记录入库。**level 判定沿用 analyzer 规则**，保证标红标绿行为不变。

```python
sync.sync_all(code, stock)     # 全量抓取 + 入库，返回新增数
sync.sync_light(code)          # 只抓行情，未关注的票用
```

### 3. fetcher 改造

- `_log()` 改为受 `config.DEBUG` 控制（默认静默）
- `collect(stock, progress=None)` 加进度回调，服务端可推进度
- 新增 `collect_light(code)` 轻量抓取
- **业务逻辑一行没动**

### 4. CLI 走 DB

`config.WATCHLIST` 只在首次启动时导入 `watch` 表，之后以 DB 为准。

---

## 回归验收结果

```
$ python -m invest_radar --no-save

>>> 600251 新疆冠农
  行情... OK    K线... OK
  公告... OK 7条    新闻... OK 9条
  研报... OK 1篇    互动易... OK 0条
  解禁... OK 1批    两融... OK 5条   股东... OK 1期

>>> 000060 中金岭南
  行情... OK    K线... OK
  公告... OK 3条    新闻... OK 6条
  研报... OK 10篇   互动易... OK 15条
  解禁... OK 2批    两融... OK 5条   股东... OK 1期

入库新增: notice+10  news+15  report+11  qa+15
库统计: {'stocks': 2, 'watch': 2, 'entries': 51, 'entry_ai': 0, 'quotes': 4, 'db_mb': 0.15}
```

**报告正文与改造前逐行一致**（仅进度显示粒度变化：原来"解禁/两融/股东"合并一行，现在拆成三行）。

搜索验证：
```
000060    -> [('000060', '中金岭南')]
岭南       -> [('000060', '中金岭南')]
zjln      -> [('000060', '中金岭南')]
zhongjin  -> [('000060', '中金岭南')]
新疆       -> [('600251', '新疆冠农')]
```

---

## 命令

```powershell
python -m invest_radar                 # 文本报告
python -m invest_radar --no-save       # 不存档
python -m invest_radar --board         # 生成看板
python -m invest_radar --open          # 生成并打开看板
python -m invest_radar --codes 600251  # 只跑指定
python -m invest_radar.store           # 查看库统计
```

---

## 红线

1. **只能自用。** 数据来自东财/巨潮，二次分发有合规风险。
2. **抓取频率不能再高。** 扩展到全市场绝不能预抓，必须按需 + 缓存 + TTL。
3. **AI 输出必须标注"AI 生成，非投资建议"**。
4. **公告以巨潮原文为准。** AI 解读只是索引。
5. **level 标红标绿会误报**，红色只是提示读原文。
