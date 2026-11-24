# -*- coding: utf-8 -*-
"""
M4 · 风险守望者
轮询关注池的新公告，把 level=risk / positive 的新词条写入告警队列。
被 server 的 /api/watcher/tick 或 DSH schedule 唤醒时执行。

输出: data/alerts_queue.json
  [{"id","code","name","type","title","url","level","published_at","first_seen"}]
"""
import io
import json
import sys
from datetime import datetime
from pathlib import Path

from . import config, fetcher, store, sync
from . import notify
from .analyzer import score_notices

QUEUE = config.DATA_DIR / "alerts_queue.json"
SEEN = config.DATA_DIR / "watcher_seen.json"


def _load_json(p, default):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return default


def _save_json(p, obj):
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")


def watch_tick(quiet=False, full_sync=False):
    """
    一轮检查。返回 dict 摘要。
    full_sync=True 时同时拉新闻/研报/互动（慢）；默认只查公告（快）。
    """
    store.init()
    now = int(datetime.now().timestamp())
    seen = _load_json(SEEN, {})          # {entry_id: first_seen_ts}
    queue = _load_json(QUEUE, [])

    queued_ids = {a["id"] for a in queue}
    report = {"checked": 0, "new": 0, "alerts": [], "errors": [], "ts": now}
    watch_list = store.list_watch()
    seen_changed = False

    for w in watch_list:
        code = w["code"]
        try:
            notices = fetcher.get_notices(code)
        except Exception as e:
            report["errors"].append(f"{code}: {str(e)[:60]}")
            continue
        report["checked"] += len(notices)
        scored = score_notices(notices)

        for n in scored:
            eid = store.make_entry_id(code, "notice", n.get("url") or n["title"])
            was_seen = eid in seen          # 关键：入队判断必须用"本轮之前"的 seen
            if not was_seen:
                seen[eid] = now
                seen_changed = True
            # 风险/利好 且 从未见过的才入队（seen/queue 双重防重）
            if n["level"] in ("high", "good") and not was_seen and eid not in queued_ids:
                # M5: 三级分级 + 72h 去重
                prio = notify.classify(n["title"], n["level"])
                if notify.already_notified(code, n["title"]):
                    continue
                notify.log_notification(
                    prio, code, n["title"], eid,
                    status="queued" if prio in ("p1", "p2") else "skipped")
                queue.append({
                    "id": eid,
                    "code": code,
                    "name": w["name"],
                    "type": "notice",
                    "title": n["title"],
                    "url": n.get("url", ""),
                    "level": "risk" if n["level"] == "high" else "positive",
                    "priority": prio,          # M5: p1/p2/p3
                    "keywords": n.get("risk") or n.get("good") or [],
                    "published": n.get("date", ""),
                    "first_seen": now,
                })
                queued_ids.add(eid)
                if prio in ("p1", "p2"):
                    report["new"] += 1
                    tag = "🚨" if prio == "p1" else "📌"
                    report["alerts"].append(
                        f"{tag}[{prio.upper()}] [{w['name']}] {n['title'][:40]}")

        # 入库（去重靠 entry 表主键）
        sync.sync_notices(code, notices, w)

    # 只保留 7 天内的已见记录，防膨胀
    cutoff = now - 7 * 86400
    seen = {k: v for k, v in seen.items() if v > cutoff}
    # 队列保留 3 天
    queue = [a for a in queue if a.get("first_seen", 0) > now - 3 * 86400]

    if seen_changed:
        _save_json(SEEN, seen)
    _save_json(QUEUE, queue)

    if not quiet:
        print(f"检查 {len(watch_list)} 只 | 公告 {report['checked']} 条 | "
              f"新告警 {report['new']} 条")
        for a in report["alerts"]:
            print("  " + a)
        for e in report["errors"]:
            print("  ! " + e)
    return report


def make_daily_brief():
    """晨报数据：关注池快照 + 最近24h词条统计"""
    store.init()
    items = store.list_watch()
    out = {"ts": int(datetime.now().timestamp()), "stocks": []}
    now = int(datetime.now().timestamp())

    for w in items:
        q = store.latest_quote(w["code"])
        s = {"code": w["code"], "name": w["name"], "thesis": w["thesis"],
             "price": q["price"] if q else None,
             "pct": q["pct"] if q else None,
             "pe": q["pe"] if q else None, "pb": q["pb"] if q else None}
        # 24h 内词条
        for t, label in (("notice", "公告"), ("news", "新闻"),
                          ("qa", "互动"), ("report", "研报")):
            rows = store.list_entries(w["code"], t, days=1, limit=50)
            s[label] = [{"title": r["title"], "level": r["level"], "id": r["id"]}
                        for r in rows]
        out["stocks"].append(s)
    return out


if __name__ == "__main__":
    import argparse
    if sys.platform == "win32":
        try:
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        except Exception:
            pass
    p = argparse.ArgumentParser()
    p.add_argument("--brief", action="store_true", help="生成晨报数据")
    a = p.parse_args()
    if a.brief:
        b = make_daily_brief()
        print(json.dumps(b, ensure_ascii=False, indent=1)[:2000])
    else:
        watch_tick()
