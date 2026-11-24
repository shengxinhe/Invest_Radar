# -*- coding: utf-8 -*-
"""
数据抓取层 V2 —— 按 a-stock-data skill 的源优先级重构：
  腾讯(行情/估值，不封IP) > 巨潮(公告) > 东财(限流，只用独有数据)

所有东财请求走 em_get()，串行 + 1s 间隔 + 复用会话。
任何单源失败都不影响整体。
"""
import os
import random
import time
import urllib.request
import warnings
from datetime import datetime, timedelta

import pandas as pd
import requests

warnings.filterwarnings("ignore")

from . import config

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"

# ---------------- 代理绕过 ----------------
# 国内数据源（巨潮/东财/腾讯）走本地翻墙代理会 SSL 断连或超时。
# 策略：显式禁用环境代理，全部直连。如确实需要代理，设 config.USE_PROXY=True。
_BYPASS_PROXY = not getattr(config, "USE_PROXY", False)


def _mk_session():
    s = requests.Session()
    s.headers.update({"User-Agent": UA})
    if _BYPASS_PROXY:
        s.trust_env = False          # 忽略 HTTP_PROXY / HTTPS_PROXY
        s.proxies = {"http": None, "https": None}
    return s


def _strip_proxy_env():
    """akshare 内部用 httpx/requests 会读环境变量，全局清掉"""
    if not _BYPASS_PROXY:
        return
    for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy",
              "ALL_PROXY", "all_proxy", "NO_PROXY", "no_proxy"):
        os.environ.pop(k, None)


_strip_proxy_env()

# ---------------- 东财限流 ----------------
EM_SESSION = _mk_session()
EM_MIN_INTERVAL = 1.2
_em_last = [0.0]


def em_get(url, params=None, headers=None, timeout=15, **kw):
    wait = EM_MIN_INTERVAL - (time.time() - _em_last[0])
    if wait > 0:
        time.sleep(wait + random.uniform(0.1, 0.4))
    try:
        return EM_SESSION.get(url, params=params, headers=headers, timeout=timeout, **kw)
    finally:
        _em_last[0] = time.time()


DATACENTER_URL = "https://datacenter-web.eastmoney.com/api/data/v1/get"


# 直连会话（忽略系统代理），非东财接口用它
_PLAIN = _mk_session()


def sess_get(url, **kw):
    kw.setdefault("timeout", 15)
    if _BYPASS_PROXY:
        kw["proxies"] = {"http": None, "https": None}
    return _PLAIN.get(url, **kw)


def sess_post(url, **kw):
    kw.setdefault("timeout", 15)
    if _BYPASS_PROXY:
        kw["proxies"] = {"http": None, "https": None}
    return _PLAIN.post(url, **kw)


def em_datacenter(report_name, columns="ALL", filter_str="", page_size=50,
                  sort_columns="", sort_types="-1"):
    params = {
        "reportName": report_name, "columns": columns, "filter": filter_str,
        "pageNumber": "1", "pageSize": str(page_size),
        "sortColumns": sort_columns, "sortTypes": sort_types,
        "source": "WEB", "client": "WEB",
    }
    try:
        r = em_get(DATACENTER_URL, params=params)
        d = r.json()
        if d.get("result") and d["result"].get("data"):
            return d["result"]["data"]
    except Exception:
        pass
    return []


def _log(m):
    """静默模式：M0 起不再打印，需要调试时设 config.DEBUG=True"""
    if getattr(config, "DEBUG", False):
        print(f"    {m}")


# ---------------- 腾讯行情 ----------------

def get_copper_futures(days=60):
    """
    M7: 沪铜期货行情（新浪期货，用于中金岭南等有色股的主变量跟踪）。
    返回 {latest, chg_5d, chg_20d, ma20, ma60, high_1y, low_1y, series}
    """
    import json as _json
    import re as _re
    try:
        r = sess_get(
            "https://stock2.finance.sina.com.cn/futures/api/jsonp.php/"
            "var%20_CU0=/InnerFuturesNewService.getDailyKLine?symbol=CU0",
            headers={"Referer": "https://finance.sina.com.cn"}, timeout=25)
        m = _re.search(r"\((\[.*\])\)", r.text, _re.S)
        if not m:
            return None
        data = _json.loads(m.group(1))
        if not data:
            return None
        series = [(x["d"], float(x["c"])) for x in data if x.get("c")]
        if len(series) < 2:
            return None
        closes = [c for _, c in series]
        latest = closes[-1]

        def _chg(n):
            return (latest / closes[-1 - n] - 1) * 100 if len(closes) > n else None

        def _ma(n):
            return sum(closes[-n:]) / n if len(closes) >= n else None

        return {
            "symbol": "沪铜主连",
            "latest": latest,
            "date": series[-1][0],
            "chg_1d": _chg(1),
            "chg_5d": _chg(5),
            "chg_20d": _chg(20),
            "ma20": _ma(20),
            "ma60": _ma(60),
            "high_1y": max(closes[-250:]) if len(closes) >= 250 else max(closes),
            "low_1y": min(closes[-250:]) if len(closes) >= 250 else min(closes),
            "series": series[-days:],
        }
    except Exception:
        return None


def get_quote(code):
    """腾讯行情：价格 + PE/PB/市值/换手率/涨跌停/量比。不封 IP。"""
    prefix = "sh" if code.startswith(("6", "9")) else ("bj" if code.startswith("8") else "sz")
    url = f"https://qt.gtimg.cn/q={prefix}{code}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        raw = urllib.request.urlopen(req, timeout=10).read().decode("gbk")
        vals = raw.split('"')[1].split("~")
        if len(vals) < 53:
            return None

        def f(i):
            try:
                return float(vals[i]) if vals[i] else 0.0
            except (ValueError, IndexError):
                return 0.0

        return {
            "code": code,
            "name": vals[1],
            "price": f(3),
            "prev_close": f(4),
            "open": f(5),
            "change_amt": f(31),
            "pct": f(32),
            "high": f(33),
            "low": f(34),
            "amount_wan": f(37),
            "turnover_pct": f(38),
            "pe_ttm": f(39),
            "amplitude_pct": f(43),
            "mcap_yi": f(44),
            "float_mcap_yi": f(45),
            "pb": f(46),
            "limit_up": f(47),
            "limit_down": f(48),
            "vol_ratio": f(49),
            "pe_static": f(52),
            "source": "tencent",
        }
    except Exception as e:
        _log(f"腾讯行情失败: {e}")
        return None


def get_kline(code, days=None):
    """腾讯日K，用于算均线和一年位置。"""
    days = days or config.HIST_DAYS
    prefix = "sh" if code.startswith(("6", "9")) else ("bj" if code.startswith("8") else "sz")
    start = (datetime.now() - timedelta(days=days * 2)).strftime("%Y-%m-%d")
    end = (datetime.now() + timedelta(days=5)).strftime("%Y-%m-%d")
    url = ("https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
           f"?param={prefix}{code},day,{start},{end},640,qfq")
    try:
        r = sess_get(url, headers={"User-Agent": UA}, timeout=15)
        d = r.json()
        data = d["data"][f"{prefix}{code}"]
        rows = data.get("qfqday") or data.get("day") or []
        if not rows:
            return None
        df = pd.DataFrame([{
            "date": x[0], "open": float(x[1]), "close": float(x[2]),
            "high": float(x[3]), "low": float(x[4]), "volume": float(x[5]),
        } for x in rows])
        df["date"] = pd.to_datetime(df["date"])
        return df.sort_values("date").reset_index(drop=True).tail(days)
    except Exception as e:
        _log(f"腾讯K线失败: {e}")
        return None


def build_metrics(quote, kline):
    """把行情+K线合成判断指标"""
    if not quote:
        return None
    m = dict(quote)
    if kline is not None and len(kline) > 20:
        close = kline["close"]
        hi, lo = float(kline["high"].max()), float(kline["low"].min())
        c = m["price"] or float(close.iloc[-1])
        m["high_1y"] = hi
        m["low_1y"] = lo
        m["position"] = round((c - lo) / (hi - lo), 3) if hi > lo else 0.5
        m["ma20"] = round(float(close.tail(20).mean()), 2)
        m["ma60"] = round(float(close.tail(60).mean()), 2) if len(close) >= 60 else None
        m["above_ma20"] = c > m["ma20"]
        m["above_ma60"] = (c > m["ma60"]) if m["ma60"] else None
        m["kline"] = kline
    else:
        m.update({"high_1y": None, "low_1y": None, "position": 0.5,
                  "ma20": None, "ma60": None,
                  "above_ma20": None, "above_ma60": None})
    return m


# ---------------- 巨潮公告 ----------------

_cninfo_orgid_cache = {}


def _cninfo_orgid(code):
    """巨潮 orgId 动态查询（硬编码 gssx0{code} 对部分 601/000 失效）"""
    if code in _cninfo_orgid_cache:
        return _cninfo_orgid_cache[code]
    try:
        r = sess_get("http://www.cninfo.com.cn/new/data/szse_stock.json",
                         headers={"User-Agent": UA}, timeout=15)
        for it in r.json().get("stockList", []):
            if str(it.get("code")) == code:
                org = it.get("orgId")
                _cninfo_orgid_cache[code] = org
                return org
    except Exception:
        pass
    # fallback
    org = f"gssx0{code}"
    _cninfo_orgid_cache[code] = org
    return org


def get_notices(code, days=None):
    """巨潮公告全文检索（一次请求拿一页，不逐日扫）"""
    days = days or config.NOTICE_DAYS
    start = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    end = datetime.now().strftime("%Y-%m-%d")
    org = _cninfo_orgid(code)

    url = "http://www.cninfo.com.cn/new/hisAnnouncement/query"
    data = {
        "pageNum": "1", "pageSize": "50",
        "column": "szse", "tabName": "fulltext",
        "plate": "", "stock": f"{code},{org}",
        "searchkey": "", "secdate": "", "tdate": "",
        "type": "", "category": "",
        "trade": "", "seDate": f"{start}~{end}",
        "sortName": "", "sortType": "", "isHLtitle": "true",
    }
    try:
        r = sess_post(url, data=data,
                          headers={"User-Agent": UA,
                                   "Referer": "http://www.cninfo.com.cn/"},
                          timeout=20)
        j = r.json()
        out = []
        for it in (j.get("announcements") or []):
            ts = it.get("announcementTime")
            dt = datetime.fromtimestamp(ts / 1000).strftime("%Y-%m-%d") if ts else ""
            out.append({
                "date": dt,
                "title": str(it.get("announcementTitle", "")).replace("<em>", "").replace("</em>", ""),
                "type": it.get("announcementTypeName") or "",
                "url": "http://static.cninfo.com.cn/" + (it.get("adjunctUrl") or ""),
            })
        # 有的返回带 html 标签，清理
        return out
    except Exception as e:
        _log(f"巨潮公告失败: {e}")
        return []


# ---------------- 新闻（东财）----------------

def get_news(code, days=None, name=None):
    """
    个股新闻 + 市场快讯。

    现状（2026-11 实测）：
      - 东财 search-api-web 已废弃，只返回 passportWeb
      - akshare stock_news_em 走同端点，同样失效
      - 同花顺 basic.10jqka.com.cn/api/stockph/news 返回空
      - 东财 np-listapi 快讯可用，但个股命中率极低（800 条 0 命中）

    所以：返回两个东西
      - market: 全市场快讯（大盘背景，稳定可用）
      - stock:  个股新闻（当前基本为空，UI 上要如实说明）
    """
    days = days or config.NEWS_DAYS
    cutoff = datetime.now() - timedelta(days=days)

    market = []
    for page in range(1, 3):
        try:
            r = sess_get(
                "https://np-listapi.eastmoney.com/comm/web/getNewsByColumns",
                params={"client": "web", "biz": "web_news_col",
                        "column": "345", "order": "1", "needInteractData": "0",
                        "page_index": str(page), "page_size": "50",
                        "req_trace": "1",
                        "fields": "code,showTime,title,mediaName,summary,url"},
                headers={"Referer": "https://finance.eastmoney.com/"})
            items = (r.json().get("data") or {}).get("list") or []
        except Exception as e:
            _log(f"快讯失败: {e}")
            break
        if not items:
            break
        for it in items:
            t = it.get("showTime") or ""
            try:
                dt = pd.to_datetime(t)
            except Exception:
                continue
            if dt < cutoff:
                continue
            market.append({
                "time": str(dt),
                "title": it.get("title") or "",
                "summary": (it.get("summary") or "")[:200],
                "source": it.get("mediaName") or "",
                "url": it.get("url") or "",
            })
        if len(market) >= 60:
            break

    market.sort(key=lambda x: x["time"], reverse=True)

    # 个股新闻：从快讯里过滤（命中率低，命中则有用）
    alias = []
    try:
        from . import store
        w = store.get_watch(code)
        if w:
            alias = list(w.get("tags") or []) + [w.get("name") or ""]
    except Exception:
        pass
    if name:
        alias.append(name)
    alias = [a for a in dict.fromkeys(alias) if a and len(a) >= 2]

    stock_news = []
    if alias:
        for m in market:
            blob = m["title"] + " " + m["summary"]
            if code in blob or any(a in blob for a in alias):
                stock_news.append(m)

    return stock_news, market


def get_market_news(size=30):
    """东财全球资讯 7×24 快讯 —— 用来判断大盘情绪和宏观背景"""
    try:
        r = sess_get("https://np-listapi.eastmoney.com/comm/web/getNewsByColumns",
                         params={"client": "web", "biz": "web_news_col",
                                 "column": "345", "order": "1", "needInteractData": "0",
                                 "page_index": "1", "page_size": str(size),
                                 "req_trace": "1",
                                 "fields": "code,showTime,title,mediaName,summary,url"},
                         headers={"User-Agent": UA,
                                  "Referer": "https://finance.eastmoney.com/"},
                         timeout=15)
        items = (r.json().get("data") or {}).get("list") or []
        return [{
            "time": it.get("showTime") or "",
            "title": it.get("title") or "",
            "summary": (it.get("summary") or "")[:200],
            "source": it.get("mediaName") or "",
            "url": it.get("url") or "",
        } for it in items]
    except Exception as e:
        _log(f"全球资讯失败: {e}")
        return []


# ---------------- 研报（东财）----------------

def get_reports(code, max_pages=1):
    """个股研报 + 评级 + 三年EPS预测"""
    url = "https://reportapi.eastmoney.com/report/list"
    out = []
    for page in range(1, max_pages + 1):
        params = {
            "industryCode": "*", "pageSize": "50", "industry": "*",
            "rating": "*", "ratingChange": "*",
            "beginTime": "2024-01-01", "endTime": "2030-01-01",
            "pageNo": str(page), "fields": "", "qType": "0",
            "orgCode": "", "code": code, "rcode": "",
        }
        try:
            r = em_get(url, params=params, headers={"Referer": "https://data.eastmoney.com/"})
            d = r.json()
        except Exception as e:
            _log(f"研报失败: {e}")
            break
        rows = d.get("data") or []
        if not rows:
            break
        for it in rows:
            out.append({
                "date": (it.get("publishDate") or "")[:10],
                "org": it.get("orgSName") or "",
                "title": it.get("title") or "",
                "rating": it.get("emRatingName") or "",
                "eps_cur": it.get("predictThisYearEps"),
                "eps_next": it.get("predictNextYearEps"),
                "industry": it.get("indvInduName") or "",
                "info_code": it.get("infoCode") or "",
            })
        if page >= (d.get("TotalPage", 1) or 1):
            break
    out.sort(key=lambda x: x["date"], reverse=True)
    return out


# ---------------- 互动易问答（巨潮）----------------

def get_irm(code, page_size=20):
    """投资者提问 + 公司回复 —— 这块信息别处拿不到"""
    try:
        r1 = sess_post("https://irm.cninfo.com.cn/newircs/index/queryKeyboardInfo",
                           data={"keyWord": code},
                           headers={"User-Agent": UA}, timeout=10)
        d1 = r1.json().get("data") or []
        if not d1:
            return []
        org_id = d1[0].get("secid")
        params = {"_t": 1, "stockcode": code, "orgId": org_id,
                  "pageSize": page_size, "pageNum": 1,
                  "keyWord": "", "startDay": "", "endDay": ""}
        r2 = sess_post("https://irm.cninfo.com.cn/newircs/company/question",
                           params=params, headers={"User-Agent": UA}, timeout=10)
        rows = r2.json().get("rows") or []
        out = []
        for it in rows:
            pd_ = it.get("pubDate")
            out.append({
                "time": datetime.fromtimestamp(pd_ / 1000).strftime("%Y-%m-%d %H:%M") if pd_ else "",
                "question": (it.get("mainContent") or "").strip(),
                "answer": (it.get("attachedContent") or "").strip() or None,
                "answerer": it.get("attachedAuthor") or "",
            })
        return out
    except Exception as e:
        _log(f"互动易失败: {e}")
        return []


# ---------------- 龙虎榜 ----------------

def get_lhb(code, days=90):
    end = datetime.now()
    start = end - timedelta(days=days)
    rows = em_datacenter(
        "RPT_DAILYBILLBOARD_DETAILSNEW",
        filter_str=f"(SECURITY_CODE=\"{code}\")(TRADE_DATE>='{start:%Y-%m-%d}')",
        page_size=20, sort_columns="TRADE_DATE", sort_types="-1")
    out = []
    for r in rows:
        out.append({
            "date": (r.get("TRADE_DATE") or "")[:10],
            "reason": r.get("EXPLANATION") or "",
            "net": float(r.get("BILLBOARD_NET_AMT") or 0),
            "pct": float(r.get("CHANGE_RATE") or 0),
        })
    return out


# ---------------- 解禁 ----------------

def get_lockup(code, days_ahead=180):
    """限售解禁。字段注意：CURRENT_FREE_SHARES 单位是【万股】，FREE_RATIO 是小数。"""
    rows = em_datacenter(
        "RPT_LIFT_STAGE",
        filter_str=f"(SECURITY_CODE=\"{code}\")",
        page_size=30, sort_columns="FREE_DATE", sort_types="-1")
    out = []
    now = datetime.now()
    for r in rows:
        d = (r.get("FREE_DATE") or "")[:10]
        if not d:
            continue
        try:
            dd = datetime.strptime(d, "%Y-%m-%d")
        except ValueError:
            continue
        future = dd >= now
        if future and (dd - now).days > days_ahead:
            continue
        shares_wan = float(r.get("CURRENT_FREE_SHARES") or 0)
        ratio = float(r.get("FREE_RATIO") or 0) * 100
        out.append({
            "date": d,
            "shares": shares_wan * 1e4,      # 统一成股
            "ratio": round(ratio, 2),
            "mcap": float(r.get("LIFT_MARKET_CAP") or 0) * 1e4,
            "type": r.get("FREE_SHARES_TYPE") or "",
            "future": future,
        })
    return out


# ---------------- 融资融券 ----------------

def get_margin(code, size=10):
    rows = em_datacenter(
        "RPTA_WEB_RZRQ_GGMX",
        filter_str=f"(SCODE=\"{code}\")",
        page_size=size, sort_columns="DATE", sort_types="-1")
    out = []
    for r in rows:
        out.append({
            "date": (r.get("DATE") or "")[:10],
            "rzye": float(r.get("RZYE") or 0),      # 融资余额
            "rzjme": float(r.get("RZJME") or 0),    # 融资净买入
            "rqye": float(r.get("RQYE") or 0),      # 融券余额
        })
    return out


# ---------------- 股东户数 ----------------

def get_holders(code):
    rows = em_datacenter(
        "RPT_HOLDERNUMLATEST",
        filter_str=f"(SECURITY_CODE=\"{code}\")",
        page_size=10, sort_columns="END_DATE", sort_types="-1")
    out = []
    for r in rows:
        out.append({
            "date": (r.get("END_DATE") or "")[:10],
            "num": r.get("HOLDER_NUM"),
            "chg": r.get("HOLDER_NUM_CHANGE"),
            "ratio": r.get("HOLDER_NUM_RATIO"),
        })
    return out


# ---------------- 聚合 ----------------

def collect(stock, progress=None):
    """
    收集单只股票全部数据。
    progress: 可选回调 progress(step_name, ok, detail)，服务端用来推进度。
    签名向后兼容 —— 原来只传 stock 的调用不受影响。
    """
    code = stock["code"]

    def step(name, fn, fmt=None):
        if progress:
            progress(name, "start", "")
        try:
            val = fn()
            detail = fmt(val) if fmt else ""
            if progress:
                progress(name, "ok", detail)
            return val
        except Exception as e:
            if progress:
                progress(name, "fail", str(e)[:80])
            _log(f"{name} 失败: {e}")
            return None

    q = step("行情", lambda: get_quote(code))
    k = step("K线", lambda: get_kline(code))
    m = build_metrics(q, k) if q else None

    notices = step("公告", lambda: get_notices(code),
                   lambda v: f"{len(v)}条") or []

    nr = step("新闻", lambda: get_news(code, name=stock.get("name")),
              lambda v: f"{len(v[0])}个股/{len(v[1])}快讯")
    news, market_news = nr if nr else ([], [])
    reports = step("研报", lambda: get_reports(code),
                   lambda v: f"{len(v)}篇") or []
    irm = step("互动易", lambda: get_irm(code, 15),
               lambda v: f"{len(v)}条") or []
    lhb = step("龙虎榜", lambda: get_lhb(code, 120),
               lambda v: f"{len(v)}条") or []
    lockup = step("解禁", lambda: get_lockup(code),
                  lambda v: f"{len(v)}批") or []
    margin = step("两融", lambda: get_margin(code, 5),
                  lambda v: f"{len(v)}条") or []
    holders = step("股东", lambda: get_holders(code),
                   lambda v: f"{len(v)}期") or []

    return {
        "stock": stock, "quote": m, "kline": k,
        "notices": notices, "news": news, "market_news": market_news,
        "reports": reports,
        "irm": irm, "lhb": lhb, "lockup": lockup,
        "margin": margin, "holders": holders,
        "fetched_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def collect_light(code, name=""):
    """轻量版：只抓行情+K线，用于未关注的票快速出概览（懒抓取首选）"""
    q = get_quote(code)
    k = get_kline(code)
    m = build_metrics(q, k) if q else None
    return {"stock": {"code": code, "name": name}, "quote": m, "kline": k,
            "notices": [], "news": [], "reports": [], "irm": [],
            "lhb": [], "lockup": [], "margin": [], "holders": [],
            "fetched_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
