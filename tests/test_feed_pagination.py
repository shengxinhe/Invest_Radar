# -*- coding: utf-8 -*-
"""M1 验收：/api/feed 分页正确性（不重复/不遗漏/同时间戳/切筛选）"""
import io
import os
import sys
import warnings

warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if sys.platform == "win32":
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    except Exception:
        pass

from fastapi.testclient import TestClient

from server.main import app


def crawl(tc, flt=None, page=25):
    """翻完所有页，返回 (ids, pages)"""
    ids, pages, cursor = [], 0, ""
    while True:
        params = {"limit": page}
        if cursor:
            params["cursor"] = cursor
        if flt:
            params["filter"] = flt
        r = tc.get("/api/feed", params=params).json()
        assert r["ok"], r
        d = r["data"]
        items = d["items"]
        pages += 1
        ids.extend(x["id"] for x in items)
        cursor = d.get("next_cursor")
        if not cursor or not items:
            break
        if pages > 100:
            raise AssertionError("分页疑似死循环")
    return ids, pages


with TestClient(app) as tc:
    print("=" * 64)
    print("M1 验收 · /api/feed 复合 keyset 分页")
    print("=" * 64)

    # --- 用例1：全量翻页 无重复 ---
    ids, pages = crawl(tc)
    dup = len(ids) - len(set(ids))
    print(f"\n[1] 全量翻页: {pages} 页, {len(ids)} 条, 重复 {dup} 条")
    assert dup == 0, f"存在重复记录 {dup}"
    print("    ✓ 无重复")

    # --- 用例2：与数据库总数一致（不漏） ---
    from invest_radar import store
    c = store.conn()
    total = c.execute("SELECT COUNT(*) n FROM entry WHERE code!='MARKET'").fetchone()["n"]
    print(f"\n[2] 覆盖完整性: 翻到 {len(ids)} 条 / 库内 {total} 条")
    assert len(ids) == total, f"遗漏 {total - len(ids)} 条"
    print("    ✓ 无遗漏")

    # --- 用例3：顺序严格单调（展示序 = level ASC, type ASC, time DESC, id DESC）---
    lv_rank = {"risk": 0, "positive": 1, "neutral": 2}
    tp_rank = {"notice": 0, "qa": 1, "news": 2, "report": 3}
    keys = []
    cursor = ""
    while True:
        params = {"limit": 25}
        if cursor:
            params["cursor"] = cursor
        d = tc.get("/api/feed", params=params).json()["data"]
        for x in d["items"]:
            # id DESC：把 id 取负字节序，使元组比较与 SQL 语义一致
            inv_id = tuple(-b for b in x["id"].encode())
            keys.append((lv_rank.get(x["level"], 2), tp_rank.get(x["type"], 9),
                         -x["published_at"], inv_id))
        cursor = d.get("next_cursor")
        if not cursor:
            break
    mono = all(keys[i] <= keys[i + 1] for i in range(len(keys) - 1))
    print(f"\n[3] 展示序单调性: {'✓ 严格有序' if mono else '✗ 顺序错乱'}")
    assert mono

    # --- 用例4：相同时间戳切片正确 ---
    dup_ts = c.execute("""
        SELECT published_at, COUNT(*) n FROM entry WHERE code!='MARKET'
        GROUP BY published_at HAVING n > 1 ORDER BY n DESC LIMIT 1
    """).fetchone()
    if dup_ts:
        ts, n = dup_ts["published_at"], dup_ts["n"]
        got = []
        cursor = ""
        while True:
            params = {"limit": 3}
            if cursor:
                params["cursor"] = cursor
            d = tc.get("/api/feed", params=params).json()["data"]
            for x in d["items"]:
                if x["published_at"] == ts:
                    got.append(x["id"])
            cursor = d.get("next_cursor")
            if not cursor:
                break
        print(f"\n[4] 同时间戳: published_at={ts} 有 {n} 条, 翻页取到 {len(set(got))} 条")
        assert len(set(got)) == n, f"同时间戳切片失败"
        print("    ✓ 同时间戳全部取到且不重复")
    else:
        print("\n[4] 同时间戳: 库内无重复时间戳样本，跳过")

    # --- 用例5：切筛选后游标重置 ---
    ids_r, _ = crawl(tc, flt="risk")
    d_risk = c.execute("SELECT COUNT(*) n FROM entry WHERE code!='MARKET' AND level='risk'").fetchone()["n"]
    print(f"\n[5] risk 筛选: {len(ids_r)} 条 / 库内 {d_risk} 条, 重复 {len(ids_r)-len(set(ids_r))}")
    assert len(ids_r) == d_risk and len(ids_r) == len(set(ids_r))
    print("    ✓ 筛选独立正确，无串页")

    ids_p, _ = crawl(tc, flt="positive")
    d_pos = c.execute("SELECT COUNT(*) n FROM entry WHERE code!='MARKET' AND level='positive'").fetchone()["n"]
    print(f"[6] positive 筛选: {len(ids_p)} 条 / 库内 {d_pos} 条")
    assert len(ids_p) == d_pos
    print("    ✓ positive 也正确")

    # --- 用例7：非法游标不 500 ---
    for bad in ("garbage", "1:2:xx:abc", "9999999999999", "", "a:b:c:d"):
        r = tc.get("/api/feed", params={"cursor": bad, "limit": 5})
        assert r.status_code == 200, f"非法游标 {bad!r} 返回 {r.status_code}"
    print("\n[7] 非法游标容错: ✓ 全部 200")

    print("\n" + "=" * 64)
    print("✓ /api/feed 分页测试全部通过")
    print("=" * 64)
    c.close()
