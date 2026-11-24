# PLAN.md — 从「本地静态看板」升级为「随身 AI 投研终端」

> 施工单。按 M0 → M5 顺序执行，**每完成一个里程碑停下来等验收**，不要一口气做完。

---

## 0. 一句话结论

**不要推倒重来。** 现有抓取层（`fetcher.py`）和判断逻辑（`analyzer.py` + `thesis`）是最值钱的部分，保留。
要做三件事：

1. "生成静态 HTML" → **"常驻 API 服务 + PWA 前端"**
2. "两只票" → **"全市场股票主数据 + 按需抓取 + 关注池"**
3. **词条层**加 AI 解读/追问接口

---

## 1. 现状 vs 目标

| 诉求 | 现状 | 本质差距 |
|---|---|---|
| 每个词条能点开搜索 | 静态 HTML，条目是死链 | 缺"详情页 + 原文抓取 + AI 解读" |
| 装到手机上 | `out/dashboard.html` 只能本地双击 | 需要 HTTPS + 服务端 + PWA manifest |
| 接入 AI 模型 | 无 | 需要后端代理 LLM + 提示词（**key 绝不能进前端**） |
| 信息实时 | 手动双击 bat | 需要常驻进程 + 定时任务 + SSE |
| 所有股票可搜 | `WATCHLIST` 硬编码两只 | 需要全 A 股主数据 + FTS 索引 + 懒抓取 |

---

## 2. 目标架构

```
┌─────────────────────────────────────────────┐
│  手机 PWA（添加到主屏幕，HTTPS）              │
│  搜索 / 关注池 / 词条详情 / AI 对话 / 推送     │
└───────────────┬─────────────────────────────┘
                │ Cloudflare Tunnel（免费，自带 HTTPS）
                │ + Cloudflare Access（邮箱白名单）
┌───────────────▼─────────────────────────────┐
│  本地 Windows PC（常驻）                       │
│  ┌───────────────────────────────────────┐  │
│  │ FastAPI 服务                           │  │
│  │  ├ /api/*        业务接口              │  │
│  │  ├ /api/stream   SSE 实时行情          │  │
│  │  └ 静态托管 web/  (PWA)                │  │
│  ├───────────────────────────────────────┤  │
│  │ APScheduler 定时抓取（串行 + 限流）    │  │
│  ├───────────────────────────────────────┤  │
│  │ invest_radar（现有抓取逻辑，改为库）    │  │
│  ├───────────────────────────────────────┤  │
│  │ SQLite + FTS5                          │  │
│  └───────────────────────────────────────┘  │
└───────────────┬─────────────────────────────┘
                │
        ┌───────▼────────┐
        │ LLM API 代理    │  ← DeepSeek / Qwen / Kimi
        └────────────────┘
```

---

## 3. 五个关键决策

### ① 抓取留在国内家宽，不要上云

东财、巨潮对云厂商 IP 和海外 IP 封锁更严。
- 抓取跑本地 PC
- **Cloudflare Tunnel** 把本地 8000 映射为 `https://radar.域名.com`
- **Cloudflare Access** 邮箱白名单

> 备选：Tailscale（零成本，但手机要常开 VPN，PWA 体验打折）。**首选 Cloudflare Tunnel。**

### ② 前端用 PWA，不做原生 App

iOS 16.4+ 支持"添加到主屏幕 + Web Push"。
- `manifest.webmanifest` + `sw.js`（离线壳）
- SPA：**Vue 3 + Vite + Tailwind**
- 不引入其他 UI 框架

### ③ 数据库用 SQLite + FTS5

单用户场景够用，内嵌全文检索，省掉 Meilisearch。

### ④ AI 走后端代理，且必须缓存

- 客户端只调 `/api/ai/*`，key 存服务端 `.env`
- **同一条词条只解读一次**，存 `entry_ai` 表
- 解读用便宜模型（DeepSeek-chat / Qwen-turbo），追问才用强模型
- 预算：每天 200 次调用，月成本 < 20 元

### ⑤ "实时"分级

| 数据 | 刷新 | 说明 |
|---|---|---|
| 关注池行情 | SSE，交易时段 5s | 只推关注池 |
| 公告 | 5 分钟轮询巨潮 | 新的 → 红点 + 飞书 |
| 新闻 | 15 分钟轮询东财 | 同上 |
| 全市场其他票 | **按需抓 + 缓存** | 点进去才抓，见 TTL |

**手机通知不用 Web Push**（iOS 坑深）。用**飞书/企业微信群机器人 webhook**，后端发现红色公告直接 POST。

---

## 4. 数据模型（SQLite）

```sql
-- 全市场股票主数据，每日 8:00 更新
CREATE TABLE stock (
  code TEXT PRIMARY KEY,          -- 000060
  name TEXT NOT NULL,             -- 中金岭南
  pinyin TEXT,                    -- zjln
  market TEXT,                    -- sz/sh/bj
  industry TEXT,
  concepts TEXT,                  -- JSON 数组
  updated_at INTEGER
);
CREATE VIRTUAL TABLE stock_fts USING fts5(code, name, pinyin, concepts);

-- 关注池（替代 WATCHLIST，可在线编辑）
CREATE TABLE watch (
  code TEXT PRIMARY KEY,
  role TEXT,                      -- 核心 / 观察 / 已清仓
  tags TEXT,                      -- JSON
  thesis TEXT,                    -- ★ 灵魂字段，AI 提示词要用
  keywords TEXT,                  -- JSON，高亮用
  sort INTEGER
);

-- 词条：公告 / 新闻 / 研报 / 互动易
CREATE TABLE entry (
  id TEXT PRIMARY KEY,            -- sha1(code+type+source_id)
  code TEXT NOT NULL,
  type TEXT NOT NULL,             -- notice/news/report/qa
  source_id TEXT,
  title TEXT,
  url TEXT,
  published_at INTEGER,
  content TEXT,
  level TEXT,                     -- risk / positive / neutral
  created_at INTEGER
);
CREATE INDEX idx_entry_code_type ON entry(code, type, published_at DESC);
CREATE VIRTUAL TABLE entry_fts USING fts5(title, content);

-- AI 解读缓存（一条词条只生成一次）
CREATE TABLE entry_ai (
  entry_id TEXT PRIMARY KEY,
  model TEXT,
  summary TEXT,
  why_matters TEXT,
  thesis_impact TEXT,
  read_hint TEXT,
  tokens INTEGER,
  created_at INTEGER
);

-- AI 追问对话
CREATE TABLE chat (
  id TEXT PRIMARY KEY,
  scope TEXT,                     -- entry:{id} / stock:{code} / global
  role TEXT,                      -- user / assistant
  content TEXT,
  created_at INTEGER
);

-- 行情快照（只存关注池，滚动保留 30 天）
CREATE TABLE quote (
  code TEXT, ts INTEGER, price REAL, pct REAL,
  volume_ratio REAL, pe REAL, pb REAL, mcap REAL,
  PRIMARY KEY (code, ts)
);

-- 抓取时间戳，用于 TTL 判断
CREATE TABLE fetch_log (
  key TEXT PRIMARY KEY,           -- quote:000060 / notice:000060 / universe
  fetched_at INTEGER
);
```

**TTL 策略**（`cache.py`）：

| 数据 | TTL |
|---|---|
| 全市场股票列表 | 24h |
| 行情 | 交易时段 30s / 非交易时段 1h |
| 公告、互动易 | 15min |
| 新闻 | 30min |
| 研报、筹码 | 6h |

---

## 5. 施工单

### M0 · 重构为库（0.5 天）

- [ ] `invest_radar/fetcher.py` 签名不变，但**去掉所有 `print` 和文件写入**
- [ ] 新增 `invest_radar/store.py`：SQLite 读写（`upsert_entry` / `upsert_quote` / `need_refresh`）
- [ ] `config.py` 的 `WATCHLIST` 首次启动导入 `watch` 表，之后以 DB 为准
- [ ] 现有 `--board` 保留，用于回归对比

**验收**：`python -m invest_radar --board` 输出和改造前一致。

### M1 · 服务化 + 手机可访问（1 天）

- [ ] `server/main.py`（FastAPI + uvicorn），静态托管 `web/`
- [ ] `web/` 最小 PWA：关注池 + 两个页签 + 添加到主屏幕
- [ ] `cloudflared tunnel --url http://localhost:8000` 跑通
- [ ] Cloudflare Access 配邮箱白名单
- [ ] 手机 Safari → 添加到主屏幕 → 正常用

**验收**：手机点 App 图标能看到关注池，断网显示缓存页。

### M2 · 全市场搜索（1 天）

- [ ] `scripts/update_universe.py`：`akshare.stock_info_a_code_name` 拉全 A 股，生成拼音首字母，写入 `stock` + `stock_fts`
- [ ] APScheduler 每天 08:00 跑
- [ ] `GET /api/search?q=` 支持代码前缀 / 名称模糊 / 拼音首字母
- [ ] 前端顶部搜索框，防抖 200ms，下拉出结果
- [ ] 点结果 → `/stock/{code}`，**首次访问触发懒抓取**（带 loading）

**验收**：`zjln` / `000060` / `岭南` 都能搜到中金岭南；未关注过的票 3 秒内出概览。

### M3 · 词条详情 + AI（2 天）★核心

- [ ] `GET /api/entry/{id}`：标题、时间、来源、全文、同公司前后 5 条
- [ ] 前端：列表项点击 → 抽屉展示
- [ ] 详情页三个按钮：
  1. **AI 解读** → `POST /api/entry/{id}/ai`（SSE 流式，四段输出）
  2. **看原文** → 新窗口
  3. **全网搜索** → 雪球搜 `{公司名} {关键词}`
- [ ] 底部**追问框**：多轮，上下文带 `entry.title + content + watch.thesis`
- [ ] 列表页**多选** → "对选中 5 条一起问 AI"

**验收**：点开公告 3 秒内出解读，且明确提到"这跟你写的 thesis 是什么关系"。

### M4 · 实时与推送（1 天）

- [ ] `GET /api/stream/quotes`：SSE，交易时段 5s
- [ ] 前端订阅，数字实时跳动
- [ ] APScheduler：公告 5min / 新闻 15min
- [ ] `level=risk` 新公告 → 飞书 webhook
- [ ] 每日晨报：8:30 汇总关注池，AI 写 300 字，存库 + 推送

**验收**：手机飞书收到"新风险公告"通知，点链接进详情。

### M5 · 打磨

- [ ] 关注池在线编辑（手机改 thesis）
- [ ] 全局 AI 助手（RAG 检索相关词条）
- [ ] 解读支持"重新生成 / 换个说法"
- [ ] 离线壳、弱网优化
- [ ] 成本面板（本月 token）

---

## 6. API 契约

```
GET  /api/watch                     关注池
POST /api/watch                     加/改 {code, thesis, keywords, role}
DEL  /api/watch/{code}

GET  /api/search?q=                 股票搜索
GET  /api/stock/{code}              概览
GET  /api/stock/{code}/entries?type=notice&days=30&level=risk
GET  /api/stock/{code}/chart?days=120

GET  /api/entry/{id}                词条详情
POST /api/entry/{id}/ai             AI 解读（SSE）
POST /api/entry/{id}/chat           追问（SSE）
POST /api/ai/batch                  批量问（entry_ids[] + question）

GET  /api/stream/quotes             SSE 实时行情
GET  /api/daily?date=               晨报

GET  /api/health                    健康检查（Tunnel 探活）
```

---

## 7. AI 层设计

**统一入口** `server/llm/client.py`：

```python
async def chat(messages, model="deepseek-chat", stream=True): ...
```

**词条解读提示词**（`prompts.py`）：

```
你是我的个人投研助理。我的持仓逻辑（thesis）是：
【{thesis}】
关键词：{keywords}

下面是我关注的一家公司（{name} {code}）在 {date} 的一条{type}：
标题：{title}
正文：{content}

请严格按四段输出，每段不超过 80 字：
1. 这是什么（客观事实，不带判断）
2. 为什么重要（对基本面/股价的潜在影响）
3. 跟我的 thesis 什么关系（支持 / 削弱 / 无关，说明理由）
4. 原文里我该重点看哪一段

不要给买卖建议。如果信息不足以判断，直接说"信息不足"。
```

**关键**：把 `thesis` 注入每次解读 —— 它永远在问"这跟你当初的逻辑什么关系"。

**成本控制**：
- 解读用 `deepseek-chat`
- 追问用 `deepseek-reasoner`
- `entry_ai` 命中直接返回，UI 显示"已解读过"
- 单次解读限 1500 token 输入

---

## 8. 部署与安全清单

- [ ] `.env` 存 `LLM_API_KEY`、`CF_ACCESS_AUD`，**进 `.gitignore`**
- [ ] 后端校验 `Cf-Access-Jwt-Assertion`，非法 403
- [ ] 所有抓取串行 + 1.2s 间隔（沿用现有，别改）
- [ ] 只监听 `127.0.0.1:8000`，靠 Tunnel 出去
- [ ] PC 电源计划设"从不睡眠"，或用树莓派/N100
- [ ] 每日备份 `data/radar.db` 到 OneDrive/坚果云

---

## 9. 风险与红线（写进 README）

1. **只能自用。** 数据来自东财/巨潮，二次分发有合规风险。Cloudflare Access 就是为这个。
2. **抓取频率不能再高。** 扩展到全市场**绝不能预抓**，必须按需 + 缓存 + TTL，否则三天被封。
3. **AI 输出必须标注"AI 生成，非投资建议"**，UI 固定水印。
4. **公告以巨潮原文为准。** AI 解读只是索引，"看原文"按钮永远放第一位。
5. **level 标红标绿会误报**，红色只是提示读原文。

---

## 10. 执行须知

> 严格按 M0→M5 顺序，每完成一个里程碑停下来验收。
>
> 硬约束：
> - 不删除 `fetcher.py` / `analyzer.py` 的业务逻辑，只做"去 print / 去写文件 / 加缓存"
> - 所有网络抓取串行且间隔 ≥1.2s
> - LLM key 只在服务端读取，前端不许出现
> - 每个接口写完用 `curl` 自测并贴输出
> - 前端只写 Vue 3 + Vite + Tailwind
> - 每完成一步更新 `README.md` 的"当前进度"
