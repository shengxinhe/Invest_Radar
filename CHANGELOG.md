# CHANGELOG · 投资雷达

## 2.0.0 — 2026-11-17 「系统升级」

### 安全
- 应用级认证：口令(scrypt) + 签名 Session(HttpOnly Cookie) + 登录限流 + 登出
- CORS 收敛为白名单；监听默认 127.0.0.1
- /api/health 脱敏，库统计迁至需登录的 /api/stats
- Session 落库（迁移 004），重启保持登录

### 修复（8 项审计问题）
- feed 无限滚动重复：SQL 端复合 keyset 分页（level/type/time/id 四段游标）
- FTS5 索引空壳：trigram 分词重建 + 6 个同步触发器 + <3 字 LIKE 兜底
- AI 缓存无版本：cache_key = entry+model+prompt_version+thesis_hash，thesis 改动即失效
- LLM 阻塞事件循环：httpx.AsyncClient 重写，信号量限流 3 并发
- SSE 每连接独立抓上游：共享轮询器，3 连接仍 1 次上游请求
- CSS 变量双文件覆盖：tokens/theme/components 三层拆分
- 前端搜索/SSE 竞态：AbortController + 请求序号 + 生命周期管理
- 数据新鲜度不可见：六态体系（fresh/delayed/stale/failed/missing/unknown），UI 与 AI 上下文全标注

### AI
- 交易员模式升级为证据优先：七段结构（核心结论/已核实事实/潜在影响/多空/thesis/待核查/失效条件）
- 取消强制编造概率与价位；允许输出"资料不足"
- 提示注入防护：外部正文声明为数据非指令
- 降噪口径改为"程序规则判定，未经人工核实"
- SSE 统一协议（start/chunk/segment/progress/warning/error/done）

### 新功能
- 首页驾驶舱：真实三大指数 / 今日重点分级 / AI 今日研究建议（自适应时间窗，不足即拒绝）
- 个股详情五区：概览(行业/市场/四源状态) / 走势 / 事件 / 筹码 / 投资逻辑
- 资讯六态管理：未读/待核查/稍后/已处理/忽略 + 备注 + 批量 + 筛选
- thesis 历史版本：diff 视图 + 修改原因 + AI 缓存联动失效
- 多空辩论归档 + 个股页月度复盘入口
- 研究笔记 CRUD + 搜索；AI 报告归档（晨报/复盘/辩论）+ Markdown 导出
- 月度研究复盘：严格按历史时间顺序，附 thesis 变更史
- 微信三级通知：P1 立即 / P2 汇总 / P3 入库 + 72h 去重 + 每日配额 + 通知日志

### 基础设施
- 版本化迁移框架 migrations/（5 个迁移，前置备份，幂等）
- 备份脚本升级：integrity_check + 四表查询验证 + 失败 exit 1
- 测试体系：分页 7 用例 / 认证矩阵 / AI 验收 / 状态 6 用例 / M5 通知 / M7 全链路 32 项

### 1.5.x（时间线内迭代，未单独版本化）
- 交易员模式提示词 / 多空辩论 / 联网搜索（巨潮 trigram + 东财快讯）
- 行情上下文全字段（换手/量比/振幅/成交额进 AI）
- 登录页 / 液态玻璃设计

## 1.0.0 — 2026-11-16
- M0-M5 + UI-KLINE：多源抓取 / SQLite+FTS / FastAPI+PWA / klinecharts / DeepSeek 四类 AI / watcher 微信推送 / Tailscale HTTPS
