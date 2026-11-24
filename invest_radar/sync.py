# -*- coding: utf-8 -*-
"""
同步层 —— 把 fetcher 抓到的原始数据写进 store。
服务层只调这里，不直接碰 fetcher + store 的组合。

关键：level 判定沿用 analyzer 的规则，保持"标红标绿"行为一致。
"""
import time
from datetime import datetime

from . import analyzer, fetcher, store


def _ts(dt_str, fmt="%Y-%m-%d"):
    """字符串日期 → unix 时间戳"""
    try:
        return int(datetime.strptime(dt_str[:10], fmt).timestamp())
    except (ValueError, TypeError):
        return store.now()


def _ts_any(s):
    """尽量解析多种时间格式"""
    if not s:
        return store.now()
    s = str(s)
    for fmt, n in (("%Y-%m-%d %H:%M:%S", 19), ("%Y-%m-%d %H:%M", 16), ("%Y-%m-%d", 10)):
        try:
            return int(datetime.strptime(s[:n], fmt).timestamp())
        except ValueError:
            continue
    return store.now()


# ---------------- 词条入库 ----------------

def sync_notices(code, notices, stock=None):
    """公告入库。level 用 analyzer 的规则判定。"""
    if not notices:
        return 0, 0

    scored = analyzer.score_notices(notices)
    items = []
    for n in scored:
        items.append({
            "code": code,
            "type": "notice",
            "source_id": n.get("url") or n.get("title", ""),
            "title": n.get("title", ""),
            "url": n.get("url", ""),
            "published_at": _ts(n.get("date")),
            "content": " ".join(n.get("risk", []) + n.get("good", [])),
            "level": "risk" if n["level"] == "high" else (
                "positive" if n["level"] == "good" else "neutral"),
        })
    new, total = store.bulk_upsert_entries(items)
    store.mark_fetched(f"notice:{code}")
    return new, total


def sync_news(code, news, stock=None, market=None):
    """
    news: 个股新闻（可能为空）
    market: 全市场快讯，作为独立 type='market' 存一份（不带 code 维度）
    返回 (新增数, 总处理数)
    """
    new = total = 0

    if news:
        pw = {"code": code, "name": (stock or {}).get("name", ""),
              "alias": (stock or {}).get("tags", []) or [], "keywords": []}
        scored = analyzer.score_news(news, pw)
        items = []
        for n in scored:
            items.append({
                "code": code,
                "type": "news",
                "source_id": n.get("url") or n.get("title", ""),
                "title": n.get("title", ""),
                "url": n.get("url", ""),
                "published_at": _ts_any(n.get("time")),
                "content": n.get("summary", ""),
                "level": "risk" if n["tag"] == "risk" else (
                    "positive" if n["tag"] == "good" else "neutral"),
            })
        a, b = store.bulk_upsert_entries(items)
        new += a
        total += b

    store.mark_fetched(f"news:{code}")
    return new, total


def sync_market(market):
    """全市场快讯，存到 code='MARKET' 下，供全局页展示"""
    if not market:
        return 0, 0
    items = []
    for n in market:
        items.append({
            "code": "MARKET",
            "type": "market",
            "source_id": n.get("url") or n.get("title", ""),
            "title": n.get("title", ""),
            "url": n.get("url", ""),
            "published_at": _ts_any(n.get("time")),
            "content": n.get("summary", ""),
            "level": "neutral",
        })
    a, b = store.bulk_upsert_entries(items)
    store.mark_fetched("market:all")
    return a, b


def sync_reports(code, reports):
    if not reports:
        return 0, 0
    items = []
    for r in reports:
        items.append({
            "code": code,
            "type": "report",
            "source_id": r.get("info_code") or f"{r.get('org')}|{r.get('title')}",
            "title": f"[{r.get('org','')}] {r.get('title','')}",
            "url": (f"https://pdf.dfcfw.com/pdf/H3_{r['info_code']}_1.pdf"
                    if r.get("info_code") else ""),
            "published_at": _ts(r.get("date")),
            "content": f"评级:{r.get('rating','')} EPS今年:{r.get('eps_cur')} 明年:{r.get('eps_next')}",
            "level": "neutral",
        })
    new, total = store.bulk_upsert_entries(items)
    store.mark_fetched(f"report:{code}")
    return new, total


def sync_irm(code, irm):
    if not irm:
        return 0, 0
    items = []
    for q in irm:
        items.append({
            "code": code,
            "type": "qa",
            "source_id": (q.get("question", "")[:80] + "|" + q.get("time", "")),
            "title": (q.get("question", "") or "")[:100],
            "url": "",
            "published_at": _ts_any(q.get("time")),
            "content": (q.get("question", "") or "") + "\n\n答：" + (q.get("answer") or "（未回复）"),
            "level": "neutral",
        })
    new, total = store.bulk_upsert_entries(items)
    store.mark_fetched(f"qa:{code}")
    return new, total


# ---------------- 全量同步 ----------------

def sync_all(code, stock=None, progress=None):
    """
    抓一只票的全部数据并入库。
    返回 dict：每类数据的新增条数 + 原始数据（给前端即时用）
    """
    stock = stock or store.get_watch(code) or {"code": code, "name": code}
    # 统一字段名：analyzer 用 tags 当 alias
    stock.setdefault("tags", stock.get("tags") or stock.get("alias") or [])
    stock.setdefault("keywords", [])

    def step(name, fn, fmt=None):
        if progress:
            progress(name, "start", "")
        try:
            v = fn()
            if progress:
                progress(name, "ok", fmt(v) if fmt else "")
            return v
        except Exception as e:
            if progress:
                progress(name, "fail", str(e)[:80])
            return None

    res = {"code": code, "new": {}, "raw": {}}

    q = step("行情", lambda: fetcher.get_quote(code))
    k = step("K线", lambda: fetcher.get_kline(code))
    m = fetcher.build_metrics(q, k) if q else None
    if m:
        store.save_quote(m)
        store.mark_fetched(f"quote:{code}")
    res["raw"]["quote"] = m
    res["raw"]["kline"] = k

    n = step("公告", lambda: fetcher.get_notices(code),
             lambda v: f"{len(v)}条") or []
    res["new"]["notice"] = sync_notices(code, n, stock)[0]
    res["raw"]["notices"] = n

    nr = step("新闻", lambda: fetcher.get_news(code, name=stock.get("name")),
              lambda v: f"{len(v[0])}条个股/{len(v[1])}条快讯")
    if nr:
        stock_news, market_news = nr
        a, _ = sync_news(code, stock_news, stock)
        sync_market(market_news)
        res["new"]["news"] = a
        res["raw"]["news"] = stock_news
        res["raw"]["market_news"] = market_news
    else:
        res["raw"]["news"] = []
        res["raw"]["market_news"] = []

    n = step("研报", lambda: fetcher.get_reports(code),
             lambda v: f"{len(v)}篇") or []
    res["new"]["report"] = sync_reports(code, n)[0]
    res["raw"]["reports"] = n

    n = step("互动易", lambda: fetcher.get_irm(code, 15),
             lambda v: f"{len(v)}条") or []
    res["new"]["qa"] = sync_irm(code, n)[0]
    res["raw"]["irm"] = n

    res["raw"]["lhb"] = step("龙虎榜", lambda: fetcher.get_lhb(code, 120),
                             lambda v: f"{len(v)}条") or []
    res["raw"]["lockup"] = step("解禁", lambda: fetcher.get_lockup(code),
                                lambda v: f"{len(v)}批") or []
    res["raw"]["margin"] = step("两融", lambda: fetcher.get_margin(code, 5),
                                lambda v: f"{len(v)}条") or []
    res["raw"]["holders"] = step("股东", lambda: fetcher.get_holders(code),
                                 lambda v: f"{len(v)}期") or []

    return res


def sync_light(code, name=""):
    """未关注的票：只抓行情，快速出概览"""
    q = fetcher.get_quote(code)
    k = fetcher.get_kline(code)
    m = fetcher.build_metrics(q, k) if q else None
    if m:
        store.save_quote(m)
        store.mark_fetched(f"quote:{code}")
    return {"code": code, "quote": m, "kline": k}
