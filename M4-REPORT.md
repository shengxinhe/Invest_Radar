# M4 交付报告 · 个股详情与资讯管理

> 完成时间：2026-11-17 20:22 ｜ 阶段：2.0-M4

---

## 交付清单

### 1. 个股详情五区重构 ✅

截图验证的五区结构：

**区1 公司概览**
- 名称 / 代码 / 角色标签（核心）
- **行业 + 市场**（沪市/深市/北交所）
- **数据新鲜度**：`● 行情 19:33:54（已过期）` 颜色随状态变
- **四源状态行**：`行情● 公告● 新闻● K线●`（绿=新鲜 黄=延迟 红=过期 灰=无数据）
- 价格 / 涨跌幅 / 市值 / PE / PB
- 趋势判断（空头排列+四条依据）

**区2 市场表现**：K线 6 周期（沿用 klinecharts）
**区3 公司事件**：公告/新闻/研报/互动 四类，带状态筛选
**区4 资金筹码**：龙虎榜/两融/股东户数/解禁
**区5 投资逻辑**（新增 tab）：
- 当前 thesis（标注版本号）
- 编辑逻辑（带修改原因输入）
- 历史版本列表（时间 + 原因 + 旧值红/新值绿 diff）

### 2. 资讯处理状态系统 ✅

`entry_user_state` 表（迁移 003 已建），六种状态：

```
unread 未读 → pending 待核查 → saved 稍后研究 → processed 已处理 → ignored 忽略
```

- **列表项右侧圆圈按钮**：点一下循环切换状态
- **状态 chip**：列表里显示当前状态（带颜色）
- **筛选按钮**：不限状态 / 待核查 / 稍后 / 已处理
- **已读弱化**：`is_read` 的条目标题变灰
- **个人备注**：`note` 字段可存

**API**：
```
POST /api/entry/{eid}/state      单条设置（status/is_read/note）
POST /api/entries/state          批量（≤200）
GET  /api/entries/states         各状态计数
GET  /api/stock/{code}/entries   列表已带 status 字段
```

### 3. Thesis 历史版本 ✅

`thesis_history` 表（迁移 003 已建）：

- 每次修改记录 `thesis_old / thesis_new / reason / changed_at`
- `thesis_version(code)` = 历史次数 + 1，注入 AI 提示词
- **改动立刻让 AI 缓存失效**（M2 的 cache_key 含 thesis_hash）
- 详情页可查看完整历史 diff

**实测**：
```
修改 thesis + 原因"M4 验收"
→ 版本号: 2
→ 历史记录 1 条
   原因: M4 验收
   旧: 铜冶炼占收入70%但毛利率极薄，赚的是加工费；有色价格+TC/RC是主变量
   新: ...（+[M4测试]）
```

### 4. 状态系统测试（6 项全过）✅

```
[1] 单条 CRUD：unread → pending(带备注) → processed        ✓
[2] 批量标记：3 条设 saved                                  ✓
[3] 状态统计：{unread:228, processed:1, saved:2}            ✓
[4] 列表回传：状态正确显示在每条上                          ✓
[5] thesis 历史：版本号递增 + 原因 + 新旧值                 ✓
[6] 重置为未读                                              ✓
```

---

## 修改文件

**新增**
```
web/src/components/StatusBar.vue   状态切换条（备用）
tests/test_m4.py                   M4 验收测试
scripts/shot.py                    CDP 截图工具（可复用）
```

**修改**
```
invest_radar/store.py     +set_entry_state/get_entry_state/state_map
                          +bulk_set_state/state_counts/STATUS_LABEL
server/main.py            +3 个状态 API / thesis 历史 API
                          / entries 带状态 / thesis 更新记历史
web/src/components/StockView.vue   五区重构 + 状态交互 + thesis 历史 tab
web/src/api.js            +setEntryState/bulkState/stateCounts
                          +thesisHistory/updateThesis
web/src/styles/components.css      +源状态行/状态 chip/quick 按钮/thesis diff
```

**清理**：删除 11 个临时补丁脚本

---

## 数据现状

```
231 条词条 / 5580 只股票 / 4 只关注
状态分布：unread 228, processed 1, saved 2
thesis 历史：2 条（含 M4 测试记录）
```

---

## 遗留

| 项 | 去向 |
|---|---|
公司研究档案独立页面 | M6 |
研究报告归档 | M6 |
K线 overlay 重复创建（切周期） | 待验证，M5 顺手查 |
320/360px 极窄屏 | M5 适配检查 |

---

## 验收方法

手机下拉刷新（SW v202611172007）：

1. **自选 tab** → 点中金岭南 → 看到五区（概览含行业/市场/四源状态）
2. **公告 tab** → 每条右侧有 ○ 圆圈，点一下变 ⚑ 待核查，再点变 ★ 稍后
3. 筛选行点"待核查" → 只显示标记过的
4. **逻辑 tab** → 看当前 thesis + 历史版本 diff，点"编辑逻辑"改一句试试
5. 改完 thesis 后去公告点"AI解读" → 会用新逻辑重新分析（缓存已失效）
