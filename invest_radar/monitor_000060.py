# -*- coding: utf-8 -*-
"""
中金岭南 000060 专用监控
监控项：
  1. 沪铜期货上涨（任何上涨都报，>0.5% 标重点）
  2. 该股全部新公告 / 新闻 / 互动 / 研报（不筛级别，全推）
  3. 铜精矿 TC/RC 相关关键词出现在公告库
  4. 价格预警：破一年低点 / 破整数关 / 单日大跌 / 站上均线 / 接近涨停跌停
去重：state 文件记录上次铜价 + 已推词条 id + 上次价格
"""
import json
import time
from datetime import datetime
from pathlib import Path

from . import config, fetcher, store

CODE = "000060"
NAME = "中金岭南"
STATE = config.DATA_DIR / "monitor_000060_state.json"

# 价格预警阈值
PRICE_LEVELS = [4.50, 4.30, 4.10, 3.90, 5.00, 5.20]   # 整数关/心理位
BIG_DROP_PCT = -3.0        # 单日跌幅超过就报
BIG_RISE_PCT = 3.0         # 单日涨幅超过就报


def _load_state():
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        return {"last_copper": None, "seen_ids": [], "last_run": 0}


def _save_state(st):
    try:
        st["seen_ids"] = st.get("seen_ids", [])[-300:]   # 只留最近 300 个
        STATE.write_text(json.dumps(st, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def _copper_section(st):
    """铜价对比上次检查"""
    out = {"has_news": False, "lines": [], "alert": False}
    try:
        cu = fetcher.get_copper_futures(30)
    except Exception:
        return out
    if not cu:
        return out

    latest = cu["latest"]
    last = st.get("last_copper")
    lines = []

    # 今日涨跌
    d1 = cu.get("chg_1d")
    if d1 is not None:
        arrow = "📈" if d1 > 0 else ("📉" if d1 < 0 else "➖")
        lines.append(f"{arrow} 沪铜 {latest:,.0f} 元/吨（今日 {d1:+.2f}%）")

    # 相对上次检查的变化
    if last:
        delta = (latest / last - 1) * 100
        if abs(delta) >= 0.3:
            lines.append(f"   较上次检查（{last:,.0f}）{delta:+.2f}%")
            if delta >= 0.5:
                out["alert"] = True
                out["has_news"] = True
    # 关键位置
    ma20 = cu.get("ma20")
    if ma20:
        pos = "站上" if latest > ma20 else "低于"
        lines.append(f"   {pos} MA20 {ma20:,.0f}")
        # 首次站上 MA20 → 重要信号
        if latest > ma20 and last and last <= ma20:
            out["alert"] = True
            out["has_news"] = True
            lines.append("   ⚠️ 首次站上 20 日均线，趋势可能转折")

    out["lines"] = lines
    st["last_copper"] = latest
    st["last_copper_date"] = cu.get("date")
    return out


def _price_section(st):
    """价格预警：破位/整数关/单日异动/均线"""
    out = {"lines": [], "alert": False, "price": None, "pct": None}
    try:
        q = fetcher.get_quote(CODE)
    except Exception:
        return out
    if not q or not q.get("price"):
        return out

    price = q["price"]
    pct = q.get("pct")
    out["price"], out["pct"] = price, pct

    # 技术指标（日K）
    ma5 = ma20 = low_1y = high_1y = None
    try:
        k = fetcher.get_kline(CODE)
        if hasattr(k, "iloc") and len(k) >= 20:
            closes = k["close"].astype(float)
            ma5 = closes.tail(5).mean()
            ma20 = closes.tail(20).mean()
            seg = closes.tail(250) if len(closes) >= 250 else closes
            # 一年低点要含当日实时价（日K收盘价不含盘中新低）
            low_1y = min(seg.min(), price)
            high_1y = max(seg.max(), price)
    except Exception:
        pass

    last_price = st.get("last_stock_price")
    last_low = st.get("last_low_1y")

    # ① 创新低（破一年低点）
    if low_1y and last_low:
        if price < last_low and price < (last_price or 1e9):
            out["lines"].append(
                f"🆘 创一年新低：{price}（前低 {last_low:.2f}）")
            out["alert"] = True
    # ② 突破整数关（向下）
    if last_price:
        for lv in PRICE_LEVELS:
            if last_price > lv >= price:
                out["lines"].append(f"⚠️ 跌破关口 {lv}（现价 {price}）")
                out["alert"] = True
            elif last_price < lv <= price:
                out["lines"].append(f"✅ 收复关口 {lv}（现价 {price}）")
                out["alert"] = True

    # ③ 单日异动
    if pct is not None:
        if pct <= BIG_DROP_PCT:
            out["lines"].append(f"🔴 单日大跌 {pct:+.2f}%（现价 {price}）")
            out["alert"] = True
        elif pct >= BIG_RISE_PCT:
            out["lines"].append(f"🟢 单日大涨 {pct:+.2f}%（现价 {price}）")
            out["alert"] = True

    # ④ 均线穿越
    if last_price and ma5 and ma20:
        if last_price < ma5 <= price:
            out["lines"].append(f"📈 站上 MA5 {ma5:.2f}（现价 {price}）")
            out["alert"] = True
        elif last_price > ma5 >= price:
            out["lines"].append(f"📉 跌破 MA5 {ma5:.2f}（现价 {price}）")
            out["alert"] = True
        if last_price < ma20 <= price:
            out["lines"].append(f"🚀 站上 MA20 {ma20:.2f} —— 趋势可能转折")
            out["alert"] = True

    # ⑤ 涨跌停附近
    if pct is not None and (pct >= 9.5 or pct <= -9.5):
        out["lines"].append(f"🚨 接近涨跌停 {pct:+.2f}%")

    # 常规状态行（每次都给，让用户知道价位）
    base = f"现价 {price}"
    if pct is not None:
        base += f"（{pct:+.2f}%）"
    if ma20:
        base += f"  MA5 {ma5:.2f} / MA20 {ma20:.2f}"
    if low_1y:
        base += f"  一年低点 {low_1y:.2f}"
    out["lines"].insert(0, base)
    out["lines"].append("")     # 空行

    st["last_stock_price"] = price
    if low_1y:
        st["last_low_1y"] = min(low_1y, price)
    st["last_ma5"] = ma5
    st["last_ma20"] = ma20
    return out


def _news_section(st):
    """该股全部新词条（不筛级别）"""
    seen = set(st.get("seen_ids", []))
    cutoff = time.time() - 7 * 86400      # 只看 7 天内，防首次运行刷屏
    c = store.conn()
    rows = c.execute("""
        SELECT id, type, title, level, published_at, url
        FROM entry WHERE code=? AND published_at > ?
        ORDER BY published_at ASC
    """, (CODE, cutoff)).fetchall()

    fresh = [r for r in rows if r["id"] not in seen]
    out = {"items": [], "lines": [], "ids": []}
    TYPE = {"notice": "公告", "news": "新闻", "qa": "互动", "report": "研报"}
    for r in fresh:
        d = datetime.fromtimestamp(r["published_at"]).strftime("%m-%d")
        tag = {"risk": "⚠️", "positive": "✅"}.get(r["level"], "·")
        out["items"].append({
            "id": r["id"], "type": r["type"], "title": r["title"],
            "level": r["level"], "date": d, "url": r["url"],
        })
        out["lines"].append(
            f"{tag} [{d}] {TYPE.get(r['type'], r['type'])}：{r['title']}")
        out["ids"].append(r["id"])
    return out


def _copper_keyword_section(st):
    """公告库里 TC/RC、铜精矿相关关键词（行业变量）"""
    from .websearch import cninfo_fulltext
    out = {"lines": [], "alert": False}
    kws = ["铜精矿加工费", "TC/RC"]
    for kw in kws:
        try:
            rows = cninfo_fulltext(kw, days=14, limit=3)
        except Exception:
            continue
        for r in rows:
            t = r.get("title") or ""
            key = f"kw:{t[:40]}"
            if key in set(st.get("seen_ids", [])):
                continue
            out["lines"].append(f"🔧 [{r.get('date','')}] {t[:60]}（{r.get('sec_name','')}）")
            out["alert"] = True
            st.setdefault("seen_ids", []).append(key)
    return out


def check(update_state=True):
    """
    返回 {has_update, copper_alert, price_alert, lines, items}
    """
    st = _load_state()
    before = dict(st)

    cu = _copper_section(st)
    px = _price_section(st)
    news = _news_section(st)
    kw = _copper_keyword_section(st)

    lines = []
    if px["lines"]:
        lines.extend(px["lines"])
    if cu["lines"]:
        lines.extend(cu["lines"])
        lines.append("")
    if news["lines"]:
        lines.append("【新消息】")
        lines.extend(news["lines"][:15])
        if len(news["lines"]) > 15:
            lines.append(f"…另有 {len(news['lines'])-15} 条")
    if kw["lines"]:
        lines.append("")
        lines.extend(kw["lines"][:3])

    has_update = bool(news["items"] or kw["lines"] or cu["alert"]
                      or px["alert"])

    st["seen_ids"] = st.get("seen_ids", []) + news["ids"]
    st["last_run"] = int(time.time())
    if update_state:
        _save_state(st)

    return {
        "code": CODE, "name": NAME,
        "has_update": has_update,
        "copper_alert": cu["alert"],
        "price_alert": px["alert"],
        "price": px["price"],
        "pct": px["pct"],
        "lines": lines,
        "items": news["items"],
        "at": datetime.now().strftime("%H:%M"),
    }


def reset_state():
    """清空状态（重来一遍全量）"""
    if STATE.exists():
        STATE.unlink()
    return True


if __name__ == "__main__":
    r = check()
    tag = "有更新" if r["has_update"] else "无更新"
    print(f"[{r['at']}] {r['name']} 监控：{tag}")
    if r.get("price_alert"):
        print("  价格预警！")
    if r.get("copper_alert"):
        print("  铜价异动！")
    for l in r["lines"]:
        print("  " + l)
