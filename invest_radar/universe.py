# -*- coding: utf-8 -*-
"""
M2 · 全市场股票主数据更新
用法：
    python -m invest_radar.universe          # 全量更新（增量合入）
    python -m invest_radar.universe --force  # 强制重建 FTS

数据源：akshare.stock_info_a_code_name（东财，5000+ 只，含主板/创业板/科创板/北交所）
TTL：24h，server 会在 need_refresh 时自动调用
"""
import io
import sys
import time
from datetime import datetime

from . import store
from .pyutil import to_pinyin


def update_universe(force=False):
    """拉全 A 股并入库。返回 (总数, 新增数)"""
    if not force and not store.need_refresh("universe"):
        return store.count_stocks(), 0

    import akshare as ak
    df = ak.stock_info_a_code_name()
    if df is None or df.empty:
        raise RuntimeError("拉取全 A 股列表失败")

    rows = []
    seen = set()
    for _, r in df.iterrows():
        code = str(r["code"]).zfill(6)
        if code in seen:
            continue
        seen.add(code)
        name = str(r["name"]).replace(" ", "").replace("Ａ", "A").replace("Ｂ", "B")
        market = "sh" if code.startswith(("6", "9")) else (
            "bj" if code.startswith(("4", "8")) else "sz")
        rows.append((code, name, to_pinyin(name), market, "", "[]"))

    t0 = time.time()
    store.bulk_upsert_stocks(rows)
    elapsed = time.time() - t0

    store.mark_fetched("universe")
    return len(rows), store.count_stocks() - len(rows)


def main():
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--force", action="store_true", help="跳过 TTL 强制更新")
    a = p.parse_args()

    print("=" * 60)
    print(f"全 A 股主数据更新  {datetime.now():%Y-%m-%d %H:%M:%S}")
    print("=" * 60)
    store.init()
    total, new = update_universe(force=a.force)
    print(f"入库 {total} 只（其中本次新增 {max(new,0)}）")
    print(f"库统计: {store.stats()}")

    # 抽查
    print("\n搜索抽查:")
    for q in ["000060", "zjln", "岭南", "gzgf", "贵州茅台", "mt"]:
        r = store.search_stock(q, 5)
        names = "  ".join(f"{x['code']} {x['name']}" for x in r[:3])
        print(f"  {q:8s} -> {names or '(空)'}")


if __name__ == "__main__":
    # 仅在作为脚本运行时包装 stdout（import 时不碰全局流）
    if sys.platform == "win32":
        try:
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                                          errors="replace")
        except Exception:
            pass
    main()
