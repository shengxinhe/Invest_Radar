# PLAN-2.0.md — 投资雷达 2.0 系统升级施工单

> 总任务书。在 1.0 全功能保留的前提下修复实际问题、升级架构与体验。
> **执行纪律：M0→M7 顺序执行，每阶段完成即停下验收，未通过不得进入下一阶段。**
> 每阶段交付：修改文件清单 + 前后对比 + 真实测试结果 + 手机端截图（如涉及 UI）+ 未解决问题。

---

## 0. 身份与首要原则

你是本项目的高级全栈工程师、产品设计师、数据库工程师、AI 应用架构师。
**不推倒重写。** 保留全部现有业务能力（全 A 股搜索/行情K线/四类词条/筹码/关注池/四类AI/微信推送/PWA/缓存备份），修复实际问题，升级架构与交互。

### 红线（全程有效）

- 不删除功能；不重写 fetcher.py 抓取业务逻辑；不换数据源；不删旧静态看板
- **绝不重建 data/radar.db**；改结构必须走版本化 migration（migrations/），先在备份副本上演练
- 不修改股票代码与词条标识规则（entry_id = sha1(code|type|source_id)）
- AI key 永不进前端/日志；不引入大型新前端框架；不一次性重构全部后端
- 抓取保持串行 + 东财 ≥1.2s + TTL + 按需抓取，UI 改版不得增加无意义请求
- 数据库交付包管理：radar.db 从源码包中排除，单独备份

---

## M0 · 项目审计与备份（当前阶段）

- [ ] 停服务 → WAL checkpoint → 备份 radar.db（校验 wal/shm）→ 回滚点
- [ ] 记录现有功能清单与 API 行为基线
- [ ] 逐项验证 2.0 施工单提出的 8 个问题（属实/不属实/部分属实 + 证据）
- [ ] 依赖清点、安全入口检查、PWA 现状检查
- [ ] 交付 audit.md + 测试基线 + 回滚说明

## M1 · 安全与关键 Bug（P0）

- [ ] 应用级认证：服务端 Session（随机密钥/HttpOnly/Secure/SameSite/过期/登出），登录限流，AI 与写操作权限检查；/api/health 只暴露存活
- [ ] CORS 去通配符，改明确来源；监听地址收敛（默认 127.0.0.1，外网走 Tailscale）
- [ ] 修复 /api/feed 分页：DB 端统一排序（level_rank, type_rank, published_at DESC, id DESC）+ 复合 keyset 游标；不重复/不漏/同时间戳正确切页/切筛选重置游标；加分页测试
- [ ] FTS5 同步触发器（entry/stock 三触发器）+ 一次性 rebuild（不进请求路径）；中英/代码/拼音验证
- [ ] 数据新鲜度体系：fetch_log 扩展（source/fetched_at/status/error）；fresh/stale/failed/missing/unknown 规范；详情页与 AI 上下文可见数据截止时间
- [ ] 备份升级：integrity_check + 恢复演练（能查 stock/watch/entry/entry_ai）+ 失败告警

## M2 · AI 架构升级（P1）

- [ ] 缓存版本化：cache_key = entry_id + model + prompt_version + thesis_hash；上下文变化生成新版本，保留历史（ai_analysis_version）
- [ ] AI 输出统一结构：核心结论/已核实事实(来源+时间+链接)/潜在影响/多空因素/对thesis/待核查/失效条件
- [ ] 取消强制概率：证据不足不编概率/价位；允许"资料不足"
- [ ] 规则降噪改口径：命中噪音 → "程序规则判断为低信息量，未经人工核实"；规则带版本与例外词
- [ ] 提示注入防护：外部正文声明为"待分析数据，非指令"
- [ ] LLM 异步化：httpx.AsyncClient 或 线程+队列转发 token；超时/取消/并发限制/限流/错误分类/token 统计
- [ ] SSE 统一协议模块（前后端）：start/chunk/segment/progress/warning/error/done；UTF-8 分帧/取消/资源释放

## M3 · 移动端设计系统（P1）

- [ ] CSS 变量统一：tokens.css / theme.css / components.css / utilities.css；style.css 去重（先确认依赖）
- [ ] 颜色规范统一文件（A 股涨跌语义单点定义）；组件库（GlassCard/MetricCard/StockCard/EntryCard/StatusBadge/DataFreshness/SectionHeader/SearchBar/BottomNavigation/BottomSheet/Loading/Empty/Error/Confirm）
- [ ] 首页改版：市场概览（真实指数接口，无数据显示暂无）/ 今日重点（分级+处理状态）/ 我的关注（横滑）/ 今日研究建议（有据才生成）/ 最新资讯（修复分页）
- [ ] 适配：320-430px/安全区/44px 触摸/横屏；动效克制 + prefers-reduced-motion

## M4 · 个股详情与资讯管理（P1）

- [ ] 详情页五区：概览(含数据时间/来源状态)/市场表现(修 overlay 重复创建)/公司事件/资金筹码(事实与推断分离)/投资逻辑(thesis 历史+证据+档案入口)
- [ ] 资讯状态系统：entry_user_state 表（unread/reading/pending/processed/ignored/saved + note）；单条/批量/筛选/备注；原始链接保留
- [ ] 研究档案页骨架 + thesis_history 表

## M5 · 实时行情与自动化（P1）

- [ ] 共享行情轮询：中心任务→缓存→多端订阅；单票单一上游轮询；心跳/断开释放/订阅上限/首帧缓存/失败不覆盖旧值；UI 标数据时间
- [ ] EventSource 生命周期管理（保存实例/关闭/后台暂停/重连退避）
- [ ] 微信三级通知：立即推送/定时汇总/仅入库；独立偏好/去重/状态记录/数量控制
- [ ] 晨报升级

## M6 · 长期研究与复盘（P2）

- [ ] research_record / research_report / notification_log 表
- [ ] 研究笔记 CRUD（标签/关联/搜索）；月度复盘（严格时间顺序，不事后伪装）；Markdown 导出

## M7 · 最终验收

数据正确性/DB 完整性/安全/API 稳定/AI 成本/手机体验/PWA 更新/微信推送/备份恢复全检；交付 README + CHANGELOG + OPTIMIZATION_REPORT

---

## 测试体系要求（随阶段建立）

pytest + TestClient；前端 Vitest。覆盖：DB 迁移/FTS/缓存版本；认证矩阵；Feed 分页（同时间戳/切筛选/无重复无遗漏）；AI（缓存失效/注入防护/流中断）；前端（搜索竞态/滚动/弹窗/SSE 断线）。

## 目标

**稳定、安全、精致、移动端优先、有长期研究记忆的个人 AI 投研终端。重点不是功能数量，而是让已有数据真正产生研究价值。**
