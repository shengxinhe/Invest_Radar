# 借鉴与致谢 / Credits

本项目站在很多开源项目的肩膀上。下面如实说明**哪些是借鉴的、哪些是自己写的**，以及每一处借鉴的来源。

---

## 一、架构与设计思路的借鉴

### 1. TradingAgents — 多空辩论结构 ★ 核心借鉴

**来源**：[TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents)（Apache-2.0）

**借鉴了什么**：

多智能体辩论的**流程结构**：

```
分析员产出观点 → 多空双方各自论证 → 裁决者综合判断
```

本项目的 `多空辩论` 功能（`server/main.py` 的 `/api/stock/{code}/debate`）直接采用这个三段式：

1. **看多研究员**（`BULL_SYSTEM`）——只准找支持证据
2. **看空研究员**（`BEAR_SYSTEM`）——刻意挑剔
3. **交易员裁决**（`JUDGE_PROMPT`）——判断哪方更有说服力

**没有借鉴的部分**（重要）：

| TradingAgents 的做法 | 本项目的做法 |
|---|---|
基于 LangGraph + LangChain 的多智能体框架 | 纯 asyncio 顺序调用，无框架依赖 |
yfinance 获取美股数据 | 腾讯/巨潮/东财获取 A 股数据 |
38 个 Python 依赖 | 10 个依赖 |
内置回测与记忆模块 | 无回测，用 `thesis_history` 做研究记忆 |
美股市场 | A 股市场（含中文分词、龙虎榜、互动易） |

**为什么只借结构**：TradingAgents 的数据层是美股导向（yfinance），A 股的公告体系（巨潮）、互动平台（互动易）、筹码数据（龙虎榜/两融/解禁）它都没有。直接引入框架反而要写大量适配层。

代码中的标注位置：
- `server/main.py:1152` — 注释 `# ---------------- 多空辩论（借鉴 TradingAgents） ----------------`
- `README.md:55` — 功能表格中标注

---

### 2. Bloomberg 终端 — 信息密度与布局参考

**来源**：[Bloomberg Terminal](https://www.bloomberg.com/professional/solution/bloomberg-terminal/)（商业产品，非开源）

**借鉴了什么**：只有**设计理念**，没有代码。

- 深色背景 + 高信息密度
- 数据优先，装饰最少
- 价格变动用颜色区分（本项目按 A 股习惯：涨红跌绿）

**未借鉴**：任何功能、界面元素、数据结构。

---

### 3. 自托管个人工具的设计模式

**来源**：这一类项目的通用做法，非特定项目

- 数据完全本地（SQLite 单文件）
- 不做多租户 SaaS，一人一套
- 用 Tailscale 而非公网暴露
- API Key 存在本地 `.env`

这类思路见于很多 self-hosted 项目（如 [Hoarder](https://github.com/hoarder-app/hoarder)、[Linkwarden](https://github.com/linkwarden/linkwarden) 的部署哲学），但没有复制它们的代码。

---

## 二、核心依赖（10 个）

这些是项目能跑起来的基础，**全部是开源库**：

| 库 | 用途 | License |
|---|---|---|
[FastAPI](https://github.com/tiangolo/fastapi) | Web 框架 + SSE | MIT |
[uvicorn](https://github.com/encode/uvicorn) | ASGI 服务器 | BSD-3 |
[httpx](https://github.com/encode/httpx) | 异步 HTTP（LLM 调用） | BSD-3 |
[requests](https://github.com/psf/requests) | 同步 HTTP（数据抓取） | Apache-2.0 |
[pandas](https://github.com/pandas-dev/pandas) | 数据处理 | BSD-3 |
[akshare](https://github.com/akfamily/akshare) | A 股数据接口集合 | MIT |
[pypinyin](https://github.com/mozillazg/python-pinyin) | 汉字转拼音（搜索用） | MIT |
[Pillow](https://github.com/python-pillow/Pillow) | 图标生成 | HPND |
[pypdf](https://github.com/py-pdf/pypdf) | 财报 PDF 解析 | BSD-3 |
[python-dotenv](https://github.com/theskumar/python-dotenv) | 环境变量加载 | BSD-3 |

---

## 三、前端依赖

| 库 | 用途 | License |
|---|---|---|
[Vue 3](https://github.com/vuejs/core) | 前端框架 | MIT |
[Vite](https://github.com/vitejs/vite) | 构建工具 | MIT |
**[klinecharts](https://github.com/klinecharts/KLineChart)** | K 线图表 | Apache-2.0 |

### klinecharts 的特别说明

K 线模块（`web/src/components/kline/`）**没有自己画图**，全部基于 klinecharts：

- 图表渲染、缩放、十字光标 —— 用 klinecharts 的 API
- 本项目只写了：数据获取层（`invest_radar/klinefetch.py`）、周期切换 UI、与后端 MA 计算对接

如果你也用 A 股 K 线，强烈推荐这个库。

---

## 四、数据来源（非代码借鉴，但必须致谢）

**这些是公开数据接口，本项目只做只读访问，遵守其使用条款并做了限流。**

| 来源 | 提供什么 | 本项目做法 |
|---|---|---|
**腾讯行情** `qt.gtimg.cn` | 实时行情、K 线、分时 | 主数据源，IP 友好 |
**巨潮资讯** `cninfo.com.cn` | 公告、互动易问答、全文搜索 | 官方披露，最权威 |
**东方财富** `eastmoney.com` | 研报、龙虎榜、两融、解禁、股东户数 | **串行 + ≥1.2s 间隔**，防封 |
**新浪财经** | 期货行情（沪铜等） | 用于有色股主变量跟踪 |
**AKShare** | 封装部分上述接口 | 作为备用路径 |

⚠️ **重要提示**：

- 所有数据**仅供个人研究**，不可用于商业分发
- 本项目已做请求限流（`EM_MIN_INTERVAL = 1.2`），**请勿改小**
- 数据可能有延迟或错误，**以交易所官方披露为准**

---

## 五、AI 能力

| 项 | 说明 |
|---|---|
**模型** | [DeepSeek](https://platform.deepseek.com/)（deepseek-chat / deepseek-reasoner） |
**协议** | OpenAI 兼容 API |
**提示词** | **本项目原创**，见 `server/llm/prompts.py` |
**客户端** | 本项目用 httpx 手写异步 SSE 解析（未用 OpenAI SDK） |

### 提示词的来源

`server/llm/prompts.py` 里的七段结构、交易员模式规则、注入防护，都是本项目自己写的。

其中「事实与推断分离」「允许说资料不足」这两条原则，参考了金融研究写作的通行规范（卖方研报的信息披露标准），**不是从某个开源项目复制的**。

---

## 六、其他技术选择

| 项 | 来源 | 说明 |
|---|---|---|
**SQLite FTS5 + trigram** | SQLite 官方特性 | trigram 分词是 SQLite 3.34+ 内置能力 |
**复合 keyset 分页** | 数据库通用模式 | 非特定项目 |
**SSE（Server-Sent Events）** | W3C 标准 | 非特定项目 |
**Tailscale Serve** | [Tailscale](https://tailscale.com/)（商业服务，免费额度够用） | 提供 HTTPS + 私有网络 |
**Capacitor** | [ionic-team/capacitor](https://github.com/ionic-team/capacitor)（MIT） | 可选，打包 APK 用 |

---

## 七、明确**没有**借鉴的项目

| 项目 | 为什么没用 |
|---|---|
**[OpenBB](https://github.com/OpenBB-finance/OpenBB)** | 数据层与 A 股不匹配。本项目的腾讯/巨潮/东财数据源是逐项调试出来的（含代理绕过、限流、GBK 编码处理），换成 OpenBB 要重写全部适配 |
**[FinceptTerminal](https://github.com/Fincept-Corporation/FinceptTerminal)** | C++/Qt6 桌面应用，与本项目 Web/PWA 形态完全相反；AGPL 协议也有传染性 |
**[qlib](https://github.com/microsoft/qlib)** | 量化回测框架，本项目是「信息分析工具」不是「策略回测」，需求不同 |
**[TradingAgents](https://github.com/TauricResearch/TradingAgents)** | 只借用辩论结构，未引入框架（原因见上文） |

---

## 八、如果你要使用本项目的代码

MIT 协议，随便用。但请：

1. **遵守数据源的条款**——限流不要调小，不要高频抓取
2. **AI 输出不构成投资建议**——这是写进 LICENSE 的
3. **如果二次分发，保留本文件**——让下一个人也知道该感谢谁

---

## 九、如何补充这份文档

如果你发现本项目某处借鉴了未列出的项目，请开 Issue 或 PR 指出。**这份文档的目标是诚实，不是好看。**
