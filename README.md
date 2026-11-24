# 投资雷达 · Investment Radar

> 跑在自己电脑上的个人 AI 投研终端。数据不出本机，AI 用你自己的 Key，手机通过 Tailscale 访问。

**一句话**：本地抓 A 股数据 → 存 SQLite → FastAPI 出接口 → 手机 PWA / APK 使用 → DeepSeek 驱动的交易员模式 AI 解读。

---

## 它解决什么问题

散户每天面对的信息是碎的：

- 公告发在巨潮，新闻散在东财，互动问答藏在互动易，研报在券商 App
- 看完之后**串不起来**：「这条公告对我当初买它的理由，到底是支持还是削弱？」
- 换台设备就找不到之前的研究记录

这个项目的做法：

```
拉全市场数据 → 只盯你关注的几只 → 每条信息标注级别
                            ↓
            注入你自己写的投资逻辑（thesis）
                            ↓
        AI 回答：「这条消息跟你的逻辑什么关系」
                            ↓
              研究记录留档，可回看、可复盘
```

**核心设计：thesis 注入。** 你给每只票写一句「靠什么赚钱、盯什么变量」，AI 每次解读都拿这句话当标尺。没有 thesis，AI 只能告诉你「这是条公告」；有 thesis，它才能说「这动了你的主变量」。

---

## 功能

### 数据层（全本地，无需任何 API 付费）

| 数据 | 来源 |
|---|---|
| 全 A 股名单（5580 只，含拼音搜索） | 东方财富 |
| 实时行情（开高低收/换手/量比/振幅/PE/PB） | 腾讯 |
| 日/周/月 K + 5/15/30/60 分钟 K | 腾讯 + 东方财富 |
| 分时 / 5 日分时 | 腾讯 |
| 公告 | 巨潮资讯 |
| 互动易问答 | 巨潮 |
| 研报 | 东方财富 |
| 龙虎榜 / 两融 / 解禁 / 股东户数 | 东方财富 |
| 期货（沪铜等，用于有色股主变量） | 新浪期货 |

### AI 功能（DeepSeek，每用户自己的 Key）

| 功能 | 说明 |
|---|---|
| **词条解读** | 七段结构：核心结论 / 已核实事实（带来源）/ 潜在影响 / 多空因素 / 对 thesis 的影响 / 待核查 / 失效条件 |
| **多轮追问** | 带词条+行情+thesis 上下文 |
| **多空辩论** | 看多研究员 → 看空研究员 → 交易员裁决（借鉴 TradingAgents 结构） |
| **全局 RAG 助手** | 检索你的关注池+词条库+外部信息 |
| **每日晨报** | 每股现状 + 近 24h 要点 + 今日观察点 |
| **月度复盘** | 按时间顺序回顾，不事后伪装 |
| **今日研究建议** | 从近期信息里挑最值得深挖的三件事 |

**AI 规则**：证据优先、事实与推断分离、允许说「资料不足」、不编造概率和价位。

### 其他

- **资讯管理**：未读 / 待核查 / 稍后研究 / 已处理 / 忽略
- **Thesis 版本史**：每次修改记录旧值、新值、原因，改动后 AI 缓存自动失效
- **研究笔记**：自己的思考留档，可搜索
- **数据新鲜度**：六态标注（实时/延迟/过期/失败/缺失/未知），AI 上下文也带时间
- **共享行情轮询**：多个设备连接不重复抓上游（防封 IP）
- **三级通知**：P1 立即 / P2 汇总 / P3 仅入库

---

## 快速开始

```bash
git clone <本仓库地址>
cd investment-radar
```

### 1. 环境要求

| 项目 | 版本 |
|---|---|
Python | 3.11+（推荐 3.12） |
Node.js | 20+（仅构建前端需要） |
操作系统 | Windows / macOS / Linux |

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

<details>
<summary>手动安装（如果 requirements.txt 不可用）</summary>

```bash
pip install fastapi uvicorn httpx requests pandas akshare pypinyin pillow pypdf python-dotenv
```
</details>

### 3. 配置

```bash
cp .env.example .env
```

编辑 `.env`，填入你自己的 DeepSeek Key（[获取地址](https://platform.deepseek.com/api_keys)）：

```bash
DEEPSEEK_API_KEY=sk-你的key
```

> **也可以不填**：启动后在 App 的「我的设置」里填，每个用户各自独立。

### 4. 改成你自己的股票

编辑 `invest_radar/config.py` 的 `WATCHLIST`：

```python
WATCHLIST = [
    {
        "code": "600519",
        "name": "贵州茅台",
        "role": "核心",
        "keywords": ["白酒", "批价", "动销"],
        "thesis": "高端白酒龙头，批价与渠道库存是主变量",   # ← 最重要
    },
]
```

### 5. 初始化数据

```bash
python -m invest_radar.universe      # 拉全市场名单（约 1 分钟）
```

### 6. 启动

```bash
# Windows
启动服务.bat

# 或手动
python -m uvicorn server.main:app --host 127.0.0.1 --port 8000
```

浏览器打开 http://127.0.0.1:8000

**第一次进入**：输入一个名字（如「我自己」），系统自动创建账户，**没有密码**。之后浏览器会记住 30 天。

---

## 手机访问

有三种方式，按你的需求选。

### 方式 A：Tailscale（推荐，免费、安全、地址固定）

Tailscale 把你的设备组成一个私有网络，手机可以直接访问电脑上的服务，**不用把电脑暴露到公网**。

**1. 电脑和手机都装 Tailscale**
- 电脑：https://tailscale.com/download
- 手机：应用商店搜 Tailscale

**2. 两台设备登录同一个账号**

**3. 电脑上开启 HTTPS 服务**

```bash
tailscale serve --bg 8000
```

会输出一个地址，形如：

```
https://你的设备名.你的tailnet名.ts.net
```

**4. 手机浏览器打开这个地址**

> **第一次打开可能很慢**：Let's Encrypt 证书签发需要 10-30 秒。

**5. 加到主屏**（iPhone Safari / Android Chrome 菜单 → 添加到主屏幕），之后像 App 一样用。

**注意**：
- 手机必须开着 Tailscale App
- 部分国产手机（小米/红米）需要把「私人 DNS」设为**自动**，否则 `.ts.net` 域名解析会被劫持

### 方式 B：局域网（同一 WiFi，最快）

电脑启动时监听 `0.0.0.0`：

```bash
python -m uvicorn server.main:app --host 0.0.0.0 --port 8000
```

查本机 IP：

```bash
# Windows
ipconfig | findstr IPv4

# macOS / Linux
ifconfig | grep "inet "
```

手机浏览器打开 `http://你的内网IP:8000`。

**缺点**：只能在同一个 WiFi 下用；HTTP 明文，不适合在外网暴露。

### 方式 C：Cloudflare Tunnel（临时外网）

适合临时给别人看：

```bash
# 下载 cloudflared 到 tools/ 目录
tools\cloudflared.exe tunnel --url http://127.0.0.1:8000
```

会生成一个 `xxx.trycloudflare.com` 临时地址。**每次重启地址会变。**

---

## 打包成 Android APK

<details>
<summary>点击展开（需要 Android Studio）</summary>

### 前置

- Android Studio（约 4GB 下载）
- Android SDK（约 6GB）
- JDK 21

### 步骤

```bash
cd web
npm install
npm run build

npx cap add android
npx cap sync android
npx cap open android
```

Android Studio 打开后：

1. 连接手机（开启 USB 调试）
2. 点 Run 测试
3. `Build → Build Bundle(s) / APK(s) → Build APK(s)`

**APK 里要填你自己的 API 地址**：App 首次打开会引导填写，或在 `web/src/env.js` 里构建时注入：

```bash
VITE_API_BASE=https://你的地址 npm run build
```

</details>

---

## 架构

```
┌─────────────────────────────────────────────┐
│  你的电脑                                    │
│                                             │
│  invest_radar/          数据层               │
│    fetcher.py    多源抓取（腾讯优先，防封）    │
│    store.py      SQLite + FTS5              │
│    klinefetch.py 9 周期 K线                 │
│    websearch.py  巨潮全文 + 东财快讯         │
│    watcher.py    轮询 + 三级通知             │
│                                             │
│  server/                API 层               │
│    main.py       FastAPI + SSE              │
│    identity.py   用户身份（名字登录）          │
│    quotes.py     共享行情轮询                 │
│    llm/          DeepSeek 异步客户端          │
│                                             │
│  web/                   前端                 │
│    Vue 3 + Vite + klinecharts               │
│                                             │
│  data/radar.db          SQLite              │
└─────────────────────────────────────────────┘
              ↑                    ↑
        浏览器访问             手机 Tailscale
```

### 目录说明

```
investment-radar/
├── invest_radar/          数据抓取与存储
│   ├── config.py          ★ 改这个文件
│   ├── fetcher.py         多源抓取（代理绕过 + 限流）
│   ├── store.py           SQLite 层
│   ├── analyzer.py        打分 / 趋势 / 估值
│   ├── klinefetch.py      K线 9 周期
│   ├── watcher.py         轮询 + 告警
│   └── websearch.py       巨潮 + 东财检索
├── server/
│   ├── main.py            FastAPI 路由
│   ├── identity.py        用户身份
│   ├── quotes.py          共享行情轮询
│   └── llm/
│       ├── client.py      DeepSeek 异步客户端
│       └── prompts.py     提示词（交易员模式）
├── web/                   Vue 前端源码
├── web_build/             构建产物（服务托管这里）
├── migrations/            数据库迁移
├── scripts/               备份、工具
└── data/                  SQLite 数据库（已 gitignore）
```

---

## 关键设计说明

### 为什么优先用腾讯数据源

东方财富会对高频请求做 IP 限流（`Push2RateLimitError`），腾讯接口宽松得多。代码里的优先级是：

```
腾讯（行情/K线）> 巨潮（公告）> 东方财富（研报/筹码，串行 + 1.2s 间隔）
```

**不要调小 `EM_MIN_INTERVAL`**，否则会被封。

### 为什么共享行情轮询

如果每个浏览器标签页/每台手机各自轮询，3 台设备 × 4 个页面 = 12 倍上游请求，很快会被封。

代码里是**中心轮询 + 广播**：只有一个任务在抓，所有客户端订阅同一个结果。

### 为什么 AI 缓存带版本号

缓存键 = `entry_id + 模型 + 提示词版本 + thesis 哈希`

你改了 thesis，或者我升级了提示词，旧缓存自动失效。**不会出现「改了逻辑还看到旧分析」的情况。**

### 数据新鲜度六态

```
fresh    正常（行情 60 秒内）
delayed  有延迟（30 分钟内）
stale    已过期
failed   最近抓取失败
missing  没有数据
unknown  时间无法确认
```

**抓取失败不覆盖旧的有效数据**，UI 和 AI 上下文都会标注数据时间。

---

## 常见问题

<details>
<summary><b>启动报 WinError 10048 / 端口被占用</b></summary>

有僵尸进程占着 8000：

```powershell
# Windows
Get-NetTCPConnection -LocalPort 8000 | Select-Object OwningProcess
Stop-Process -Id <上面查到的PID> -Force
```

`启动服务.bat` 已内置清理逻辑。
</details>

<details>
<summary><b>抓数据全部失败 / SSL 报错</b></summary>

检查是否开了系统代理（Clash/V2Ray 等）。国内数据源（巨潮、东财、腾讯）走代理会失败。

代码里已经做了 `trust_env=False` + 剥离代理环境变量，但如果代理软件开了「TLS 解密/MITM」仍会干扰。**抓数据时关掉代理的 MITM 功能。**
</details>

<details>
<summary><b>手机打不开 ts.net 地址</b></summary>

1. 手机 Tailscale App 是否在线
2. 电脑 `tailscale serve status` 是否正常
3. **小米/红米**：设置 → 网络 → 私人 DNS → 改为「自动」
4. 等 30 秒（首次证书签发慢）
</details>

<details>
<summary><b>AI 返回「LLM 未配置」</b></summary>

`.env` 里没填 Key，或者填错了。检查：

- 是否以 `sk-` 开头
- 是否超过 20 个字符
- 是否全是 ASCII 字符（不能有中文）

也可以在 App 的「我的设置」里填，会存到数据库按用户隔离。
</details>

<details>
<summary><b>改了 thesis 但 AI 还是旧答案</b></summary>

正常设计是自动失效。如果没生效，检查 `thesis_history` 表是否有记录，或强制重新生成（详情页点「重跑」）。
</details>

---

## 技术栈

| 层 | 技术 |
|---|---|
后端 | FastAPI + uvicorn + httpx |
数据库 | SQLite（WAL 模式）+ FTS5（trigram 分词） |
前端 | Vue 3 + Vite + klinecharts@9 |
AI | DeepSeek（OpenAI 兼容协议） |
数据 | akshare + 腾讯 + 巨潮 + 东方财富 + 新浪 |
部署 | Windows 本地 + Tailscale Serve |

---

## 免责声明

**本项目仅供个人研究与学习使用。**

- 所有 AI 输出**不构成投资建议**
- 数据来自公开渠道，可能存在延迟或错误，**以交易所官方披露为准**
- 抓取频率已做限制，请勿修改为高频请求，避免给对方服务器造成压力
- 投资有风险，决策请自行判断

---

## License

MIT
