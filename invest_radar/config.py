# -*- coding: utf-8 -*-
"""
投资雷达 · 默认配置（开源版）

═══════════════════════════════════════════════════════════════
  两种改法，选一个：
═══════════════════════════════════════════════════════════════

  方式 A（推荐，不影响上游更新）：
      复制本文件为 config.local.py，改那个文件
      config.local.py 已在 .gitignore 里，不会被提交
      本文件末尾的加载逻辑会自动覆盖同名变量

  方式 B（简单粗暴）：
      直接改这个文件。但以后 git pull 上游更新时会冲突

═══════════════════════════════════════════════════════════════

第一次使用：
  1. 把你的股票填进 WATCHLIST（或 config.local.py）
  2. thesis 写清「这票靠什么赚钱、你盯什么变量」
     —— 这是整套系统最重要的一句话，AI 每次解读都会拿它当标尺
  3. 跑 `python -m invest_radar.universe` 拉全市场名单
  4. 跑 `python -m invest_radar --board` 看第一版看板
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
OUT_DIR = ROOT / "out"
DATA_DIR.mkdir(exist_ok=True)
OUT_DIR.mkdir(exist_ok=True)


# ============ 监控清单（示例，改成你自己的）============
# code    : 6 位股票代码
# name    : 你的叫法，跟交易所简称不一样也没关系
# alias   : 别名，新闻里出现这些词也算命中
# role    : 核心 / 观察 / 已清仓
# keywords: 这只票的关键词，会叠加到 GLOBAL_KEYWORDS
# thesis  : ★ 投资逻辑（一句话说清怎么赚钱、盯什么变量）
#           写不好就先空着，但写了之后 AI 判断质量会完全不同
WATCHLIST = [
    {
        "code": "600519",
        "name": "贵州茅台",
        "alias": ["茅台", "贵州茅台"],
        "role": "核心",
        "keywords": ["白酒", "批价", "动销", "经销商", "i茅台"],
        "thesis": "高端白酒龙头，批价与渠道库存是主变量；预收款反映需求强弱",
    },
    {
        "code": "000001",
        "name": "平安银行",
        "alias": ["平安银行", "平银"],
        "role": "观察",
        "keywords": ["净息差", "不良率", "零售", "拨备"],
        "thesis": "零售转型银行，净息差与资产质量是主变量；关注不良生成率拐点",
    },
]


# ============ 全局关键词（所有票都会匹配）============
GLOBAL_KEYWORDS = [
    # 风险类 —— 命中就红色标记
    "减持", "质押", "问询", "立案", "处罚", "警示函", "诉讼", "仲裁",
    "停产", "事故", "爆炸", "泄漏", "召回", "商誉减值", "计提", "下修",
    "亏损", "预减", "预亏", "退市", "ST", "违规", "担保", "债务",
    # 机会类 —— 命中就绿色标记
    "中标", "订单", "增持", "回购", "涨价", "提价", "扩产", "投产",
    "预增", "扭亏", "分红", "中标通知", "战略合作", "并购", "重组",
    "产能", "涨价函", "供不应求", "突破",
]

# 风险关键词（用于分级，比 GLOBAL_KEYWORDS 更严格）
RISK_KEYWORDS = {
    "减持", "质押", "问询", "立案", "处罚", "警示函", "诉讼", "仲裁",
    "停产", "事故", "爆炸", "泄漏", "召回", "商誉减值", "计提", "下修",
    "亏损", "预减", "预亏", "退市", "ST", "违规", "担保", "债务",
}


# ============ 抓取参数 ============
NEWS_DAYS = 30          # 新闻回溯天数
NOTICE_DAYS = 30        # 公告回溯天数
HIST_DAYS = 250         # 算一年高低点用的天数

# 抓取节流（重要：不要调小，否则会被数据源封 IP）
EM_MIN_INTERVAL = 1.2   # 东方财富请求最小间隔（秒）
REQUEST_TIMEOUT = 20    # 单次请求超时


# ============ 推送（可选，留空就不推）============
# 企业微信群机器人 webhook
WECHAT_WEBHOOK = ""
# 飞书自定义机器人 webhook
FEISHU_WEBHOOK = ""
# Telegram: ("bot_token", "chat_id")
TELEGRAM = ("", "")


# ============ 告警阈值 ============
ALERT = {
    "pct_change": 5.0,       # 单日涨跌超过 5% 提醒
    "volume_ratio": 2.0,     # 量比超过 2 提醒
    "position_high": 0.90,   # 处于一年 90% 分位以上提醒
    "position_low": 0.10,    # 处于一年 10% 分位以下提醒
}


# ============ 服务配置 ============
# 监听地址：127.0.0.1 = 只有本机能访问（配合 Tailscale Serve 给手机用）
#           0.0.0.0   = 同一 WiFi 下的设备能直接访问
HOST = "127.0.0.1"
PORT = 8000

# 允许的前端来源（浏览器 + Capacitor APK）
ALLOWED_ORIGINS = [
    "http://127.0.0.1:8000",
    "http://localhost:8000",
    "http://127.0.0.1:5173",
    "http://localhost:5173",
    "https://localhost",          # Capacitor WebView
    "capacitor://localhost",      # iOS Capacitor
]


# ═══════════════════════════════════════════════════════════════
#  本地配置覆盖（config.local.py）
# ═══════════════════════════════════════════════════════════════
#  如果你的关注池、阈值、推送地址不想公开，写在 config.local.py 里。
#  这个文件不会被 git 跟踪，上游更新 config.py 时也不会冲突。
# ═══════════════════════════════════════════════════════════════
_LOCAL_CONFIG = Path(__file__).resolve().parent / "config.local.py"

LOCAL_CONFIG_LOADED = False
LOCAL_CONFIG_ERROR = ""

if _LOCAL_CONFIG.exists():
    try:
        _ns = {
            "__file__": str(_LOCAL_CONFIG),
            "__name__": "config.local",
        }
        exec(compile(_LOCAL_CONFIG.read_text(encoding="utf-8"),
                     str(_LOCAL_CONFIG), "exec"), _ns)
        for _key, _val in _ns.items():
            if _key.isupper() and not _key.startswith("_"):
                globals()[_key] = _val
        LOCAL_CONFIG_LOADED = True
    except Exception as _exc:      # noqa: BLE001
        LOCAL_CONFIG_ERROR = str(_exc)
