# -*- coding: utf-8 -*-
"""
投资雷达 2.0 · 综合验收
一次跑完全链路：安全 / 数据库 / API / 分页 / 行情 / AI / 备份 / PWA / 运维
用法：python tests/test_acceptance.py
"""
import glob
import io
import json
import os
import sqlite3
import sys
import time
import warnings

warnings.filterwarnings("ignore")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
if sys.platform == "win32":
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    except Exception:
        pass

import requests

U = "http://127.0.0.1:8000"
PASSWORD = os.environ.get("RADAR_PASSWORD", "")  # 从环境变量读，不硬编码
s = requests.Session()
s.trust_env = False
s.proxies = {"http": None, "https": None}

results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))
    mark = "OK  " if ok else "FAIL"
    print(f"  [{mark}] {name}" + (f"  {detail}" if detail else ""))


def section(t):
    print(f"\n{'='*60}\n{t}\n{'='*60}")


# ============ 1. 安全 ============
section("1 / 安全")
r = s.get(f"{U}/api/watch", timeout=15)
check("未登录访问敏感接口返回 401", r.status_code == 401, f"got {r.status_code}")

r = s.get(f"{U}/api/health", timeout=15)
check("health 公开", r.status_code == 200)
check("health 不泄露库统计", "stats" not in r.text)

r = s.options(f"{U}/api/watch", timeout=15, headers={
    "Origin": "https://evil.example.com",
    "Access-Control-Request-Method": "POST"})
check("CORS 拒绝未知来源",
      r.headers.get("access-control-allow-origin") != "https://evil.example.com")

r = s.post(f"{U}/api/auth/login", json={"password": PASSWORD}, timeout=20)
check("口令登录成功", r.json().get("ok") is True)
check("会话 Cookie 已下发", bool(s.cookies.get("radar_sid")))

r = s.post(f"{U}/api/auth/login", json={"password": "wrong-password-x"}, timeout=20)
check("错误口令被拒", r.json().get("ok") is not True)

# ============ 2. 数据库 ============
section("2 / 数据库")
c = sqlite3.connect("data/radar.db")
check("integrity_check", c.execute("PRAGMA integrity_check").fetchone()[0] == "ok")

migs = [x[0] for x in c.execute("SELECT version FROM schema_migrations ORDER BY version")]
check(f"迁移共 {len(migs)} 个", len(migs) >= 6)

trg = c.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='trigger'").fetchone()[0]
check(f"FTS 触发器 {trg} 个", trg >= 6)

# trigram 需 >=3 字符；2 字走 LIKE 兜底
fts = c.execute("SELECT COUNT(*) FROM entry_fts WHERE entry_fts MATCH '会计师'").fetchone()[0]
check("FTS 中文子串可检索", fts > 0, f"{fts} 命中")

counts = {t: c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
          for t in ("stock", "watch", "entry", "entry_ai", "quote_daily",
                    "research_report", "notification_log", "app_session")}
check("核心数据存在", counts["stock"] > 5000 and counts["entry"] > 0, str(counts))
c.close()

# ============ 3. API 矩阵 ============
section("3 / API")
ENDPOINTS = [
    "/api/watch", "/api/search?q=000001", "/api/stock/000001",
    "/api/feed?limit=3", "/api/pulse", "/api/market/overview",
    "/api/ai/usage", "/api/ai/status", "/api/entries/states",
    "/api/notify/stats", "/api/research", "/api/reports",
    "/api/quotes/poller", "/api/watcher/queue", "/api/daily",
    "/api/stock/000001/entries?type=notice", "/api/stock/000001/extras",
    "/api/stock/000001/kline?period=day", "/api/watch/000001/thesis/history",
]
fails = []
for p in ENDPOINTS:
    try:
        code = s.get(f"{U}{p}", timeout=40).status_code
        if code != 200:
            fails.append((p, code))
    except Exception as e:
        fails.append((p, str(e)[:40]))
check(f"{len(ENDPOINTS)} 个端点全部可用", not fails, str(fails) if fails else "")

# ============ 4. Feed 分页 ============
section("4 / Feed 分页")
ids, cursor, pages = [], "", 0
while pages < 60:
    params = {"limit": 25}
    if cursor:
        params["cursor"] = cursor
    d = s.get(f"{U}/api/feed", params=params, timeout=25).json()["data"]
    ids.extend(x["id"] for x in d["items"])
    cursor = d.get("next_cursor")
    pages += 1
    if not cursor:
        break
check(f"翻 {pages} 页共 {len(ids)} 条，无重复", len(ids) == len(set(ids)))

# ============ 5. 行情 ============
section("5 / 行情")
st = s.get(f"{U}/api/quotes/poller", timeout=20).json()["data"]
check("共享轮询器运行中", st["errors"] == 0 and st["cached"] > 0, str(
    {k: st[k] for k in ("polls", "cached", "errors", "subscribers")}))
check("轮询间隔符合时段规则", st["interval"] in (5, 60), f"{st['interval']}s")

mk = s.get(f"{U}/api/market/overview", timeout=40).json()["data"]
check("大盘指数真实可用", mk["available"] and len(mk["indices"]) == 3,
      " / ".join(f"{i['name']} {i['price']}" for i in mk["indices"]) if mk["available"] else "无")

# ============ 6. AI ============
section("6 / AI")
u = s.get(f"{U}/api/ai/usage", timeout=20).json()["data"]
check("用量统计可读", isinstance(u, dict), json.dumps(u, ensure_ascii=False)[:90])
sa = s.get(f"{U}/api/ai/status", timeout=20).json()["data"]
check("LLM Key 已配置", sa.get("available") is True)
check("提示词版本号存在", bool(sa.get("prompt_version")), sa.get("prompt_version", ""))

# 实测一次解读（走缓存或真实调用）
ents = s.get(f"{U}/api/stock/000001/entries",
             params={"type": "notice", "days": 3650}, timeout=25).json()["data"]
if ents:
    eid = ents[0]["id"]
    segs, evs = {}, []
    with s.post(f"{U}/api/entry/{eid}/ai", timeout=300, stream=True) as resp:
        for line in resp.iter_lines(decode_unicode=False):
            if not line:
                continue
            line = line.decode("utf-8", "replace")
            if not line.startswith("data:"):
                continue
            m = json.loads(line[5:])
            evs.append(m["type"])
            if m["type"] == "segment":
                segs[m["key"]] = m["text"]
    check("AI 解读返回结构化段落", len(segs) >= 4, f"{len(segs)} 段 {list(segs)}")
    check("SSE 事件协议合规",
          all(e in ("start", "chunk", "segment", "warning", "error", "done", "progress")
              for e in evs))

# ============ 7. 备份 ============
section("7 / 备份")
baks = sorted(glob.glob("data/backups/radar_*.db"))
check(f"备份共 {len(baks)} 份", len(baks) >= 3)
if baks:
    import shutil
    tmp = os.path.join(os.environ["TEMP"], "accept_restore.db")
    shutil.copy2(baks[-1], tmp)
    c2 = sqlite3.connect(tmp)
    ig = c2.execute("PRAGMA integrity_check").fetchone()[0]
    n1 = c2.execute("SELECT COUNT(*) FROM stock").fetchone()[0]
    n2 = c2.execute("SELECT COUNT(*) FROM watch").fetchone()[0]
    c2.close()
    os.remove(tmp)
    check("备份可恢复且数据完整", ig == "ok" and n1 > 5000 and n2 > 0,
          f"{os.path.basename(baks[-1])} stock={n1} watch={n2}")

# ============ 8. PWA ============
section("8 / PWA")
for path, kw in [("/", "投资雷达"), ("/sw.js", "VERSION"),
                 ("/manifest.webmanifest", "name")]:
    try:
        body = s.get(f"{U}{path}", timeout=15).text
        check(f"{path} 可访问", kw in body or len(body) > 100)
    except Exception as e:
        check(f"{path} 可访问", False, str(e)[:40])

# ============ 9. 运维 ============
section("9 / 运维")
db_mb = os.path.getsize("data/radar.db") / 1024 / 1024
wal = "data/radar.db-wal"
wal_mb = os.path.getsize(wal) / 1024 / 1024 if os.path.exists(wal) else 0
check("数据库体积可控", db_mb < 50, f"{db_mb:.2f} MB")
check("WAL 未异常膨胀", wal_mb < 10, f"{wal_mb:.2f} MB")

c3 = sqlite3.connect("data/radar.db")
n_q = c3.execute("SELECT COUNT(*) FROM quote").fetchone()[0]
n_qd = c3.execute("SELECT COUNT(*) FROM quote_daily").fetchone()[0]
c3.close()
check("行情明细已做保留策略", n_q < 5000, f"明细 {n_q} 行 / 日快照 {n_qd} 行")

# 周末快照检查
import datetime as dt
n_weekend = 0
c4 = sqlite3.connect("data/radar.db")
for (d,) in c4.execute("SELECT DISTINCT date FROM quote_daily"):
    try:
        if dt.datetime.strptime(d, "%Y-%m-%d").weekday() >= 5:
            n_weekend += 1
    except Exception:
        pass
c4.close()
check("日快照不含周末", n_weekend == 0, f"{n_weekend} 天")

# ============ 汇总 ============
section("汇总")
total = len(results)
passed = sum(1 for _, ok, _ in results if ok)
print(f"\n  总计 {total} 项，通过 {passed}，失败 {total - passed}\n")
if total != passed:
    print("  失败明细：")
    for name, ok, detail in results:
        if not ok:
            print(f"    - {name} {detail}")
    sys.exit(1)
print("  全部通过 ✓\n")
