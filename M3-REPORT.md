# M3 交付报告 · 移动端设计系统

> 完成时间：2026-11-17 20:01 ｜ 阶段：2.0-M3

---

## 交付清单

### 1. CSS 变量统一（解决审计第 7 项）✅

**改造前**：`theme.css` 与 `style.css` 双文件重叠定义 11 个变量，`main.js` 先 theme 后 style → **style 覆盖液态玻璃主题**。

**改造后**：六层分离，单一变量源

```
web/src/styles/
├── tokens.css        ← 唯一变量源（28 组：颜色/圆角/间距/字号/触摸尺寸）
├── theme.css         ← 基础重置 + 布局 + 工具类（零变量定义）
└── components.css    ← 组件样式（零变量定义）
```

- A 股涨跌语义**单点定义**：`--up: #FF5C7A`（涨红）、`--down: #3DDC97`（跌绿）
- 保留旧别名（`--panel/--panel2/--line/--dim`）映射到新 token，旧组件无需改动
- 删除 `style.css`（187 行，含 14 个重复变量）

### 2. 首页改版为投资驾驶舱 ✅

| 区块 | 内容 | 数据来源 |
|---|---|---|
今日脉搏 | 呼吸点（risk 变红加速）+ 24h 风险/利好计数 + 待读徽章 | `/api/pulse` |
**大盘** | 上证/深证/创业板**真实指数** + 关注池涨跌家数 | `/api/market/overview`（腾讯，60s 缓存） |
**今日重点** | 按 level 分级的 3 条优先事项（风险/机会/待查标签） | `/api/feed?filter=risk` |
我的关注 | 横滑卡片（价格/涨幅/PE） | `/api/watch` |
**今日研究建议** | AI 从近 24h 信息挑 3 件事，每条含"为什么值得研究"+"具体查什么" | `/api/ai/today-focus` |
最新资讯 | 无限滚动 + 筛选 | `/api/feed` |

**实测 AI 输出质量**（第 2 条尤其精准）：
> **中金岭南 11-16 高弹铜钢复合材料（SCS）问答**
> 为什么值得研究：thesis 核心是"铜冶炼加工费薄利"，而 SCS 把铜用量降至 20%–30%，属于产品结构/单位铜耗的潜在变化，可能影响"有色价格+TC/RC 是主变量"这一路径的敏感度（铜价敞口下降、加工附加值上升）
> 具体查什么：查该材料的产能/收入占比、客户与量产阶段…

**自适应窗口**：近 24h 不足 2 条时自动放宽到 72h → 7 天；全无内容时明确拒绝生成（"信息不足，暂不生成"），不编造。

### 3. 通用组件库 ✅

```
components/ui/
├── DataFreshness.vue   六态新鲜度标签（fresh/delayed/stale/failed/missing/unknown）
├── EmptyState.vue      空/错误/离线三态 + 重试
└── Skeleton.vue        骨架屏（尊重 prefers-reduced-motion）
components/
├── MarketOverview.vue  大盘概览
└── TodayFocus.vue      今日研究建议
```

### 4. 搜索竞态保护（审计第 8 项之一）✅

`web/src/composables/useSearch.js`：
- 防抖 220ms
- AbortController 取消旧请求
- **请求序号**：旧响应永不覆盖新结果
- 组件卸载自动取消
- 错误/空结果独立状态

### 5. FeedList 重写（审计第 8 项之二）✅

- `AbortController` 取消进行中请求
- 请求序号防竞态
- 切筛选 → 立即取消 + 重置游标
- **去重兜底**（`items.some(x => x.id === ...)`）
- 骨架屏（首次加载）+ 错误重试 + 空态
- `onUnmounted` 断开 IntersectionObserver + abort

### 6. Session 落库（弥补 M1 遗留）✅

迁移 `004_session_persist.py` 建 `app_session` 表，`security.py` 改为库读写：
- 重启服务**保持登录**（不再要求重新输口令）
- 启动时 `prune_sessions()` 清理过期会话
- 记录 `created_at / last_seen / ip / ua`
- DB 异常时自动降级回内存字典

---

## 顺带修掉的严重 bug

**根路径 `/` 被认证中间件拦截** → 返回 `{"ok":false,"msg":"未登录"}` 的 JSON，**登录页根本加载不出来**（首次截图暴露）。

修复：`is_public()` 改为「非 `/api/` 前缀一律放行」，只有 API 需要认证。

验证：
```
GET /            -> 200 ✓（登录页可加载）
GET /api/watch   -> 401 ✓（未登录仍拦截）
GET /api/health  -> 200 ✓（公开）
```

---

## 修改文件

**新增**
```
web/src/styles/tokens.css            变量唯一源
web/src/styles/components.css        组件样式
web/src/composables/useSearch.js     搜索竞态保护
web/src/components/MarketOverview.vue  大盘概览
web/src/components/TodayFocus.vue     今日研究建议
web/src/components/ui/DataFreshness.vue
web/src/components/ui/EmptyState.vue
web/src/components/ui/Skeleton.vue
migrations/004_session_persist.py
scripts/_shot_login.py               CDP 登录态截图工具
```

**重写**
```
web/src/styles/theme.css      只保留元素/布局
web/src/components/FeedList.vue  请求取消+竞态+骨架屏+去重
web/src/main.js               三层样式导入
```

**修改**
```
server/main.py           +/api/market/overview  +/api/ai/today-focus  +prune_sessions
server/security.py       Session 落库 + is_public 修复
server/auth_routes.py    传 UA
web/src/App.vue          首页驾驶舱 + useSearch 接入
web/src/api.js           feed 游标签名 + marketOverview
scripts/**               临时补丁脚本（已清理逻辑，文件待删）
```

**删除**
```
web/src/style.css        （187 行重复样式）
```

---

## 验收方法

手机打开 `https://rancho.duiker-ling.ts.net`（**下拉刷新**拉新 SW 版本 v202611171958）：

1. 登录后（**现在重启服务不用重新登录了**）
2. 首页自上而下：脉搏 → 大盘（真实指数）→ 今日重点 → 关注横滑 → **今日研究建议（点"生成"）** → 资讯流
3. 搜索框快速输入不同关键词 → 结果不会串
4. 资讯流切"风险"/"利好" → 不会出现重复或卡住

---

## 遗留（转 M4）

| 项 | 去向 |
|---|---|
320/360px 极窄屏细调 | M4 顺手做 |
横屏布局 | M4 |
entry_user_state 资讯处理状态 | M4 |
thesis 历史版本 UI | M4 |
个股详情五区重构 | M4 |
CSRF token | 当前 SameSite=Lax + 自定义 header 足够，M5 视需要 |
临时补丁脚本清理 | M4 开始前清 |
