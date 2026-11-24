# M1 交付报告 · 安全与关键 Bug 修复

> 完成时间：2026-11-17 19:35 ｜ 阶段：2.0-M1
> 数据库迁移：001/002/003 已应用（前置备份 `radar_premigrate_20261117_192333.db`）

---

## 交付清单

### 1. 应用级认证 ✅

| 项 | 实现 |
|---|---|
方案 | 口令 + 服务端 Session（HttpOnly Cookie，签名防篡改） |
密钥 | `data/.session_secret`（随机 48 字节，chmod 600） |
口令存储 | `.env` 的 `RADAR_PASSWORD_HASH`（scrypt n=16384 派生，不可逆） |
会话有效期 | 30 天 |
登录限流 | 同 IP 5 次/5 分钟 |
登出 | 服务端会话销毁 + Cookie 清除 |

**你的登录口令：`tiger-tiger-amber-2318`**（保存在 `.env`，可随时改）

接口：
```
GET  /api/auth/status   公开：是否已配置、是否已登录
POST /api/auth/setup    首次设置口令（仅未配置时可用）
POST /api/auth/login    登录
POST /api/auth/logout   登出
```

**保护区**：除 `/api/health`、认证相关、静态资源外，**全部 API 默认 401**。
实测 8 个敏感接口未登录全部拒绝。

### 2. health 脱敏 ✅
`/api/health` 现在只返回 `{ok, ts, service, version}`，库统计迁到需登录的 `/api/stats`。

### 3. CORS 收敛 ✅
`allow_origins` 从 `["*"]` 改为明确的三项：`127.0.0.1:8000`、`localhost:8000`、`rancho.duiker-ling.ts.net`。`allow_credentials=True` 支持 Cookie。

### 4. 监听地址收敛 ✅
默认 `--host 127.0.0.1`（原 `0.0.0.0`）。外网仍经 Tailscale Serve 进入，攻击面收敛。

### 5. Feed 分页重写 ✅
**原 bug**：SQL 按 `published_at DESC` 过滤游标 → Python 里再按 `(level,type,time)` 排序并寻找游标 → 永远找不到 → 重复首页。

**新实现**：SQL 端 `CASE` 表达式算 rank，单一排序 `(lv_rank, tp_rank, published_at DESC, id DESC)`，复合 keyset 游标 `lv:tp:ts:id` 四段式，SQL 直接分页（不再捞 400 条给 Python）。

**测试结果（7 项全过）**：
```
[1] 全量翻页: 4 页 89 条, 重复 0            ✓
[2] 覆盖完整性: 89/89, 无遗漏               ✓
[3] 展示序单调性: 严格有序                  ✓
[4] 同时间戳: 6 条全部取到且不重复          ✓
[5] risk 筛选: 7/7 独立正确                 ✓
[6] positive 筛选: 0/0                      ✓
[7] 非法游标容错: 全部 200 不崩             ✓
```

### 6. FTS5 索引同步 ✅
**原 bug**：无任何触发器，索引是空壳（实测最新词条 0 命中）。

**迁移 001**：
- 6 个触发器（entry/stock 各 AI/AU/AD）
- 分词器从 unicode61 改为 **trigram**（实测 unicode61 下「岭南」搜不到「中金岭南」，trigram 可）
- 迁移内一次性 rebuild

**CRUD 全链路验证**：
```
新增词条 → 立即命中        ✓
更新标题 → 新标题命中      ✓
         → 旧标题失效      ✓
删除词条 → 不再出现        ✓
2 字查询 → LIKE 兜底       ✓（trigram 最小 3 字符）
```

### 7. 数据新鲜度体系 ✅
`fetch_log` 增列：`source` / `status` / `error`。
新函数：`mark_fetched(key, source, status)`、`mark_failed(key, error)`（**失败不覆盖旧时间戳**，防止旧有效数据被清空）、`data_status(key)`、`quote_freshness(code)`。

状态规范：`fresh` / `delayed` / `stale` / `failed` / `missing` / `unknown`

**暴露到 API**：`/api/stock/{code}` 新增 `freshness` 与 `sources` 字段。
**前端**：个股详情显示带颜色圆点的数据时间标签（绿=新鲜/黄=延迟/红=过期/灰=无数据）。

### 8. 备份升级 ✅
`scripts/backup.ps1` 现在：
- WAL checkpoint 后拷贝
- **对备份文件实际执行 integrity_check + 查询 stock/watch/entry/entry_ai**
- 校验失败则保留文件并 exit 1
- 保留 14 份

**恢复演练**：把备份恢复到临时库 → integrity ok → stock 5580 / watch 4 / entry 231 / entry_ai 3 / kline 1856 / 关注池 4 条正确 → 清理临时文件。**通过**。

### 9. 数据库迁移框架 ✅
`migrations/runner.py` + 3 个迁移脚本，`schema_migrations` 表记录版本，幂等（重复执行全 skip），迁移前强制备份。

---

## 修改文件清单

**新增**
```
migrations/__init__.py
migrations/runner.py                              迁移框架
migrations/001_fts_triggers_and_freshness.py      FTS trigram + 触发器 + fetch_log 扩展
migrations/002_ai_cache_version.py                AI 缓存版本字段 + 历史表
migrations/003_user_state_and_research.py         entry_user_state/thesis_history/notification_log
server/security.py                                认证核心（scrypt/签名Session/限流）
server/auth_routes.py                             认证路由
web/src/components/Login.vue                      登录页
tests/test_feed_pagination.py                     分页测试（7 用例）
tests/test_auth.py                                认证矩阵测试
```

**修改**
```
server/main.py          CORS 收敛 / 认证中间件 / health 脱敏 / stats 新端点
                        / feed 重写 / 详情页 freshness / 监听 127.0.0.1
invest_radar/store.py   search_entries trigram+LIKE / mark_fetched 扩展
                        / mark_failed / data_status / quote_freshness / last_fetched 修复
invest_radar/universe.py  stdout 包装移到 __main__（修 import 副作用）
web/src/App.vue         登录门控 + 401 兜底 + 卸载清理
web/src/api.js          credentials + 401 事件派发
web/src/components/StockView.vue  数据新鲜度标签
web/src/styles/theme.css          fresh-tag 样式
scripts/backup.ps1      integrity_check + 恢复校验 + 失败退出
```

---

## 验收方法（你可以自己验证）

**手机/浏览器**：打开 `https://rancho.duiker-ling.ts.net`
1. 应看到登录页 → 输入 `tiger-tiger-amber-2318`
2. 登录后进任意个股 → 名称下方有带圆点的「行情 HH:MM:SS」标签
3. 首页资讯下拉到底 → 不会再出现重复内容

**命令行验证 401**：
```powershell
# 无 Cookie 直接访问应 401
curl https://rancho.duiker-ling.ts.net/api/watch
```

---

## 未解决 / 留给后续阶段

| 项 | 计划 |
|---|---|
Session 存内存（重启失效） | M2 落 SQLite，支持重启保持登录 |
CSRF token | 当前 SameSite=Lax + 自定义 header 已足够；正式 token 机制留 M2 |
AI 缓存版本逻辑（表已建好） | M2 接入 cache_key 判断 |
LLM 异步化 | M2 |
SSE 共享轮询 | M5 |
CSS 变量统一 | M3 |
前端 AbortController | M3 |

---

## 回滚方法

```powershell
# 停服
Get-Process python | Where-Object { $_.CommandLine -match 'uvicorn' } | Stop-Process -Force
# 回滚数据库
Copy-Item data\backups\radar_M0_20261117_190829.db data\radar.db -Force
# 回滚代码：删除 migrations/ server/security.py server/auth_routes.py
#   并 revert server/main.py 的 CORS/中间件/feed 段（audit.md 保留了原始行为描述）
```
