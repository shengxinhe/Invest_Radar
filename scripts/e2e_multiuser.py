# -*- coding: utf-8 -*-
"""
M8 端到端验证：对真实运行中的服务发 HTTP 请求

用法：python scripts/e2e_multiuser.py [base_url]
默认 http://127.0.0.1:8010
"""
import io
import json
import sys
import urllib.error
import urllib.request

if sys.platform == "win32":
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                                      errors="replace")
    except Exception:
        pass

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8010"
PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  {'✓' if cond else '✗'} {name}"
          + (f"   [{detail}]" if detail and not cond else ""))


def call(method, path, body=None, token=None, cookie=None):
    url = BASE + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    if cookie:
        req.add_header("Cookie", cookie)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read().decode()), r.headers
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw), e.headers
        except Exception:
            return e.code, {"raw": raw[:200]}, e.headers
    except Exception as e:
        return 0, {"err": str(e)}, {}


print("=" * 68)
print(f"M8 端到端 · 真实 HTTP · {BASE}")
print("=" * 68)

# 0. 健康
st, j, _ = call("GET", "/api/health")
check("服务在线", st == 200 and j.get("ok"), f"{st} {j}")

# 1. 匿名访问私有接口 → 401
print("\n[1] 未进入时访问私有接口")
for p in ("/api/watch", "/api/ai/usage", "/api/me/key"):
    st, _, _ = call("GET", p)
    check(f"{p} → 401", st == 401, str(st))

# 2. 用两个名字进入
print("\n[2] 名字进入（无密码）")
st, ja, _ = call("POST", "/api/auth/enter", {"name": "测试A"})
check("A 进入成功", st == 200 and ja.get("ok"), str(ja)[:120])
ta = ja["data"]["token"]
ua = ja["data"]["user_id"]

st, jb, _ = call("POST", "/api/auth/enter", {"name": "测试B"})
check("B 进入成功", st == 200 and jb.get("ok"), str(jb)[:120])
tb = jb["data"]["token"]
ub = jb["data"]["user_id"]
check("A/B 是不同账户", ua != ub, f"{ua} vs {ub}")

# 3. 名字归一化：同一个人换个写法
st, ja2, _ = call("POST", "/api/auth/enter", {"name": "  测试A "})
check("『  测试A 』归到同一账户", ja2.get("data", {}).get("user_id") == ua,
      str(ja2.get("data")))

# 4. Bearer 独立可用（APK 场景，不带 Cookie）
print("\n[3] Bearer token 独立认证（模拟 APK）")
st, jw, _ = call("GET", "/api/auth/me", token=ta)
check("仅用 Bearer 能取 me", st == 200 and jw.get("data", {}).get("user_id") == ua,
      str(jw)[:120])

# 5. 自选隔离
print("\n[4] 自选股隔离")
call("POST", "/api/watch", {"code": "600519", "thesis": "A 的逻辑"}, token=ta)
call("POST", "/api/watch", {"code": "000001"}, token=ta)
st, wa, _ = call("GET", "/api/watch", token=ta)
codes_a = {x["code"] for x in wa["data"]}
check("A 有自己的自选", {"600519", "000001"} <= codes_a, str(codes_a))

st, wb, _ = call("GET", "/api/watch", token=tb)
codes_b = {x["code"] for x in wb["data"]}
check("B 看不到 A 的自选",
      not ({"600519", "000001"} & codes_b), str(codes_b))

call("POST", "/api/watch", {"code": "000858"}, token=tb)
st, wa2, _ = call("GET", "/api/watch", token=ta)
check("A 看不到 B 的 000858",
      "000858" not in {x["code"] for x in wa2["data"]})

# 6. 越权伪造 user_id
print("\n[5] 伪造 user_id 不能越权")
call("POST", "/api/watch", {"code": "601398", "user_id": ua}, token=tb)
st, wa3, _ = call("GET", "/api/watch", token=ta)
st2, wb3, _ = call("GET", "/api/watch", token=tb)
check("带 A 的 user_id 写入，落在 B 名下",
      "601398" in {x["code"] for x in wb3["data"]}
      and "601398" not in {x["code"] for x in wa3["data"]})
st, wq, _ = call("GET", f"/api/watch?user_id={ua}", token=tb)
check("查询串伪造 user_id 无效",
      "600519" not in {x["code"] for x in wq["data"]})

# 7. thesis 隔离
print("\n[6] thesis 隔离")
call("PUT", "/api/watch/600519/thesis",
     {"thesis": "A 改成 v2", "reason": "test"}, token=ta)
st, sa, _ = call("GET", "/api/stock/600519", token=ta)
check("A 的 thesis 是 v2",
      "v2" in ((sa.get("data") or {}).get("watch") or {}).get("thesis", ""),
      str((sa.get("data") or {}).get("watch"))[:100])

call("POST", "/api/watch", {"code": "600519", "thesis": "B 的逻辑"}, token=tb)
st, sb, _ = call("GET", "/api/stock/600519", token=tb)
st, sa2, _ = call("GET", "/api/stock/600519", token=ta)
check("B 的 thesis 独立",
      "B 的逻辑" in ((sb.get("data") or {}).get("watch") or {}).get("thesis", ""))
check("A 的 thesis 未被覆盖",
      "v2" in ((sa2.get("data") or {}).get("watch") or {}).get("thesis", ""))

# 8. Key 隔离
print("\n[7] DeepSeek Key 隔离")
st, ka, _ = call("GET", "/api/me/key", token=ta)
check("A 初始无 Key", ka["data"]["has_key"] is False, str(ka["data"]))

st, kr, _ = call("PUT", "/api/me/key", {"api_key": "sk-" + "z" * 32}, token=ta)
check("A 保存 Key 成功", st == 200 and kr.get("ok"), str(kr)[:120])

st, kb, _ = call("GET", "/api/me/key", token=tb)
check("B 看不到 A 的 Key", kb["data"]["has_key"] is False, str(kb["data"]))

st, ka2, _ = call("GET", "/api/me/key", token=ta)
raw = json.dumps(ka2, ensure_ascii=False)
check("接口不回传明文", "sk-" + "z" * 32 not in raw, raw[:120])
check("返回脱敏提示", "…" in ka2["data"].get("key_hint", "")
      or "****" in ka2["data"].get("key_hint", ""), str(ka2["data"]))

st, kd, _ = call("DELETE", "/api/me/key", token=ta)
check("A 能删除 Key", kd["data"]["has_key"] is False)

# 9. 共享行情
print("\n[8] 共享行情（同一只票两人都看得到）")
st_a, qa, _ = call("GET", "/api/stock/600519", token=ta)
st_b, qb, _ = call("GET", "/api/stock/600519", token=tb)
check("A 取到 600519", st_a == 200 and qa.get("ok"), str(st_a))
check("B 取到 600519", st_b == 200 and qb.get("ok"), str(st_b))

# 10. 退出
print("\n[9] 退出")
call("POST", "/api/auth/logout", token=ta)
st, _, _ = call("GET", "/api/watch", token=ta)
check("退出后该 token 失效", st == 401, str(st))
st, _, _ = call("GET", "/api/watch", token=tb)
check("B 不受影响", st == 200, str(st))

print("\n" + "=" * 68)
print(f"通过 {len(PASS)} 项 / 失败 {len(FAIL)} 项")
for f in FAIL:
    print("  ✗", f)
print("=" * 68)
sys.exit(1 if FAIL else 0)
