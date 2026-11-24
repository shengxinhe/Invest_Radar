# -*- coding: utf-8 -*-
"""
M1 · 应用级认证
单用户场景：口令 + 服务端 Session（HttpOnly Cookie）。
- 密钥随机生成并持久化到 data/.session_secret（权限 600 等价）
- 登录失败限流（同 IP 5 次/5 分钟）
- Session 有效期 30 天，可主动登出
- 密码用 scrypt 派生的口令哈希存 .env
"""
import hashlib
import hmac
import os
import secrets
import time
from pathlib import Path

from fastapi import Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
SECRET_FILE = DATA_DIR / ".session_secret"
COOKIE = "radar_sid"
SESSION_TTL = 30 * 24 * 3600


def _load_env_file():
    """自行加载 .env（不能依赖 llm/client.py，导入顺序不保证）"""
    env_path = DATA_DIR.parent / ".env"
    if not env_path.exists():
        return
    try:
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())
    except Exception:
        pass


_load_env_file()

# 认证总开关：.env 里 AUTH_DISABLED=1 时跳过所有口令校验
# 想恢复密码登录：把 .env 那行改成 AUTH_DISABLED=0 或删掉，重启即可
AUTH_DISABLED = os.environ.get("AUTH_DISABLED", "0").strip() in ("1", "true", "True")

# ---- 运行时状态 ----
_sessions: dict[str, dict] = {}     # sid -> {created, last, ip}
_fail_log: dict[str, list] = {}     # ip -> [ts,...]
_FAIL_WINDOW = 300
_FAIL_MAX = 5

# 免认证路径（只读状态 / 登录相关；setup 仅未配置口令时可用，由路由自身校验）
PUBLIC_PATHS = {
    "/api/health",
    "/api/auth/login",
    "/api/auth/logout",
    "/api/auth/setup",
    "/api/auth/status",
}
PUBLIC_PREFIXES = (
    "/assets/",
    "/manifest.webmanifest",
    "/sw.js",
    "/icon-",
    "/apple-touch-icon",
)
# 公开的精确路径（前端壳：登录页必须能加载）
PUBLIC_EXACT = {"/", "/index.html", "/favicon.ico"}


def _load_secret() -> bytes:
    DATA_DIR.mkdir(exist_ok=True)
    if SECRET_FILE.exists():
        return SECRET_FILE.read_bytes()
    s = secrets.token_bytes(48)
    SECRET_FILE.write_bytes(s)
    try:
        os.chmod(SECRET_FILE, 0o600)
    except Exception:
        pass
    return s


SECRET = _load_secret()


# ---- 口令 ----
def _password_hash() -> str:
    """从 .env 读 RADAR_PASSWORD_HASH；未设置则返回空（首次登录时创建）"""
    return os.environ.get("RADAR_PASSWORD_HASH", "").strip()


def hash_password(pw: str) -> str:
    salt = secrets.token_hex(16)
    dk = hashlib.scrypt(pw.encode(), salt=salt.encode(), n=16384, r=8, p=1, dklen=32)
    return f"scrypt${salt}${dk.hex()}"


def verify_password(pw: str, stored: str) -> bool:
    try:
        algo, salt, hexdk = stored.split("$", 2)
        dk = hashlib.scrypt(pw.encode(), salt=salt.encode(), n=16384, r=8, p=1, dklen=32)
        return hmac.compare_digest(dk.hex(), hexdk)
    except Exception:
        return False


def password_configured() -> bool:
    return bool(_password_hash())


# ---- 限流 ----
def _check_rate(ip: str) -> bool:
    now = time.time()
    arr = [t for t in _fail_log.get(ip, []) if now - t < _FAIL_WINDOW]
    _fail_log[ip] = arr
    return len(arr) < _FAIL_MAX


def _record_fail(ip: str):
    _fail_log.setdefault(ip, []).append(time.time())


# ---- Session（M3: 落库，重启保持登录） ----

def _db():
    from invest_radar import store
    store.init()
    return store.conn()


def _sign(sid: str) -> str:
    mac = hmac.new(SECRET, sid.encode(), hashlib.sha256).hexdigest()[:32]
    return f"{sid}.{mac}"


def _unsign(token: str) -> str | None:
    if not token or "." not in token:
        return None
    sid, mac = token.rsplit(".", 1)
    expect = hmac.new(SECRET, sid.encode(), hashlib.sha256).hexdigest()[:32]
    return sid if hmac.compare_digest(mac, expect) else None


def create_session(ip: str, ua: str = "") -> str:
    sid = secrets.token_urlsafe(32)
    now = int(time.time())
    try:
        c = _db()
        c.execute("""INSERT OR REPLACE INTO app_session
                     (sid,created_at,last_seen,ip,ua) VALUES(?,?,?,?,?)""",
                  (sid, now, now, ip, ua[:200]))
        c.commit()
    except Exception:
        _sessions[sid] = {"created": time.time(), "last": time.time(), "ip": ip}
    return _sign(sid)


def valid_session(token: str | None) -> bool:
    sid = _unsign(token or "")
    if not sid:
        return False
    now = int(time.time())
    try:
        c = _db()
        r = c.execute("SELECT created_at FROM app_session WHERE sid=?",
                      (sid,)).fetchone()
        if not r:
            return False
        if now - (r["created_at"] or 0) > SESSION_TTL:
            c.execute("DELETE FROM app_session WHERE sid=?", (sid,))
            c.commit()
            return False
        c.execute("UPDATE app_session SET last_seen=? WHERE sid=?", (now, sid))
        c.commit()
        return True
    except Exception:
        s = _sessions.get(sid)
        if not s:
            return False
        if time.time() - s["created"] > SESSION_TTL:
            _sessions.pop(sid, None)
            return False
        s["last"] = time.time()
        return True


def drop_session(token: str | None):
    sid = _unsign(token or "")
    if not sid:
        return
    try:
        c = _db()
        c.execute("DELETE FROM app_session WHERE sid=?", (sid,))
        c.commit()
    except Exception:
        pass
    _sessions.pop(sid, None)


def prune_sessions():
    """清理过期会话（启动时调用）"""
    try:
        c = _db()
        c.execute("DELETE FROM app_session WHERE created_at < ?",
                  (int(time.time()) - SESSION_TTL,))
        c.commit()
    except Exception:
        pass


# ---- FastAPI 依赖 ----
def require_auth(request: Request):
    """除公共路径外一律要求有效 Session"""
    path = request.url.path
    if path in PUBLIC_PATHS or any(path.startswith(p) for p in PUBLIC_PREFIXES):
        return
    if request.method == "OPTIONS":
        return
    if not valid_session(request.cookies.get(COOKIE)):
        raise HTTPException(status_code=401, detail="未登录")


def is_public(request: Request) -> bool:
    """静态壳与非 API 路径一律放行；只有 /api/* 需要认证（认证路由自身再校验）"""
    # 认证已关闭：所有请求都放行
    if AUTH_DISABLED:
        return True
    p = request.url.path
    if p in PUBLIC_PATHS or p in PUBLIC_EXACT:
        return True
    if any(p.startswith(x) for x in PUBLIC_PREFIXES):
        return True
    # 非 /api 前缀 = 前端资源（含 SPA 回退路由）
    if not p.startswith("/api/"):
        return True
    return False


def auth_enabled() -> bool:
    return not AUTH_DISABLED
