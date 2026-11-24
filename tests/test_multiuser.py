# -*- coding: utf-8 -*-
"""
M8 验收：无密码多用户隔离

覆盖用户要求的关键项：
  · A 加股票，B 看不到
  · B 删股票，不影响 A
  · A 改 thesis，不影响 B
  · A 的 AI 历史不能被 B 查看
  · A 的 DeepSeek Key 不能被 B 读取或使用
  · A/B 同时看同一只股票行情
  · 请求体里伪造 user_id 不能越权

运行：python tests/test_multiuser.py
（使用独立临时库，不碰 data/radar.db）
"""
import io
import os
import shutil
import sys
import tempfile
from pathlib import Path

warnings_ok = True
import warnings
warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# 先把数据库指到临时文件，必须在 import store 之前
TMP = Path(tempfile.mkdtemp(prefix="radar_mu_"))
from invest_radar import config
config.DATA_DIR = TMP
config.ROOT = ROOT

import invest_radar.store as store
store.DB_PATH = TMP / "radar.db"

if sys.platform == "win32":
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                                      errors="replace")
    except Exception:
        pass

from fastapi.testclient import TestClient
from server.main import app

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    mark = "✓" if cond else "✗"
    print(f"  {mark} {name}" + (f"  [{detail}]" if detail and not cond else ""))


def login(tc, name):
    r = tc.post("/api/auth/enter", json={"name": name})
    j = r.json()
    assert j.get("ok"), j
    return j["data"]


print("=" * 70)
print("M8 验收 · 名字即账户 + 数据隔离")
print("=" * 70)

with TestClient(app) as tc:
    # ---------- 0. 匿名访问必须 401 ----------
    print("\n[0] 未进入时访问私有接口")
    for path in ("/api/watch", "/api/ai/usage", "/api/me/key"):
        r = tc.get(path)
        check(f"{path} → 401", r.status_code == 401, f"got {r.status_code}")

    # ---------- 1. 名字归一化 ----------
    print("\n[1] 名字归一化（同一人不同写法不分裂账户）")
    a = login(tc, "阿明")
    tc.post("/api/auth/logout")
    a2 = login(tc, "  阿明  ")
    check("『阿明』与『  阿明  』同一 uid", a["user_id"] == a2["user_id"],
          f'{a["user_id"]} vs {a2["user_id"]}')

    tc.post("/api/auth/logout")
    b = login(tc, "小李")
    check("不同名字得到不同 uid", b["user_id"] != a["user_id"],
          f'{a["user_id"]} vs {b["user_id"]}')
    tc.post("/api/auth/logout")

    # ---------- 2. 自选股隔离 ----------
    print("\n[2] 自选股隔离")
    ta = login(tc, "阿明")
    ca = TestClient(app)
    ca.cookies.set("radar_sid", ta["token"])
    ca.headers["Authorization"] = f"Bearer {ta['token']}"

    r = ca.post("/api/watch", json={"code": "600519", "thesis": "A的茅台逻辑"})
    check("A 添加 600519", r.json().get("ok"), str(r.json())[:100])
    ca.post("/api/watch", json={"code": "000001"})

    tb = login(tc, "小李")
    cb = TestClient(app)
    cb.cookies.set("radar_sid", tb["token"])
    cb.headers["Authorization"] = f"Bearer {tb['token']}"

    wb = cb.get("/api/watch").json()["data"]
    check("B 看不到 A 的自选", all(x["code"] not in ("600519", "000001") for x in wb),
          str([x["code"] for x in wb]))

    cb.post("/api/watch", json={"code": "000858"})
    wa = ca.get("/api/watch").json()["data"]
    codes_a = {x["code"] for x in wa}
    check("A 看不到 B 加的 000858", "000858" not in codes_a, str(codes_a))
    check("A 仍有自己的两只", {"600519", "000001"} <= codes_a, str(codes_a))

    # ---------- 3. B 删股票不影响 A ----------
    print("\n[3] B 删除不影响 A")
    cb.delete("/api/watch/600519")
    wa = {x["code"] for x in ca.get("/api/watch").json()["data"]}
    check("B 删 600519 后 A 仍在", "600519" in wa, str(wa))

    # ---------- 4. thesis 隔离 ----------
    print("\n[4] thesis 隔离")
    r = ca.put("/api/watch/600519/thesis",
               json={"thesis": "A 修改后的逻辑 v2", "reason": "A 的笔记"})
    check("A 更新 thesis 接口成功", r.json().get("ok"), str(r.json())[:120])
    # 用 /api/stock/{code} 读回（它会带 watch 字段）
    ga = ca.get("/api/stock/600519").json().get("data") or {}
    theo_a = (ga.get("watch") or {}).get("thesis", "")
    check("A 的 thesis 已更新", "v2" in theo_a, theo_a)

    cb.post("/api/watch", json={"code": "600519", "thesis": "B 的完全不同逻辑"})
    gb = cb.get("/api/stock/600519").json().get("data") or {}
    theo_b = (gb.get("watch") or {}).get("thesis", "")
    ga2 = ca.get("/api/stock/600519").json().get("data") or {}
    theo_a2 = (ga2.get("watch") or {}).get("thesis", "")
    check("B 的 thesis 独立", "B 的完全不同逻辑" in theo_b, theo_b)
    check("A 的 thesis 未被 B 覆盖", "v2" in theo_a2, theo_a2)

    # ---------- 5. 越权：请求体伪造 user_id ----------
    print("\n[5] 伪造 user_id 不能越权")
    r = cb.post("/api/watch", json={"code": "601398", "user_id": a["user_id"]})
    check("B 带 A 的 user_id 添加", r.json().get("ok"))
    wa = {x["code"] for x in ca.get("/api/watch").json()["data"]}
    wb2 = {x["code"] for x in cb.get("/api/watch").json()["data"]}
    check("新股票进的是 B 的池子", "601398" in wb2, str(wb2))
    check("A 的池子没被污染", "601398" not in wa, str(wa))

    r = cb.get(f"/api/watch?user_id={a['user_id']}")
    codes = {x["code"] for x in r.json()["data"]}
    check("查询串伪造 user_id 无效", "600519" not in codes or "000858" in codes,
          str(codes))

    # ---------- 6. AI 历史隔离 ----------
    print("\n[6] AI 对话历史隔离（直接写库验证，不依赖是否配了 Key）")
    c0 = store.conn()
    c0.execute("INSERT INTO chat(id,scope,role,content,created_at,user_id) "
               "VALUES(?,?,?,?,?,?)", ("mu-a1", "global", "user", "A 的小秘密问题", 1, a["user_id"]))
    c0.execute("INSERT INTO chat(id,scope,role,content,created_at,user_id) "
               "VALUES(?,?,?,?,?,?)", ("mu-b1", "global", "user", "B 的另一个问题", 1, b["user_id"]))
    c0.commit()

    ha = ca.get("/api/chat/global").json()["data"]
    hb = cb.get("/api/chat/global").json()["data"]
    a_txt = " ".join(x["content"] for x in ha)
    b_txt = " ".join(x["content"] for x in hb)
    check("A 看得到自己的历史", "A 的小秘密问题" in a_txt, a_txt[:60])
    check("A 看不到 B 的提问", "B 的另一个问题" not in a_txt)
    check("B 看得到自己的历史", "B 的另一个问题" in b_txt, b_txt[:60])
    check("B 看不到 A 的提问", "A 的小秘密问题" not in b_txt)

    ca.delete("/api/chat/global")
    hb2 = cb.get("/api/chat/global").json()["data"]
    ha2 = ca.get("/api/chat/global").json()["data"]
    check("A 清空历史不影响 B", any("B 的另一个问题" in x["content"] for x in hb2),
          str(len(hb2)))
    check("A 自己的历史已清空", not any("A 的小秘密问题" in x["content"] for x in ha2))

    # entry_ai 缓存也按用户隔离
    c0.execute("INSERT INTO entry_ai(user_id,entry_id,model,summary,cache_key) "
               "VALUES(?,?,?,?,?)", (a["user_id"], "eid-test", "m1", "A 的解读", "k1"))
    c0.execute("INSERT INTO entry_ai(user_id,entry_id,model,summary,cache_key) "
               "VALUES(?,?,?,?,?)", (b["user_id"], "eid-test", "m1", "B 的解读", "k1"))
    c0.commit()
    rows = c0.execute("SELECT user_id, summary FROM entry_ai WHERE entry_id='eid-test'"
                      ).fetchall()
    check("同一词条可存两份解读", len(rows) == 2, str(rows))
    check("两份解读内容不同",
          {r["summary"] for r in rows} == {"A 的解读", "B 的解读"}, str(rows))

    # ---------- 7. API Key 隔离 ----------
    print("\n[7] DeepSeek Key 隔离")
    ka = ca.get("/api/me/key").json()["data"]
    check("A 初始无 Key", ka["has_key"] is False)

    r = ca.put("/api/me/key", json={"api_key": "sk-" + "a" * 32})
    check("A 保存 Key", r.json().get("ok"), str(r.json())[:120])

    kb = cb.get("/api/me/key").json()["data"]
    check("B 看不到 A 的 Key", kb["has_key"] is False, str(kb))

    body = ca.get("/api/me/key").text
    check("接口不回传明文 Key", "sk-" + "a" * 32 not in body, body[:120])

    # 直接查库：B 的 key 必须为空，且 A 的密文不是明文
    c = store.conn()
    rows = {r["user_id"]: r for r in
            c.execute("SELECT user_id, deepseek_key_enc, key_hint FROM user_secret")}
    check("A 的 Key 落库为密文",
          "sk-" + "a" * 32 not in (rows[a["user_id"]]["deepseek_key_enc"] or ""))
    check("B 无 user_secret 行或其密文为空",
          (b["user_id"] not in rows) or not rows[b["user_id"]]["deepseek_key_enc"])

    # ---------- 8. 共享行情 ----------
    print("\n[8] 同一只股票两人都能看行情")
    ra = ca.get("/api/stock/600519")
    rb = cb.get("/api/stock/600519")
    check("A 能取 600519 概览", ra.status_code == 200 and ra.json().get("ok"),
          str(ra.status_code))
    check("B 能取 600519 概览", rb.status_code == 200 and rb.json().get("ok"),
          str(rb.status_code))

    # ---------- 9. 退出 ----------
    print("\n[9] 退出登录")
    ca.post("/api/auth/logout")
    r = ca.get("/api/watch")
    check("退出后 401", r.status_code == 401, str(r.status_code))

print("\n" + "=" * 70)
print(f"通过 {len(PASS)} 项，失败 {len(FAIL)} 项")
if FAIL:
    print("失败项：")
    for f in FAIL:
        print("  -", f)
print("=" * 70)
shutil.rmtree(TMP, ignore_errors=True)
sys.exit(1 if FAIL else 0)
