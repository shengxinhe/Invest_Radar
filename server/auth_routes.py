# -*- coding: utf-8 -*-
"""M1 · 认证路由（登录/登出/状态/首次设置口令）"""
import os

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel

from . import security as sec

router = APIRouter()


class LoginIn(BaseModel):
    password: str


def _client_ip(request: Request) -> str:
    return (request.headers.get("x-forwarded-for", "").split(",")[0].strip()
            or (request.client.host if request.client else "unknown"))


@router.get("/api/auth/status")
def auth_status(request: Request):
    """公开：告知前端是否已配置口令、当前是否已登录"""
    return {
        "ok": True,
        "data": {
            "configured": sec.password_configured(),
            "authenticated": sec.valid_session(request.cookies.get(sec.COOKIE)),
            "auth_disabled": not sec.auth_enabled(),   # M8: 前端据此跳过登录页
        },
    }


@router.post("/api/auth/setup")
def auth_setup(body: LoginIn, request: Request, response: Response):
    """首次设置口令（仅在未配置时允许，设置后立即登录）"""
    if sec.password_configured():
        return {"ok": False, "msg": "口令已设置，请使用登录"}
    pw = (body.password or "").strip()
    if len(pw) < 8:
        return {"ok": False, "msg": "口令至少 8 位"}
    h = sec.hash_password(pw)
    # 写入 .env（持久化）
    root = sec.DATA_DIR.parent
    env = root / ".env"
    lines = []
    if env.exists():
        lines = [l for l in env.read_text(encoding="utf-8").splitlines()
                 if not l.startswith("RADAR_PASSWORD_HASH")]
    lines.append(f"RADAR_PASSWORD_HASH={h}")
    env.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.environ["RADAR_PASSWORD_HASH"] = h

    token = sec.create_session(_client_ip(request), request.headers.get("user-agent", ""))
    response.set_cookie(sec.COOKIE, token, max_age=sec.SESSION_TTL,
                        httponly=True, samesite="lax", path="/")
    return {"ok": True, "data": {"authenticated": True}}


@router.post("/api/auth/login")
def auth_login(body: LoginIn, request: Request, response: Response):
    ip = _client_ip(request)
    if not sec._check_rate(ip):
        return {"ok": False, "msg": "尝试过于频繁，请 5 分钟后再试"}
    stored = sec._password_hash()
    if not stored:
        return {"ok": False, "msg": "尚未设置口令"}
    if not sec.verify_password(body.password or "", stored):
        sec._record_fail(ip)
        return {"ok": False, "msg": "口令错误"}
    token = sec.create_session(ip, request.headers.get("user-agent", ""))
    response.set_cookie(sec.COOKIE, token, max_age=sec.SESSION_TTL,
                        httponly=True, samesite="lax", path="/")
    return {"ok": True, "data": {"authenticated": True}}


@router.post("/api/auth/logout")
def auth_logout(request: Request, response: Response):
    sec.drop_session(request.cookies.get(sec.COOKIE))
    response.delete_cookie(sec.COOKIE, path="/")
    return {"ok": True}
