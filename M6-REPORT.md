# M6 交付报告 · 长期研究与复盘

> 完成时间：2026-11-17 20:40 ｜ 阶段：2.0-M6

---

## 1. 研究笔记 ✅

`research_record` 表（迁移 005）：标题/内容/标签/关联词条，CRUD 全套。

**API**：
```
POST   /api/research            新建
PUT    /api/research/{id}       更新
DELETE /api/research/{id}       删除
GET    /api/research            列表（code/q/分页），支持标题/内容/标签搜索
GET    /api/research/{id}       详情
```

**前端**（AI tab → 研究工作台）：新建/编辑弹层（标题+内容+标签）、删除确认、搜索、时间排序。

**实测**：新建→更新→搜索命中→删除 全链路 ✓

## 2. 研究报告归档 ✅

`research_report` 表：晨报/月度复盘/辩论/AI 解读统一归档，kind+period 索引。

- **晨报已自动归档**（daily_brief kind）
- **月度复盘自动归档**（monthly_review kind，带 period=YYYY-MM）
- **Markdown 导出**：`GET /api/reports/{id}/export` 带下载头
- 列表/详情/删除 API 齐全

## 3. 月度研究复盘 ✅

`POST /api/ai/monthly-review`（SSE），**严格按历史时间顺序**（SQL `published_at ASC`），不事后伪装：

输入组装：
- 当月资料时间线（日期+类型+级别+标题）
- 当月 thesis 变更史（从 thesis_history 过滤当月，含原因）
- 当月已生成的研究记录（防复盘与已知信息脱节）

输出四段：本月重要变化 / thesis 支持与削弱 / 风险确认与未解决 / 下月研究重点

**实测输出**（中金岭南 2026-11，6 条资料）：
> **1. 本月重要变化（按时间顺序）**
> - 11-12《锑矿资源布局合作意向》…资料未给出公司回应内容
> - 11-13 两条股价与经营关切…资料未披露公司实质行动
> - 11-16《高弹铜钢复合材料（SCS）》铜用量降至 20%—30%…
> - 11-17 thesis 两次修改（M4 测试及恢复）…
>
> **2. 削弱**：资料未覆盖 TC/RC 具体水平…**thesis 的核心变量本月无任何量化验证**
>
> **3. 未解决**：锑矿合作是否推进（11-12 无回应）…TC/RC 与冶炼毛利现状（资料未覆盖）

诚实标注"资料未覆盖"，不做无依据推断——M2 规则贯穿。

---

## 修改文件

**新增**
```
migrations/005_research.py          research_record + research_report
web/src/components/ResearchView.vue 研究工作台（笔记+报告双 tab）
```

**修改**
```
invest_radar/store.py    +add/update/delete/list_research +save/list/get_report
                         +monthly_window
server/main.py           +7 个笔记/报告 API + 月度复盘 SSE + 导出
                         晨报归档到 research_report
web/src/api.js           +research*/report* 方法
web/src/App.vue          AI tab 加研究工作台
```

---

## 验收方法

手机下拉刷新（SW v202611172038）：

1. **AI tab** → 底部出现「研究工作台」
2. 点「＋ 笔记」→ 写一条"为什么关注中金岭南"→ 保存
3. 切「AI 报告」tab → 看到刚生成的「中金岭南 · 2026-11 月度复盘」→ 点开阅读 → 点「导出」下载 md
4. 顶部搜索框输入关键词过滤笔记

---

## 遗留（M7 收尾）

| 项 | 说明 |
|---|---|
复盘入口进个股详情 | 当前在 AI tab 全局入口；个股页入口 M7 顺手加 |
辩论/解读归档 | 已有表结构，debate 端点顺手补一行 save_report |
微信通知分流 | M5 遗留，待用户确认后改 schedule 提示词 |
最终全链路检查 | M7：安全/备份/手机体验/PWA/成本 全面复核 |
