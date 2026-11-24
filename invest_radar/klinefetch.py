# -*- coding: utf-8 -*-
"""
M3.5/B2 · K线数据抓取
周期: minute(1日分时) 5day 5m 15m 30m 60m day week month
源优先级（沿用 a-stock-data 技能）：
  分时/日/周/月 → 腾讯 ifzq.gtimg.cn（不封IP，前复权）
  分钟K(5/15/30/60) → 东财 push2his（限流，走 em_get 节流）
统一前复权 qfq。
"""
import time
from datetime import datetime, timedelta

import pandas as pd

from . import store
from .fetcher import sess_get, em_get, _log

TENCENT_KLINE = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
EM_MIN_KLINE = "https://push2his.eastmoney.com/api/qt/stock/kline/get"

PERIODS = ("minute", "5day", "5m", "15m", "30m", "60m", "day", "week", "month")


def _prefix(code):
    return "sh" if code.startswith(("6", "9")) else (
        "bj" if code.startswith(("4", "8")) else "sz")


def _tencent_kline(code, period, count):
    """腾讯日/周/月K，qfq 前复权"""
    pmap = {"day": "day", "week": "week", "month": "month"}
    pk = pmap[period]
    url = f"{TENCENT_KLINE}?param={_prefix(code)}{code},{pk},,,{count},qfq"
    r = sess_get(url, headers={"Referer": "https://gu.qq.com/"})
    d = r.json()
    data = d.get("data") or {}
    node = data.get(f"{_prefix(code)}{code}") or {}
    bars = node.get(pk) or node.get(f"qfq{pk}") or []
    out = []
    for row in bars:
        # 行可能是 list（正常）或 dict（最后一根附带 qfq 信息）——只收 list
        if not isinstance(row, list) or len(row) < 6:
            continue
        try:
            ts = int(datetime.strptime(row[0], "%Y-%m-%d").timestamp() * 1000)
            out.append({
                "ts": ts,
                "o": float(row[1]), "c": float(row[2]),
                "h": float(row[3]), "l": float(row[4]),
                "volume": float(row[5]),
                "amount": float(row[6]) if len(row) > 6 and row[6] else None,
            })
        except (ValueError, TypeError):
            continue
    return out


def _tencent_minute(code):
    """腾讯当日分时：返回 [{ts, price, volume}]，盘后含完整 241 点"""
    url = (f"https://web.ifzq.gtimg.cn/appstock/app/minute/query"
           f"?code={_prefix(code)}{code}")
    r = sess_get(url, headers={"Referer": "https://gu.qq.com/"})
    d = r.json()
    node = (d.get("data") or {}).get(f"{_prefix(code)}{code}") or {}
    data = node.get("data") or {}
    date = str(data.get("date") or "")
    pts = data.get("data") or []
    out = []
    base = datetime.strptime(date, "%Y%m%d") if date else datetime.now().replace(hour=0, minute=0)
    for i, p in enumerate(pts):
        # p 形如 "0930 8.97 1234 8.97"（时间 价格 累计量 均价）
        parts = p.split()
        if len(parts) < 3:
            continue
        hm = parts[0]
        ts = int(base.timestamp()) + (int(hm[:2]) * 60 + int(hm[2:])) * 60
        out.append({
            "ts": ts * 1000,
            "price": float(parts[1]),
            "volume": float(parts[2]),
            "avg": float(parts[3]) if len(parts) > 3 else None,
        })
    pre_close = None
    try:
        pre_close = float(node.get("qt") and list(node["qt"].values())[0].get(4)) if node.get("qt") else None
    except Exception:
        pass
    return out, pre_close


def _em_minute_kline(code, period, count=480):
    """东财分钟K（5/15/30/60），走节流"""
    klt = {"5m": 5, "15m": 15, "30m": 30, "60m": 60}[period]
    secid = f"{'1' if code.startswith(('6','9')) else '0'}.{code}"
    params = {
        "secid": secid, "klt": str(klt), "fqt": "1",  # fqt=1 前复权
        "lmt": str(count), "end": "20500101", "iscca": "1",
        "fields1": "f1,f2,f3,f4,f5,f6", "fields2": "f51,f52,f53,f54,f55,f56,f57",
    }
    r = em_get(EM_MIN_KLINE, params=params,
               headers={"Referer": "https://quote.eastmoney.com/"})
    d = r.json()
    kl = (d.get("data") or {}).get("klines") or []
    out = []
    for row in kl:
        # "2026-11-17 10:30,open,close,high,low,volume,amount"
        parts = row.split(",")
        if len(parts) < 7:
            continue
        ts = int(pd.to_datetime(parts[0]).timestamp() * 1000)
        out.append({
            "ts": ts, "o": float(parts[1]), "c": float(parts[2]),
            "h": float(parts[3]), "l": float(parts[4]),
            "volume": float(parts[5]), "amount": float(parts[6]),
        })
    return out


def _tencent_5day_minute(code):
    """5日分时：腾讯按日拉 5 次拼起来"""
    out = []
    for i in range(5, 0, -1):
        day = (datetime.now() - timedelta(days=i)).strftime("%Y%m%d")
        try:
            url = (f"https://web.ifzq.gtimg.cn/appstock/app/minute/query"
                   f"?code={_prefix(code)}{code}&date={day}")
            r = sess_get(url, headers={"Referer": "https://gu.qq.com/"})
            node = ((r.json().get("data") or {}).get(_prefix(code) + code) or {})
            data = node.get("data") or {}
            date = str(data.get("date") or day)
            base = datetime.strptime(date, "%Y%m%d")
            for p in (data.get("data") or []):
                parts = p.split()
                if len(parts) < 3:
                    continue
                ts = int(base.timestamp()) + (int(parts[0][:2]) * 60 + int(parts[0][2:])) * 60
                out.append({"ts": ts * 1000, "price": float(parts[1]),
                            "volume": float(parts[2])})
        except Exception as e:
            _log(f"5日分时 {day} 失败: {e}")
        time.sleep(0.4)   # 腾讯温和限速
    return out


def get_kline_bars(code, period, force=False):
    """
    带缓存的 K线获取入口。返回 dict(bars, pre_close, from_cache)。
    day/week/month/5m/15m/30m/60m → OHLC 存储；minute/5day → 分时点存储。
    """
    if period not in PERIODS:
        raise ValueError(f"未知周期 {period}")
    key = f"kline:{code}:{period}"
    is_timeline = period in ("minute", "5day")
    limit = 480 if period in ("5m", "15m", "30m", "60m") else 300

    if not force and not store.need_refresh(key):
        if is_timeline:
            cached = store.load_timeline(code, period)
            if cached:
                return {"bars": cached, "pre_close": None, "from_cache": True}
        else:
            cached = store.load_kline(code, period, limit)
            if cached:
                return {"bars": cached, "from_cache": True}

    bars = []
    pre_close = None
    if period in ("day", "week", "month"):
        bars = _tencent_kline(code, period, 250)
    elif period == "minute":
        bars, pre_close = _tencent_minute(code)
    elif period == "5day":
        bars = _tencent_5day_minute(code)
    else:
        bars = _em_minute_kline(code, period)

    if bars:
        if is_timeline:
            store.save_timeline(code, period, bars)
        else:
            store.save_kline(code, period, bars)
        store.mark_fetched(key)
    return {"bars": bars, "pre_close": pre_close, "from_cache": False}
