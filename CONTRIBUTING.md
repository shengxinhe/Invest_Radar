# 贡献指南

## 报告问题

开 Issue 时请包含：

- 操作系统和 Python 版本
- 复现步骤
- 完整报错信息（**先删掉里面的 API Key**）
- 相关日志（`out/` 目录）

## 提交代码

```bash
git checkout -b feature/你的功能
# 改代码
git commit -m "feat: 说明改了什么"
git push origin feature/你的功能
```

然后开 Pull Request。

## 代码约定

### 数据抓取（重要）

- **新数据源要优先考虑防封**：串行 + 间隔 ≥1 秒
- 东方财富必须走 `fetcher.em_get()`（内置限流），不要直接 `requests.get`
- 加新数据源前先确认：是否已有更宽松的来源？腾讯 > 巨潮 > 东财

### AI 提示词

- 改 `server/llm/prompts.py` 后**必须 bump `PROMPT_VERSION`**，否则旧缓存不会失效
- 提示词要遵守三条底线：
  1. 事实与推断分离，事实标来源
  2. 资料缺失要直说，不编造
  3. 允许输出「资料不足」

### 数据库

- 改表结构必须走 `migrations/`，写新文件 `009_xxx.py`
- **不要直接改 `data/radar.db`**
- 迁移脚本必须幂等（重复执行不报错）

### 前端

- 样式变量只在 `web/src/styles/tokens.css` 定义
- 组件不写全局变量
- 移动端优先（375px 宽度先测试）

## 不要提交

以下内容已在 `.gitignore`，但仍请确认：

- `.env`（含 API Key）
- `data/`（个人持仓数据）
- `out/`（你的研究记录）
- `invest_radar/monitor_*.py`（个人监控策略）

## 测试

```bash
python tests/test_acceptance.py
```

覆盖：安全 / 数据库 / API / 分页 / 行情 / AI / 备份 / PWA / 运维
