# -*- coding: utf-8 -*-
"""输出层：终端 + Markdown + 推送"""
import json
from datetime import datetime

import requests

from . import config


def _fmt_yi(v):
    try:
        return f"{float(v)/1e8:+.2f}亿"
    except (TypeError, ValueError):
        return "-"


def render_console(results):
    L = []
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    L.append("=" * 78)
    L.append(f"  投资雷达  {now}")
    L.append("=" * 78)

    for r in results:
        s, q = r["stock"], r["quote"]
        L.append("")
        L.append(f"【{s['name']} {s['code']}】{s['role']}")

        if q:
            arrow = "↑" if q["pct"] > 0 else ("↓" if q["pct"] < 0 else "→")
            L.append(f"  {q['price']}  {arrow}{q['pct']:+.2f}%   "
                     f"换手{q['turnover_pct']:.2f}%  量比{q['vol_ratio']:.2f}")

        if r["val"]:
            L.append("  估值：" + " | ".join(r["val"]))

        tr = r["trend"]
        L.append(f"  趋势：{tr['verdict']}")
        for p in tr["points"]:
            L.append(f"    · {p}")

        al = r["alerts"]
        if al:
            L.append("  ⚠ 提醒：")
            for x in al:
                L.append(f"    ! {x}")

        # 研报
        rp = r["reports_scored"]
        if rp:
            L.append(f"  研报：{rp['count']}篇 / {rp['orgs']}家机构")
            latest = rp["latest"]
            L.append(f"    最新 {latest['date']} {latest['org']} [{latest['rating']}]")
            L.append(f"      {latest['title'][:50]}")
            if rp["ratings"]:
                L.append(f"    评级分布: {rp['ratings']}")
            if latest["eps_cur"]:
                L.append(f"    EPS预测: 今年{latest['eps_cur']} 明年{latest['eps_next']}")

        # 公告
        hi = [n for n in r["notices_scored"] if n["level"] == "high"]
        gd = [n for n in r["notices_scored"] if n["level"] == "good"]
        if hi:
            L.append(f"  🔴 需关注公告 {len(hi)} 条：")
            for n in hi[:6]:
                L.append(f"    [{n['date']}] {n['title'][:54]}")
                L.append(f"           命中: {','.join(n['risk'])}")
        if gd:
            L.append(f"  🟢 利好公告 {len(gd)} 条：")
            for n in gd[:4]:
                L.append(f"    [{n['date']}] {n['title'][:54]}")

        # 新闻
        rn = [n for n in r["news_scored"] if n["tag"] == "risk"][:5]
        if rn:
            L.append("  🔴 风险新闻：")
            for n in rn:
                L.append(f"    [{n['time'][:16]}] {n['title'][:50]}")
                L.append(f"           命中: {','.join(n['risk'])}")

        # 互动易
        if r["irm"]:
            answered = [x for x in r["irm"] if x["answer"]]
            if answered:
                L.append(f"  互动易（{len(answered)}条已回复）：")
                for x in answered[:3]:
                    L.append(f"    Q: {x['question'][:46]}")
                    L.append(f"    A: {x['answer'][:60]}")

        # 筹码
        if r["holders"]:
            h = r["holders"][0]
            L.append(f"  股东户数 {h['date']}: {h['num']} 户（环比 {h['ratio']}%）")
        if r["margin"]:
            m = r["margin"][0]
            L.append(f"  融资余额 {m['date']}: {m['rzye']/1e8:.2f}亿")

        # 解禁
        fut = [x for x in r["lockup"] if x["future"]]
        if fut:
            L.append("  ⚠ 待解禁：")
            for x in fut[:3]:
                L.append(f"    {x['date']}  {x['shares']/1e8:.2f}亿股  占比{x['ratio']}%")

        if r["lhb"]:
            L.append("  近期龙虎榜：")
            for x in r["lhb"][:3]:
                L.append(f"    [{x['date']}] 净买{_fmt_yi(x['net'])}  {x['reason'][:28]}")

        L.append(f"  —— 逻辑：{s['thesis']}")

    L.append("")
    L.append("=" * 78)
    tn = sum(len(r["notices_scored"]) for r in results)
    tw = sum(len(r["news_scored"]) for r in results)
    tr = sum(r["reports_scored"].get("count", 0) if r["reports_scored"] else 0 for r in results)
    L.append(f"  公告 {tn} / 新闻 {tw} / 研报 {tr}")
    L.append("=" * 78)
    return "\n".join(L)


def render_markdown(results):
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    L = [f"# 投资雷达报告 {now}", ""]

    for r in results:
        s, q = r["stock"], r["quote"]
        L.append(f"## {s['name']}（{s['code']}）· {s['role']}")
        L.append("")
        L.append(f"> **投资逻辑**：{s['thesis']}")
        L.append("")

        if q:
            L.append("| 指标 | 值 |")
            L.append("|---|---|")
            L.append(f"| 现价 | {q['price']} ({q['pct']:+.2f}%) |")
            L.append(f"| 总市值 | {q['mcap_yi']:.0f} 亿 |")
            L.append(f"| PE(TTM) / PB | {q['pe_ttm']:.1f} / {q['pb']:.2f} |")
            L.append(f"| 换手率 | {q['turnover_pct']:.2f}% |")
            L.append(f"| 量比 | {q['vol_ratio']:.2f} |")
            if q.get("high_1y"):
                L.append(f"| 一年区间 | {q['low_1y']} ~ {q['high_1y']}（{q['position']*100:.0f}%分位）|")
            if q.get("ma20"):
                L.append(f"| MA20 / MA60 | {q['ma20']} / {q['ma60']} |")
            L.append("")

        if r["val"]:
            L.append("**估值**")
            L.append("")
            for x in r["val"]:
                L.append(f"- {x}")
            L.append("")

        tr = r["trend"]
        L.append(f"**趋势**：{tr['verdict']}")
        L.append("")
        for p in tr["points"]:
            L.append(f"- {p}")
        L.append("")

        if r["alerts"]:
            L.append("**提醒**")
            L.append("")
            for x in r["alerts"]:
                L.append(f"- ⚠ {x}")
            L.append("")

        rp = r["reports_scored"]
        if rp:
            L.append(f"**研报（{rp['count']}篇 / {rp['orgs']}家）**")
            L.append("")
            L.append(f"评级分布：{rp['ratings']}")
            L.append("")
            latest = rp["latest"]
            if latest["eps_cur"]:
                L.append(f"EPS预测：今年 {latest['eps_cur']}，明年 {latest['eps_next']}")
                L.append("")
            L.append("| 日期 | 机构 | 评级 | 标题 |")
            L.append("|---|---|---|---|")
            for x in r["reports"][:10]:
                L.append(f"| {x['date']} | {x['org']} | {x['rating']} | {x['title'][:50]} |")
            L.append("")

        hi = [n for n in r["notices_scored"] if n["level"] == "high"]
        if hi:
            L.append(f"**🔴 需关注公告（{len(hi)}）**")
            L.append("")
            L.append("| 日期 | 标题 | 命中 |")
            L.append("|---|---|---|")
            for n in hi[:15]:
                L.append(f"| {n['date']} | [{n['title'][:58]}]({n['url']}) | {','.join(n['risk'])} |")
            L.append("")

        gd = [n for n in r["notices_scored"] if n["level"] == "good"]
        if gd:
            L.append(f"**🟢 利好公告（{len(gd)}）**")
            L.append("")
            for n in gd[:10]:
                L.append(f"- `{n['date']}` [{n['title'][:65]}]({n['url']})")
            L.append("")

        if r["irm"]:
            ans = [x for x in r["irm"] if x["answer"]]
            if ans:
                L.append("**投资者互动**")
                L.append("")
                for x in ans[:8]:
                    L.append(f"- **Q**（{x['time']}）：{x['question'][:100]}")
                    L.append(f"  **A**：{x['answer'][:200]}")
                L.append("")

        if r["holders"] or r["margin"]:
            L.append("**筹码 / 资金**")
            L.append("")
            if r["holders"]:
                h = r["holders"][0]
                L.append(f"- 股东户数（{h['date']}）：{h['num']}，环比 {h['ratio']}%")
            if r["margin"]:
                m = r["margin"][0]
                L.append(f"- 融资余额（{m['date']}）：{m['rzye']/1e8:.2f} 亿")
            L.append("")

        fut = [x for x in r["lockup"] if x["future"]]
        if fut:
            L.append("**待解禁**")
            L.append("")
            for x in fut[:5]:
                L.append(f"- {x['date']}：{x['shares']/1e8:.2f} 亿股，占比 {x['ratio']}%")
            L.append("")

        if r["notices_scored"]:
            L.append("<details><summary>全部公告（%d）</summary>" % len(r["notices_scored"]))
            L.append("")
            for n in r["notices_scored"]:
                f = "🔴" if n["level"] == "high" else ("🟢" if n["level"] == "good" else "⚪")
                L.append(f"- {f} `{n['date']}` [{n['title'][:70]}]({n['url']})")
            L.append("")
            L.append("</details>")
            L.append("")

        if r["news_scored"]:
            L.append("<details><summary>全部新闻（%d）</summary>" % len(r["news_scored"]))
            L.append("")
            for n in r["news_scored"][:40]:
                f = "🔴" if n["tag"] == "risk" else ("🟢" if n["tag"] == "good" else "⚪")
                L.append(f"- {f} `{n['time'][:16]}` [{n['title'][:70]}]({n['url']})")
            L.append("")
            L.append("</details>")
            L.append("")

    return "\n".join(L)


def save(results):
    ts = datetime.now().strftime("%Y%m%d_%H%M")
    md = config.OUT_DIR / f"radar_{ts}.md"
    md.write_text(render_markdown(results), encoding="utf-8")

    raw = []
    for r in results:
        q = r["quote"] or {}
        raw.append({
            "code": r["stock"]["code"],
            "name": r["stock"]["name"],
            "fetched_at": r["fetched_at"],
            "price": q.get("price"),
            "pct": q.get("pct"),
            "pe_ttm": q.get("pe_ttm"),
            "pb": q.get("pb"),
            "mcap_yi": q.get("mcap_yi"),
            "position": q.get("position"),
            "trend": r["trend"]["verdict"],
            "notices": len(r["notices_scored"]),
            "high_risk": len([n for n in r["notices_scored"] if n["level"] == "high"]),
            "reports": r["reports_scored"].get("count", 0) if r["reports_scored"] else 0,
            "news": len(r["news_scored"]),
        })
    js = config.DATA_DIR / f"radar_{ts}.json"
    js.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")

    (config.OUT_DIR / "latest.md").write_text(render_markdown(results), encoding="utf-8")
    return md, js


def push(text):
    ok = 0
    if config.WECHAT_WEBHOOK:
        try:
            r = requests.post(config.WECHAT_WEBHOOK,
                              json={"msgtype": "text", "text": {"content": text[:2000]}},
                              timeout=10)
            if r.json().get("errcode") == 0:
                ok += 1
        except Exception as e:
            print(f"  微信推送失败: {e}")

    if config.FEISHU_WEBHOOK:
        try:
            r = requests.post(config.FEISHU_WEBHOOK,
                              json={"msg_type": "text", "content": {"text": text[:4000]}},
                              timeout=10)
            if r.json().get("code") == 0:
                ok += 1
        except Exception as e:
            print(f"  飞书推送失败: {e}")

    tok, chat = config.TELEGRAM
    if tok and chat:
        try:
            r = requests.post(f"https://api.telegram.org/bot{tok}/sendMessage",
                              json={"chat_id": chat, "text": text[:4000]}, timeout=10)
            if r.json().get("ok"):
                ok += 1
        except Exception as e:
            print(f"  Telegram 推送失败: {e}")
    return ok
