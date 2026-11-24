# -*- coding: utf-8 -*-
"""
M8 · 认证路由（名字即账户，无密码）

接口
----
GET  /api/auth/status   公开：是否已有用户、当前是否已识别身份
GET  /api/auth/users    公开：最近活跃的几个名字（登录页提示用）
POST /api/auth/enter    {name} → 进入（不存在则创建）
GET  /api/auth/me       需登录：当前身份 + 是否配了自己的 Key
POST /api/auth/logout   需登录：退出
PUT  /api/auth/me       {name} → 改名（保留 user_id，不丢数据）
"""
import time

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel

from . import identity as ident

router = APIRouter()


class EnterIn(BaseModel):
    name: str


class RenameIn(BaseModel):
    name: str


def _client_ip(request: Request) -> str:
    return (request.headers.get("x-forwarded-for", "").split(",")[0].strip()
            or (request.client.host if request.client else "unknown"))


def _set_session(response: Response, token: str):
    """Cookie 给网页；token 同时在响应体返回给 APK"""
    response.set_cookie(
        ident.COOKIE, token, max_age=ident.SESSION_TTL,
        httponly=True, samesite="lax", path="/",
        # 生产环境走 HTTPS，由 Caddy 终止；secure 在本地 http 下要关，
        # 所以按请求是否 https 动态设置，见下面 _cookie_secure
    )


def _cookie_secure(request: Request) -> bool:
    proto = (request.headers.get("x-forwarded-proto") or "").lower()
    return proto == "https" or request.url.scheme == "https"


@router.get("/api/auth/status")
def auth_status(request: Request):
    uid = ident.resolve_session(ident.token_from_request(request))
    total = len(ident.list_users(limit=999))
    return {
        "ok": True,
        "data": {
            "has_users": total > 0,
            "user_count": total,
            "authenticated": bool(uid),
            "user": ident.get_user(uid)["name"] if uid else None,
        },
    }


@router.get("/api/auth/users")
def auth_users(limit: int = 20):
    """登录页下拉提示：只暴露名字与最近活跃时间，不泄露任何业务数据"""
    rows = ident.list_users(min(max(limit, 1), 50))
    return {"ok": True, "data": [{"name": r["name"]} for r in rows]}


@router.post("/api/auth/enter")
def auth_enter(body: EnterIn, request: Request, response: Response):
    try:
        user, created = ident.enter(body.name)
    except ValueError as e:
        return {"ok": False, "msg": str(e)}
    except Exception as e:
        return {"ok": False, "msg": f"进入失败：{str(e)[:80]}"}

    token = ident.create_session(user["id"], _client_ip(request),
                                 request.headers.get("user-agent", ""))
    response.set_cookie(ident.COOKIE, token, max_age=ident.SESSION_TTL,
                        httponly=True, samesite="lax", path="/",
                        secure=_cookie_secure(request))
    return {
        "ok": True,
        "data": {
            "user_id": user["id"],
            "name": user["name"],
            "created": created,
            "token": token,        # APK 用；网页会忽略并依赖 Cookie
        },
    }


@router.get("/api/auth/me")
def auth_me(request: Request):
    uid = ident.uid_from_request(request)
    user = ident.get_user(uid) or {}
    from . import usersecret
    sec = usersecret.get_public(uid)
    return {
        "ok": True,
        "data": {
            "user_id": uid,
            "name": user.get("name", ""),
            "created_at": user.get("created_at"),
            "last_seen_at": user.get("last_seen_at"),
            "ai": sec,
        },
    }


@router.put("/api/auth/me")
def auth_rename(body: RenameIn, request: Request):
    uid = ident.uid_from_request(request)
    try:
        key = ident.normalize_name(body.name)
    except ValueError as e:
        return {"ok": False, "msg": str(e)}
    disp = ident.display_name(body.name) or key

    other = ident.find_user_by_key(key)
    if other and other["id"] != uid:
        return {"ok": False, "msg": "这个名字已被占用"}

    c = ident._db()
    c.execute("UPDATE app_user SET name=?, name_key=? WHERE id=?", (disp, key, uid))
    c.commit()
    return {"ok": True, "data": {"user_id": uid, "name": disp}}


@router.post("/api/auth/logout")
def auth_logout(request: Request, response: Response):
    ident.drop_session(ident.token_from_request(request))
    response.delete_cookie(ident.COOKIE, path="/")
    return {"ok": True}
