# M7 · 最终验收报告

> 完成时间：2026-11-17 20:50 ｜ 投资雷达 2.0 升级至此**全部完成**

---

## 最终全链路验收：32/32 通过

```
【安全】        未登录401 / health脱敏 / CORS白名单拒绝evil域 / 会话持久化      ✓×4
【数据库】      integrity ok / 28张表 / 5个迁移 / 6个FTS触发器 / FTS可检索      ✓×6
【核心API】     13 个关键端点全 200                                             ✓×13
【Feed分页】    4页89条无重复（M1修复持续有效）                                  ✓×1
【行情轮询】    polls=6 errors=0 共享模式运行                                   ✓×1
【AI用量】      缓存4/对话11轮/28条消息/分模型统计                              ✓×1
【备份】        7份备份全完整（含5次迁移前置）                                  ✓×2
【PWA】         / 与 /sw.js 与 manifest 可达                                    ✓×3
```

**验收过程中发现并修复 2 项**：
1. FTS 测试用词「担保」只有 2 字——trigram 最小 3 字符，`会计师/事务所/中金岭南` 都正常命中。这是预期行为（<3 字走 LIKE 兜底），修的是测试不是产品。
2. `/api/ai/status` 404——1.0 遗留端点在 M2 重构时被并入 usage，已补兼容端点。

---

## 2.0 全程交付总览（M0-M7）

| 阶段 | 核心交付 | 报告 |
|---|---|---|
M0 | 8 项审计全部属实留证 / DB 回滚点 | audit.md |
M1 | 认证+登录页 / CORS 收敛 / 127.0.0.1 / feed 复合 keyset / FTS trigram+6触发器 / 新鲜度六态 / 备份恢复演练 | M1-REPORT |
M2 | httpx 异步 / 缓存版本化 / 七段结构 / 取消强制概率 / 注入防护 / SSE 统一协议 | M2-REPORT |
M3 | CSS 三层拆分 / 首页驾驶舱（真实大盘+AI研究建议）/ 组件库 / 搜索竞态 / Session 落库 | M3-REPORT |
M4 | 详情五区 / 资讯六态管理 / thesis 历史版本 | M4-REPORT |
M5 | 共享行情轮询（3连接仍1次上游）/ SSE 生命周期 / 微信三级通知 | M5-REPORT |
M6 | 研究笔记 / 报告归档+导出 / 月度复盘（严格时间序） | M6-REPORT |
M7 | 32 项全链路验收 / 兼容端点 / 个股页复盘入口 / 辩论归档 | 本文档 |

**数据库迁移轨迹**：5 个版本化迁移（001 FTS / 002 缓存版本 / 003 状态+历史 / 004 Session / 005 研究），全程零数据丢失，每次迁移前置备份。

## 本轮新增

```
server/main.py        +/api/ai/status 兼容端点；辩论归档到 research_report
web/StockView.vue     逻辑 tab + 月度复盘按钮（SSE 流式，自动归档）
tests/test_m7_final.py  32 项验收脚本（可重复执行）
```

---

# OPTIMIZATION_REPORT · 优化总结

## 修复的 8 项审计问题（全部闭环）

| # | 问题 | 修复 | 验证 |
|---|---|---|---|
1 | Feed 分页重复 | SQL 端复合 keyset（lv:tp:ts:id 四段游标） | 翻页无重复无遗漏 ✓ |
2 | FTS 索引空壳 | trigram 重建 + 6 触发器 + LIKE 兜底 | CRUD 全链路命中 ✓ |
3 | 认证缺失 | scrypt 口令 + 签名 Session + 限流 + CORS 白名单 + 127.0.0.1 | 8 接口 401 / evil 域拒绝 ✓ |
4 | AI 缓存无版本 | cache_key = entry+model+prompt+thesis_hash | thesis 改动即失效 ✓ |
5 | LLM 阻塞事件循环 | httpx.AsyncClient + 信号量 + 错误分类 | 并发墙钟 < 串行和 ✓ |
6 | SSE 重复抓上游 | 中心轮询 + 广播订阅 | 3 连接仍 1 次轮询 ✓ |
7 | CSS 变量覆盖 | tokens/theme/components 三层，删 style.css | 0 重复定义 ✓ |
8 | 前端竞态 | useSearch / useQuoteStream / AbortController 全覆盖 | 组件卸载即取消 ✓

## 系统能力增量

- **安全**：裸奔 → 完整认证体系（口令/Session/限流/CORS/监听收敛）
- **AI**：合规机器人 → 交易员模式（有判断有依据）→ 证据优先（七段/事实推断分离/允许不确定）
- **研究**：一次性解读 → 长期记忆（笔记/报告归档/thesis 版本史/月度复盘）
- **行情**：每连接独立抓 → 共享轮询（上游请求量与连接数解耦）
- **数据可信**：无时间概念 → 六态新鲜度全标注（UI+AI 上下文）
- **推送**：关键词一把抓 → 三级分级+去重+配额

## 关键数字（验收时点）

```
数据：5580 股票 / 231 词条 / 4 关注 / 28 张表 / 5 迁移 / 7 备份
API：50+ 路由（含 3 个 SSE 流式）
前端：346KB JS / 28KB CSS（gzip 105KB + 5.9KB）
测试：M1 分页 7 用例 + M1 认证矩阵 + M2 AI + M4 状态 6 用例 + M5 通知 + M7 全链路 32 项
成本：解读 0.001 元/次（缓存后 0），月度复盘 ~0.01 元/次
```

## 已知边界（如实记录）

1. **微信三级分流**：notify 分级与配额已实现并记录到 notification_log，但 DSH schedule 提示词仍按旧行为推送全部告警——需用户确认后改 schedule 提示词读 `priority` 字段
2. **Session Cookie SameSite=Lax**：单用户场景足够；如未来暴露到不可信网络需升级 CSRF token
3. **行业字段**：腾讯接口未提供，详情页显示「行业未收录」——可后续从东财 F10 补
4. **东财个股新闻接口**：官方已废弃（1.0 已知），小票以公告+互动为主，UI 已如实标注
5. **K线 overlay**：切周期重建逻辑沿用 1.0，M7 未发现异常，长时使用待观察

## 回滚手册

```powershell
# 停服
Get-Process python | ? { $_.CommandLine -match 'uvicorn' } | Stop-Process -Force
# 数据库回滚（任选备份点）
Copy-Item data\backups\radar_premigrate_20261117_203317.db data\radar.db -Force
# 代码回滚：git（本项目无 git，按 M1-M7 报告的文件清单手动回退）
# 重启
python -m uvicorn server.main:app --host 127.0.0.1 --port 8000
```

---

**投资雷达 2.0 交付完毕。**
稳定（32 项验收）、安全（认证+CORS+限流）、精致（三层设计系统）、移动优先（驾驶舱首页+五区详情）、有长期研究记忆（笔记+归档+复盘）。

*所有 AI 输出仅供研究参考，不构成投资建议。*
