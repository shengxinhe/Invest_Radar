# -*- coding: utf-8 -*-
"""
M5+ · AI 联网搜索工具
给全局助手/辩论用的外部资料检索层：
  1. 巨潮全文搜索 —— 官方公告库（权威，A股全覆盖）
  2. 东财 7x24 快讯 —— 市场资讯（按关键词过滤）
统一返回 {source, title, date, url, snippet} 列表。
"""
import re
from datetime import datetime, timedelta

import requests

from .fetcher import sess_post

_UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36"}


def _clean(t):
    t = re.sub(r"<[^>]+>", "", t or "")
    return re.sub(r"\s+", " ", t).strip()


# ---------------- 巨潮全文搜索 ----------------

def cninfo_fulltext(q, days=180, limit=10):
    """巨潮公告全文搜索。days 限定时间窗。多词查询失败时退化为逐词。"""
    sdate = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    headers = {**_UA,
               "Referer": "http://www.cninfo.com.cn/new/commonUrl?url=disclosure/list/notice"}

    def _try(key):
        r = sess_post(
            "http://www.cninfo.com.cn/new/fulltextSearch/full",
            data={"searchkey": key, "sdate": sdate, "edate": "",
                  "isfulltext": "false", "sortName": "pubdate",
                  "sortType": "desc", "pageNum": "1",
                  "pageSize": str(min(limit, 20))},
            headers=headers, timeout=15)
        d = r.json()
        out = []
        for a in (d.get("announcements") or [])[:limit]:
            adj = a.get("adjunctUrl") or ""
            url = f"http://static.cninfo.com.cn/{adj}" if adj else ""
            out.append({
                "source": "巨潮公告",
                "title": _clean(a.get("announcementTitle")),
                "date": a.get("announcementTime") or 0,
                "sec_name": _clean(a.get("secName")),
                "url": url,
            })
        return out

    for key in (q, q.replace(" ", ""), q.split()[0] if " " in q else q):
        try:
            res = _try(key)
        except Exception:
            res = []
        if res:
            return res
    return []


def _cninfo_ts(v):
    try:
        # announcementTime 是毫秒时间戳（可能是 str）
        ts = int(v) / 1000
        return datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
    except Exception:
        return ""


# ---------------- 东财快讯关键词过滤 ----------------

def em_news_search(q, days=7, limit=10):
    """从全球 7x24 快讯里按关键词筛（快讯本身不支持服务端关键词）。"""
    cutoff = datetime.now() - timedelta(days=days)
    hits = []
    terms = [q] + [q[i:i+2] for i in range(0, max(0, len(q)-1))] if len(q) <= 4 else [q]
    for page in (1, 2, 3):
        try:
            r = sess_get(
                "https://np-listapi.eastmoney.com/comm/web/getNewsByColumns",
                params={"client": "web", "biz": "web_news_col", "column": "345",
                        "order": "1", "needInteractData": "0",
                        "page_index": str(page), "page_size": "100",
                        "req_trace": "1",
                        "fields": "code,showTime,title,mediaName,summary,url"},
                headers={**_UA, "Referer": "https://finance.eastmoney.com/"},
                timeout=15)
            items = (r.json().get("data") or {}).get("list") or []
        except Exception:
            break
        if not items:
            break
        for it in items:
            blob = (it.get("title") or "") + (it.get("summary") or "")
            if q in blob or q.replace(" ", "") in blob:
                hits.append({
                    "source": "东财快讯",
                    "title": _clean(it.get("title")),
                    "date": (it.get("showTime") or "")[:10],
                    "sec_name": "",
                    "url": it.get("url") or "",
                    "snippet": _clean(it.get("summary"))[:120],
                })
                if len(hits) >= limit:
                    return hits
    return hits


# ---------------- 统一入口 ----------------

def web_search(q, limit=12):
    """
    合并两个来源，去重排序（新在前）。
    公告库只索引公司公告，行业词（铜价/TC/加工费）搜不到时自动拼关注股名兜底。
    """
    q = (q or "").strip()
    if not q:
        return []

    results = cninfo_fulltext(q, days=365, limit=8) + em_news_search(q, days=14, limit=8)

    # 行业/宏观词兜底：拼关注股名再搜（公告库只收公司公告）
    if len(results) < 3:
        try:
            from . import store
            store.init()
            for w in store.list_watch()[:3]:
                nm = w.get("name")
                if not nm:
                    continue
                try:
                    results += cninfo_fulltext(f"{nm} {q}", days=365, limit=3)
                except Exception:
                    continue
                if len(results) >= limit:
                    break
        except Exception:
            pass

    # 格式化时间
    for r in results:
        if isinstance(r.get("date"), (int, float)):
            r["date"] = _cninfo_ts(r["date"])
    # 去重
    seen, out = set(), []
    for r in sorted(results, key=lambda x: x.get("date") or "", reverse=True):
        k = r.get("title") or ""
        if k and k not in seen:
            seen.add(k)
            out.append(r)
    return out[:limit]
