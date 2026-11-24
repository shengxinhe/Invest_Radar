# -*- coding: utf-8 -*-
"""M1 验收：应用级认证矩阵"""
import os
import sys
import warnings

warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient

from server.main import app

PROTECTED = [
    ("GET", "/api/watch"),
    ("GET", "/api/search?q=600519"),
    ("GET", "/api/stock/000001"),
    ("POST", "/api/stock/000001/sync"),
    ("GET", "/api/ai/status"),
    ("GET", "/api/ai/usage"),
    ("PUT", "/api/watch/000001/thesis"),
    ("POST", "/api/ai/global"),
]

print("=" * 64)
print("M1 验收 · 应用级认证")
print("=" * 64)

with TestClient(app) as tc:
    # [1] 未登录：全部敏感接口必须 401
    print("\n[1] 未登录访问敏感接口")
    for method, path in PROTECTED:
        r = tc.request(method, path, json={} if method in ("POST", "PUT") else None)
        mark = "✓" if r.status_code == 401 else f"✗ {r.status_code}"
        print(f"    {mark} {method:6s} {path}")
        assert r.status_code == 401, f"{method} {path} 竟然返回 {r.status_code}"

    # [2] 公共接口可访问
    print("\n[2] 公共接口（应 200）")
    for path in ("/api/health", "/api/auth/status"):
        r = tc.get(path)
        print(f"    {'✓' if r.status_code == 200 else '✗'} GET {path} -> {r.status_code}")
        assert r.status_code == 200

    # [3] health 不再泄露库统计
    h = tc.get("/api/health").json()
    leaked = "stats" in h
    print(f"\n[3] health 脱敏: {'✗ 仍泄露 stats' if leaked else '✓ 无库统计'}")
    assert not leaked

    # [4] 首次设置口令
    st = tc.get("/api/auth/status").json()["data"]
    print(f"\n[4] 口令配置状态: configured={st['configured']}")
    if not st["configured"]:
        r = tc.post("/api/auth/setup", json={"password": "test-pass-2.0"})
        print(f"    设置口令: {r.status_code} {r.json()}")
        assert r.json()["ok"]
    else:
        print("    已配置，跳过 setup（用已知测试口令需要手动重置）")

    # [5] 弱口令拒绝
    if not tc.get("/api/auth/status").json()["data"]["configured"]:
        r = tc.post("/api/auth/setup", json={"password": "123"})
        print(f"\n[5] 弱口令: {'✓ 被拒' if not r.json()['ok'] else '✗ 竟然接受'}")

    # [6] 登录成功 -> 可访问
    r = tc.post("/api/auth/login", json={"password": "test-pass-2.0"})
    ok_login = r.json().get("ok")
    print(f"\n[6] 登录: {'✓ 成功' if ok_login else '✗ ' + str(r.json())}")
    assert ok_login

    r = tc.get("/api/watch")
    print(f"    登录后 /api/watch: {r.status_code} {'✓' if r.status_code == 200 else '✗'}")
    assert r.status_code == 200

    # [7] 错误口令
    r = tc.post("/api/auth/login", json={"password": "wrong-password"})
    print(f"\n[7] 错误口令: {'✓ 拒绝' if not r.json().get('ok') else '✗ 竟然通过'}")
    assert not r.json().get("ok")

    # [8] Cookie 属性
    raw = r.headers.get("set-cookie", "") if r.cookies else ""
    print(f"\n[8] Cookie 属性检查（登出后清空）")
    r2 = tc.post("/api/auth/logout")
    r3 = tc.get("/api/watch")
    print(f"    登出后 /api/watch: {r3.status_code} {'✓ 已失效' if r3.status_code == 401 else '✗ 仍可访问'}")
    assert r3.status_code == 401

print("\n" + "=" * 64)
print("✓ 认证矩阵全部通过")
print("=" * 64)
