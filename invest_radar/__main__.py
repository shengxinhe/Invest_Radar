# -*- coding: utf-8 -*-
"""投资雷达 —— 入口"""
import io
import sys
from datetime import datetime

if sys.platform == "win32":
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
    except Exception:
        pass

from . import analyzer, config, dashboard, fetcher, reporter, store, sync


def _progress(name, state, detail):
    """命令行进度条（替代原来 fetcher 里的 print）"""
    if state == "ok":
        print(f"  {name}... OK {detail}")
    elif state == "fail":
        print(f"  {name}... FAIL {detail}")


def run(push=False, save=True, codes=None):
    print("=" * 78)
    print(f"投资雷达启动  {datetime.now():%Y-%m-%d %H:%M:%S}")
    print("=" * 78)

    store.init()

    watch = store.list_watch()
    if codes:
        watch = [s for s in watch if s["code"] in codes]

    results = []
    total_new = {}

    for stock in watch:
        print(f"\n>>> {stock['code']} {stock['name']}")

        # 走 sync 层：抓取 + 入库
        r = sync.sync_all(stock["code"], stock, progress=_progress)
        for k, v in r["new"].items():
            total_new[k] = total_new.get(k, 0) + v

        # 组装成 reporter 需要的结构
        raw = r["raw"]
        d = {
            "stock": stock,
            "quote": raw.get("quote"),
            "kline": raw.get("kline"),
            "notices": raw.get("notices") or [],
            "news": raw.get("news") or [],
            "reports": raw.get("reports") or [],
            "irm": raw.get("irm") or [],
            "lhb": raw.get("lhb") or [],
            "lockup": raw.get("lockup") or [],
            "margin": raw.get("margin") or [],
            "holders": raw.get("holders") or [],
        }
        stock.setdefault("tags", stock.get("tags") or [])
        d["news_scored"] = analyzer.score_news(d["news"], stock)
        d["notices_scored"] = analyzer.score_notices(d["notices"])
        d["reports_scored"] = analyzer.score_reports(d["reports"])
        d["val"] = analyzer.valuation(d["quote"])
        d["trend"] = analyzer.trend_read(d["quote"])
        d["fin"] = []
        d["alerts"] = analyzer.alerts(d)
        results.append(d)

    text = reporter.render_console(results)
    print("\n" + text)

    if total_new:
        print("\n入库新增: " + "  ".join(f"{k}+{v}" for k, v in total_new.items()))
    print("库统计: " + str(store.stats()))

    if save:
        md, js = reporter.save(results)
        print(f"\n已存档: {md}")

    if push:
        n = reporter.push(text)
        print(f"\n推送成功 {n} 个渠道")

    return results


def main():
    import argparse
    p = argparse.ArgumentParser(description="投资雷达")
    p.add_argument("--push", action="store_true", help="推送到配置的渠道")
    p.add_argument("--no-save", action="store_true", help="不出文本报告")
    p.add_argument("--codes", nargs="*", help="只跑指定代码")
    p.add_argument("--board", action="store_true", help="生成可视化看板")
    p.add_argument("--open", action="store_true", dest="open_it", help="生成后自动打开看板")
    a = p.parse_args()

    if a.board or a.open_it:
        path = dashboard.build(codes=a.codes)
        if a.open_it:
            import os
            os.startfile(str(path))
        return

    run(push=a.push, save=not a.no_save, codes=a.codes)


if __name__ == "__main__":
    main()
