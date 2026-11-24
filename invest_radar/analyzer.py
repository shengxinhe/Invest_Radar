# -*- coding: utf-8 -*-
"""分析层：规则打分 + 估值 + 风险标记。零成本、可解释、不调用 LLM。"""
import math

from . import config


def _hit(text, words):
    found = []
    for w in words:
        if w in text and w not in found:
            found.append(w)
    return found


def score_news(news, stock):
    kws = list(dict.fromkeys(config.GLOBAL_KEYWORDS + stock.get("keywords", [])))
    alias = stock.get("alias", []) + [stock["name"]]
    out = []
    for n in news:
        blob = n["title"] + " " + n["summary"]
        hits = _hit(blob, kws)
        risk = [h for h in hits if h in config.RISK_KEYWORDS]
        good = [h for h in hits if h not in config.RISK_KEYWORDS]
        related = any(a in blob for a in alias) or stock["code"] in blob
        tag = "risk" if risk else ("good" if good else "neutral")
        out.append({**n, "hits": hits, "risk": risk, "good": good,
                    "tag": tag, "related": related})
    return out


def score_notices(notices):
    HIGH = ["减持", "质押", "问询", "立案", "处罚", "警示", "诉讼", "仲裁",
            "停产", "事故", "减值", "差错", "更正", "非标", "保留意见",
            "退市", "风险提示", "终止", "失败", "延期", "担保", "冻结",
            "变更", "解聘", "辞职", "监管", "关注函", "股票交易异常"]
    GOOD = ["增持", "回购", "中标", "分红", "预增", "扭亏", "签订", "重大合同",
            "收购", "投产", "获得", "批复", "核准", "备案", "业绩快报", "权益分派"]
    out = []
    for n in notices:
        blob = n["title"] + " " + n["type"]
        hr = _hit(blob, HIGH)
        gd = _hit(blob, GOOD)
        level = "high" if hr else ("good" if gd else "normal")
        out.append({**n, "risk": hr, "good": gd, "level": level})
    return out


def score_reports(reports):
    """研报评级分布 + EPS 预期 + 目标涨幅"""
    if not reports:
        return {}
    from collections import Counter
    ratings = Counter(r["rating"] for r in reports if r["rating"])
    latest = reports[0]
    return {
        "count": len(reports),
        "ratings": dict(ratings),
        "latest": latest,
        "orgs": len(set(r["org"] for r in reports)),
    }


def valuation(q):
    """估值判断。腾讯给的 PE/PB 直接可用。"""
    if not q:
        return []
    out = []
    pe, pb = q.get("pe_ttm"), q.get("pb")
    mcap = q.get("mcap_yi")

    if mcap:
        out.append(f"总市值 {mcap:.0f}亿 / 流通 {q.get('float_mcap_yi', 0):.0f}亿")
    if pe:
        if pe < 0:
            out.append(f"PE(TTM) {pe:.1f} → 亏损")
        elif pe < 15:
            out.append(f"PE(TTM) {pe:.1f} → 低估区")
        elif pe < 30:
            out.append(f"PE(TTM) {pe:.1f} → 合理区")
        elif pe < 60:
            out.append(f"PE(TTM) {pe:.1f} → 偏贵")
        else:
            out.append(f"PE(TTM) {pe:.1f} → 高估")
    if pb:
        if pb < 1:
            out.append(f"PB {pb:.2f} → 破净")
        elif pb < 2:
            out.append(f"PB {pb:.2f} → 低")
        elif pb < 5:
            out.append(f"PB {pb:.2f} → 正常")
        else:
            out.append(f"PB {pb:.2f} → 偏高")
    return out


def trend_read(q):
    if not q or q.get("price") is None:
        return {"verdict": "无数据", "points": []}

    pts = []
    c = q["price"]
    pos = q.get("position")

    if q.get("above_ma20") is not None:
        pts.append(f"{'站上' if q['above_ma20'] else '跌破'} 20日线({q['ma20']})")
    if q.get("above_ma60") is not None:
        pts.append(f"{'在' if q['above_ma60'] else '跌破'} 60日线({q['ma60']})")

    if pos is not None and q.get("high_1y"):
        if pos >= config.ALERT["position_high"]:
            pts.append(f"一年 {pos*100:.0f}% 高分位（{q['low_1y']}~{q['high_1y']}）")
        elif pos <= config.ALERT["position_low"]:
            pts.append(f"一年 {pos*100:.0f}% 低分位（{q['low_1y']}~{q['high_1y']}）")
        else:
            pts.append(f"一年 {pos*100:.0f}% 中位（{q['low_1y']}~{q['high_1y']}）")

    vr = q.get("vol_ratio") or 0
    if vr >= config.ALERT["volume_ratio"]:
        pts.append(f"量比 {vr:.1f} 放量")
    elif 0 < vr <= 0.6:
        pts.append(f"量比 {vr:.1f} 缩量")
    elif vr:
        pts.append(f"量比 {vr:.1f} 正常")

    bull = sum([bool(q.get("above_ma20")), bool(q.get("above_ma60"))])
    hi = pos is not None and pos > 0.6
    lo = pos is not None and pos < 0.35

    if bull == 2 and hi:
        v = "多头排列，强势"
    elif bull == 2:
        v = "站上双均线，位置不高"
    elif bull == 0 and lo:
        v = "空头排列，弱势"
    elif bull == 0:
        v = "跌破双均线，注意"
    elif bull == 1:
        v = "均线缠绕，方向不明"
    else:
        v = "数据不足"

    return {"verdict": v, "points": pts}


def fin_read(fin):
    """财务读法：同比 + 现金流质量"""
    if not fin:
        return []
    d, p = fin["data"], fin["periods"]
    out = []

    def g(ind, pk):
        row = d.get(ind)
        if not row:
            return None
        v = row.get(pk)
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    if len(p) >= 5:
        cur, yoy = p[0], p[4]
        ni, ni_y = g("归母净利润", cur), g("归母净利润", yoy)
        rev, rev_y = g("营业总收入", cur), g("营业总收入", yoy)

        if ni and ni_y:
            out.append(f"归母净利 {ni/1e8:.2f}亿（同比 {(ni/ni_y-1)*100:+.1f}%）")
        if rev and rev_y:
            out.append(f"营收 {rev/1e8:.2f}亿（同比 {(rev/rev_y-1)*100:+.1f}%）")

        cf = g("经营现金流量净额", cur)
        if cf is not None and ni:
            r = cf / ni
            if r < 0:
                out.append(f"经营现金流 {cf/1e8:.2f}亿 为负 ← 利润没变成钱")
            elif r < 0.5:
                out.append(f"现金流/净利 = {r:.2f} 偏低")
            else:
                out.append(f"现金流/净利 = {r:.2f} 健康")

        cost = g("营业成本", cur)
        if rev and cost and rev > 0:
            out.append(f"毛利率 {(1-cost/rev)*100:.1f}%")

        debt = g("资产负债率", cur)
        if debt is not None:
            out.append(f"资产负债率 {debt:.1f}%")

    return out


def alerts(d):
    a = []
    q = d.get("quote")
    if q:
        if abs(q.get("pct", 0)) >= config.ALERT["pct_change"]:
            a.append(f"异动：今日 {q['pct']:+.2f}%")
        if q.get("vol_ratio", 0) >= config.ALERT["volume_ratio"]:
            a.append(f"放量：量比 {q['vol_ratio']:.1f}")
        if q.get("position", 0.5) >= config.ALERT["position_high"]:
            a.append(f"接近一年高点：{q['position']*100:.0f}% 分位")
        if q.get("position", 0.5) <= config.ALERT["position_low"]:
            a.append(f"接近一年低点：{q['position']*100:.0f}% 分位")

    high = [n for n in d.get("notices_scored", []) if n["level"] == "high"]
    if high:
        a.append(f"{len(high)} 条需关注公告")

    fut = [x for x in d.get("lockup", []) if x["future"]]
    if fut:
        a.append(f"未来有 {len(fut)} 批解禁（最近 {fut[0]['date']}，占比 {fut[0]['ratio']}%）")

    mg = d.get("margin") or []
    if len(mg) >= 5:
        diff = mg[0]["rzye"] - mg[4]["rzye"]
        if abs(diff) / max(mg[4]["rzye"], 1) > 0.1:
            a.append(f"融资余额5日 {'增' if diff>0 else '减'} {abs(diff)/1e8:.2f}亿")

    return a
