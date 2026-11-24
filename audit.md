# audit.md — 投资雷达 2.0 · M0 审计报告

> 审计时间：2026-11-17 19:08 ｜ 数据库版本：M0 备份点 `data/backups/radar_M0_20261117_190829.db`
> 审计方式：源码静态核查 + 数据库实查（非推测）

---

## 1. 数据库备份（红线流程已执行）

| 步骤 | 结果 |
|---|---|
停服 | uvicorn 进程已停止 |
WAL checkpoint | `(0,0,0)` 成功，wal/shm 合并清零 |
integrity_check（主库） | ok |
备份文件 | `data/backups/radar_M0_20261117_190829.db`（1.39MB） |
副本 integrity_check | ok |
副本实际查询 | stocks 5580 / watch 4 / entries 231 / entry_ai 3 / quotes 38 / kline 1856 / entry_fts 231 |
关注池内容 | 600251核心, 601668, 000530, 000060核心 |
**回滚点** | 恢复该文件即可回到 M0 前状态；迁移演练一律先在副本上做 |

---

## 2. 八项问题属实性核查（源码+DB 证据）

### ① Feed 分页缺陷 —【属实，高优先】
- SQL 先 `published_at < cursor` 过滤，随后在**已过滤**结果里用 `==cursor` 找游标起点 → 永远找不到 → `start=0` → **第二页重复首页内容**
- 实际展示顺序是 Python 的 `(level, type, -time)`，SQL 只有 `published_at DESC` → 游标与展示序完全脱节
- 每次 `LIMIT 400` 全量捞取后 Python 排序分页
- **修法（M1）**：SQL 端固定排序 `(level_rank, type_rank, published_at DESC, id DESC)` + 复合 keyset 游标，删除 Python 排序与 seek 逻辑

### ② FTS5 索引未同步 —【属实，高优先】
- `entry_fts` / `stock_fts` 均**无任何 INSERT/UPDATE/DELETE 触发器**
- `entry_fts` 从未执行过 rebuild（stock_fts 仅在 bulk_upsert_stocks 时 rebuild）
- 实测：最新词条标题片段 FTS match 0 命中（当前索引为空壳）
- **修法（M1）**：三触发器 × 两表 + 一次性 rebuild（迁移脚本内，不进请求路径）

### ③ 认证缺失 —【属实，高优先】
- CORS `allow_origins=["*"]`
- 全部 API 无认证依赖，写操作（改关注池/触发抓取/AI 调用）裸奔
- 启动默认 `--host 0.0.0.0`
- **修法（M1）**：服务端 Session（HttpOnly+Secure+SameSite+过期+登出+登录限流）+ CORS 收敛 + 监听默认 127.0.0.1；`/api/health` 仅存活信息

### ④ AI 缓存无版本 —【属实】
- `entry_ai` 主键 = entry_id，无 prompt_version/thesis_hash
- thesis 修改或提示词升级后旧解读继续命中（用户改逻辑后看到旧结论）
- **修法（M2）**：cache_key 加 model+prompt_version+thesis_hash；旧结果归档进 ai_analysis_version 保留历史

### ⑤ 同步 LLM 阻塞事件循环 —【属实】
- 多个 `async def` SSE 生成器内 `for piece in llm.chat(...)`（同步 requests 流）
- client.py 无 httpx/aiohttp → 每个流式 token 间歇性阻塞事件循环，多用户并发时全站卡顿
- **修法（M2）**：httpx.AsyncClient 重写 client + 超时/取消/并发信号量

### ⑥ SSE 行情每连接独立轮询 —【属实】
- `/api/stream/quotes` 每连接各自 `while True` 遍历关注池调腾讯接口
- 2 设备 × 4 页面 = 8 倍上游请求量，违反防封红线
- **修法（M5）**：中心轮询任务 → 共享缓存 → 连接订阅广播

### ⑦ CSS 变量双文件冲突 —【属实】
- `theme.css` 与 `style.css` 重叠定义 11 个变量（--accent/--bg/--down/--line/--panel/--panel2 等）
- main.js 先 theme 后 style → style 的旧值覆盖液态玻璃主题段
- **修法（M3）**：tokens/theme/components/utilities 四层拆分，去重，单一涨跌语义源

### ⑧ 前端交互缺陷 —【属实】
- 搜索无 AbortController/序号（旧响应可覆盖新结果）
- EventSource 创建后未保存实例，卸载不关闭
- FeedList 筛选切换与进行中加载冲突，无请求取消
- **修法（M3/M5）**：统一 useSSE composable + api.js AbortSignal + 组件清理

---

## 3. 现有功能基线（2.0 必须保全）

全 A 股搜索（5580，三路亚毫秒）｜行情 15 字段｜K线 9 周期前复权｜公告/新闻/研报/互动/快讯 5 类词条｜龙虎榜/两融/解禁/股东｜关注池+thesis 在线编辑｜AI：解读(缓存)/追问/批量/多空辩论/全局RAG+联网/晨报/成本面板｜watcher 轮询+微信双任务推送｜PWA（ts.net HTTPS）｜每日 20:00 备份（系统任务）｜旧静态看板

**抓取红线现状**：串行✓ 东财 1.2s✓ TTL✓ 按需抓取✓ 代理绕过✓ —— 2.0 全程保持。

---

## 4. 依赖与入口

- Python 3.12.10：fastapi 0.163.1 / uvicorn 0.54 / akshare / requests / pandas / pypinyin / pillow
- 前端：vue 3.5 / vite 6 / klinecharts 9 / npm 11
- 无 httpx（M2 需新增）、无 pytest（测试体系需新增）、无 alembic（用自写轻量 migration）
- 入口：`启动服务.bat`（uvicorn --host 0.0.0.0:8000）、tailscale serve（持久）、Windows 计划任务 20:00 备份、DSH schedule ×2（盘中轮询/晨报）

## 5. 回滚说明

任意阶段出问题：
1. 停服
2. `copy data\backups\radar_M0_20261117_190829.db data\radar.db`（覆盖前再拷当前库一份）
3. git/文件级回退代码（每阶段记录修改文件清单）
4. 重启服务验证 /api/health 与关注池

## 6. M1 待办（下一阶段，等验收后开工）

认证（Session/CORS/监听收敛）→ feed 分页重写+测试 → FTS 触发器+rebuild 迁移 → fetch_log 新鲜度体系 → 备份恢复演练。
