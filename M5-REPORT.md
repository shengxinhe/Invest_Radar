# M5 交付报告 · 实时行情与自动化

> 完成时间：2026-11-17 20:32 ｜ 阶段：2.0-M5

---

## 1. 共享行情轮询（解决审计第 6 项）✅

**原问题**：`/api/stream/quotes` 每个连接各自 `while True` 遍历关注池调腾讯接口 → N 设备 × M 页面 = N×M 倍上游请求，直接违反防封红线。

**新架构**（`server/quotes.py`）：

```
中心轮询任务（单例，lifespan 启停）
    ↓ 每轮串行抓 wanted 集合（遵循 ≥1.2s 红线）
内存缓存 _cache
    ↓ 只推送有变化的票（price/pct 比较）
广播到所有订阅者 Queue
    ↓ 队列满丢最旧，客户端断开自动 unsubscribe
```

**关键指标（实测）**：

| 场景 | 轮询次数 | 订阅数 |
|---|---|---|
无连接 | 1（仅关注池） | 0 |
**3 个并发 SSE** | **1**（未翻倍） | 3 |
全部断开 | — | **0**（自动清理） |

- 交易时段 5s / 非交易 60s 自动切换
- 抓取失败**不覆盖旧缓存**（保留上次有效值）
- 订阅上限 32（单人远够）
- 首帧立即发缓存快照，避免白屏
- 25s 心跳防代理断流

**诊断接口**：`GET /api/quotes/poller` → `{polls, pushes, errors, subscribers, cached, interval, trading}`

## 2. SSE 前端生命周期 ✅

`web/src/composables/useQuoteStream.js`：

- 保存 EventSource 实例（原来是局部变量，无法关闭）
- `onUnmounted` 自动关闭
- **页面隐藏时断开**（省电省上游），回前台重连
- 指数退避重连：2s → 4s → 8s → 最大 30s
- 防重复连接（`if (es) return`）
- 状态可观测：`idle/connecting/open/retrying/closed`

## 3. 微信三级通知 ✅

`invest_radar/notify.py`：

| 级别 | 触发 | 行为 |
|---|---|---|
**P1 立即推送** | 停产/事故/立案/调查/退市/预亏/违约/冻结/重大诉讼/控制权变更/董事长辞职 | 立刻打扰 |
**P2 定时汇总** | 担保/解禁/减持/增持/回购/定增/中标/投产/事务所变更/分红/业绩预告 | 汇总推送 |
**P3 仅入库** | 简称变更/LOGO/迁址/聘任/离任/投资者关系记录 | 不推送 |

**分级实测（7 个用例全对）**：
```
✓ [p1] 关于公司停产整顿的公告
✓ [p1] 关于收到证监会立案告知书的公告
✓ [p2] 关于为控股子公司提供担保的进展公告
✓ [p2] 关于限售股解禁的提示性公告
✓ [p3] 关于证券简称变更实施公告
✓ [p2] 关于拟变更会计师事务所的公告
✓ [p3] 关于举行投资者关系活动的公告
```

**配套机制**：
- **72h 去重**：同公司 + 标题规范化后比对，防重复打扰
- **每日配额**：P1 ≤ 10 条、P2 ≤ 5 条
- **状态记录**：`queued / sent / failed / skipped` 全链路可追
- **通知日志**：`notification_log` 表记录 level/code/title/entry_id/channel/status

**API**：
```
GET  /api/notify/stats    分级统计 + 待推数 + 配额状态
POST /api/notify/mark     标记已发/失败
```

**watcher 改造**：入队时执行 `classify()` → `already_notified()` → `log_notification()` 三步，队列项新增 `priority` 字段；报告里 P1 用 🚨、P2 用 📌 区分。

---

## 修改文件

**新增**
```
server/quotes.py                      共享轮询器（中心任务+缓存+广播）
web/src/composables/useQuoteStream.js SSE 生命周期管理
invest_radar/notify.py                三级分级/去重/配额/日志
tests/test_m5.py                      M5 验收测试
```

**修改**
```
server/main.py          SSE 端点为订阅模式 + /api/quotes/poller
                        + /api/notify/stats + /api/notify/mark
                        lifespan 启停轮询器
invest_radar/watcher.py 三级分级 + 去重 + 通知日志
web/src/App.vue         改用 useQuoteStream
```

**清理**：删 3 个临时脚本

---

## 遗留（转 M6/M7）

| 项 | 去向 |
|---|---|
微信实际发送链路对接三级通知 | 需在 DSH schedule 提示词里用 `priority` 字段分流 |
三级通知的「定时汇总」定时器 | M7 或按需 |
晨报升级（分级引用） | M6 |
K线 overlay 重复创建 | M7 验证 |
320/360px 极窄屏 | M7 适配检查 |
