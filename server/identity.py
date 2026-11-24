# -*- coding: utf-8 -*-
"""
M8 · 名字即账户（无密码）

契约
----
· 只有一个入口：POST /api/auth/enter {"name": "..."}
  - 归一化 name_key 命中 → 返回该用户（更新 last_seen_at）
  - 未命中 → 自动创建（这就是"注册"）
· 服务端下发签名 token，写入两处：
  - HttpOnly Cookie（网页用）
  - 响应体里的 token（APK 用，前端存 localStorage → Authorization: Bearer）
· 之后所有请求都凭 token 解析出 user_id，**永不读取请求体/查询串里的 user_id**。

名字归一化（这是正确性的关键）
------------------------------
"张三" / "张三 " / " 张三" / "　张三" / "ＡＢＣ" 必须被视为同一账户，
否则同一个人换个输入法就"丢数据"。规则：
  1. NFKC 规范化（全角字母数字 → 半角，兼容字符归一）
  2. 去除首尾所有空白（含全角空格、零宽字符）
  3. 内部连续空白折叠为单个空格
  4. 英文部分转小写（大小写不敏感）
  5. 限制 1–24 字符，禁止换行/控制字符
"""
import hashlib
import hmac
import os
import secrets
import time
import unicodedata
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
SECRET_FILE = DATA_DIR / ".session_secret"

COOKIE = "radar_sid"
SESSION_TTL = 180 * 24 * 3600        # 无密码场景：半年，减少重新输入名字
NAME_MAX = 24

# 免认证路径
PUBLIC_PATHS = {
    "/api/health",
    "/api/auth/enter",
    "/api/auth/status",
    "/api/auth/users",     # 公开：给登录页做"已有人名"提示（只返回名字，不返回任何数据）
}
PUBLIC_PREFIXES = (
    "/assets/",
    "/manifest.webmanifest",
    "/sw.js",
    "/icon-",
    "/apple-touch-icon",
)
PUBLIC_EXACT = {"/", "/index.html", "/favicon.ico"}


# ---------------- 密钥（签名 token 用，与业务无关） ----------------

def _load_secret() -> bytes:
    DATA_DIR.mkdir(exist_ok=True)
    if SECRET_FILE.exists():
        b = SECRET_FILE.read_bytes()
        if len(b) >= 32:
            return b
    s = secrets.token_bytes(48)
    SECRET_FILE.write_bytes(s)
    try:
        os.chmod(SECRET_FILE, 0o600)
    except Exception:
        pass
    return s


_SECRET = _load_secret()


# ---------------- 名字归一化 ----------------

# 需要额外剔除的不可见字符
_ZERO_WIDTH = dict.fromkeys(map(ord, "\u200b\u200c\u200d\ufeff\u00a0"), None)


def normalize_name(raw: str) -> str:
    """
    原始输入 → name_key（唯一键）。
    无法接受时抛 ValueError（调用方转成 400）。
    """
    if raw is None:
        raise ValueError("名字不能为空")
    s = unicodedata.normalize("NFKC", str(raw))
    s = s.translate(_ZERO_WIDTH)
    # 控制字符（含换行、制表）直接拒绝，避免伪造显示
    if any(unicodedata.category(ch) == "Cc" for ch in s):
        raise ValueError("名字不能包含控制字符")
    s = " ".join(s.split())          # 折叠所有空白 + 去首尾
    if not s:
        raise ValueError("名字不能为空")
    if len(s) > NAME_MAX:
        raise ValueError(f"名字最多 {NAME_MAX} 个字符")
    # 英文小写（中文不受影响）
    return s.lower()


def display_name(raw: str) -> str:
    """保留用户输入的可读形式（仅做 NFKC + 空白整理），用于显示"""
    s = unicodedata.normalize("NFKC", str(raw or "")).translate(_ZERO_WIDTH)
    return " ".join(s.split())


# ---------------- 用户 ----------------

def _db():
    from invest_radar import store
    store.init()
    return store.conn()


def find_user_by_key(name_key: str):
    r = _db().execute("SELECT * FROM app_user WHERE name_key=?", (name_key,)).fetchone()
    return dict(r) if r else None


def get_user(uid: int):
    r = _db().execute("SELECT * FROM app_user WHERE id=?", (uid,)).fetchone()
    return dict(r) if r else None


def list_users(limit: int = 50):
    """登录页提示用：只返回 id/name/last_seen_at，不泄露任何业务数据"""
    rows = _db().execute(
        "SELECT id, name, last_seen_at FROM app_user ORDER BY last_seen_at DESC LIMIT ?",
        (limit,)).fetchall()
    return [dict(r) for r in rows]


def enter(raw_name: str):
    """
    find-or-create，返回 (user_dict, created: bool)。
    并发安全：靠 name_key 的 UNIQUE 约束，冲突则回查。
    """
    key = normalize_name(raw_name)
    disp = display_name(raw_name) or key
    c = _db()
    row = c.execute("SELECT * FROM app_user WHERE name_key=?", (key,)).fetchone()
    created = False
    if row is None:
        now = int(time.time())
        try:
            c.execute("INSERT INTO app_user(name,name_key,created_at,last_seen_at) "
                      "VALUES(?,?,?,?)", (disp, key, now, now))
            c.commit()
            created = True
        except Exception:
            # 并发下被别人抢先插入
            c.rollback()
        row = c.execute("SELECT * FROM app_user WHERE name_key=?", (key,)).fetchone()
        if row is None:
            raise RuntimeError("创建账户失败")
    uid = row["id"]
    c.execute("UPDATE app_user SET last_seen_at=? WHERE id=?", (int(time.time()), uid))
    c.commit()
    return dict(row), created


def touch_user(uid: int):
    try:
        c = _db()
        c.execute("UPDATE app_user SET last_seen_at=? WHERE id=?",
                  (int(time.time()), uid))
        c.commit()
    except Exception:
        pass


# ---------------- token（签名 sid） ----------------

def _sign(sid: str) -> str:
    mac = hmac.new(_SECRET, sid.encode(), hashlib.sha256).hexdigest()[:32]
    return f"{sid}.{mac}"


def _unsign(token: str | None) -> str | None:
    if not token or "." not in token:
        return None
    sid, mac = token.rsplit(".", 1)
    expect = hmac.new(_SECRET, sid.encode(), hashlib.sha256).hexdigest()[:32]
    return sid if hmac.compare_digest(mac, expect) else None


def create_session(uid: int, ip: str = "", ua: str = "") -> str:
    sid = secrets.token_urlsafe(32)
    now = int(time.time())
    c = _db()
    c.execute("""INSERT OR REPLACE INTO app_session
                 (sid,created_at,last_seen,ip,ua,user_id) VALUES(?,?,?,?,?,?)""",
              (sid, now, now, ip, ua[:200], uid))
    c.commit()
    return _sign(sid)


def resolve_session(token: str | None):
    """token → uid（无效返回 None）"""
    sid = _unsign(token or "")
    if not sid:
        return None
    now = int(time.time())
    try:
        c = _db()
        r = c.execute("SELECT created_at, user_id FROM app_session WHERE sid=?",
                      (sid,)).fetchone()
        if not r:
            return None
        uid = r["user_id"] or 0
        if uid <= 0:
            return None
        if now - (r["created_at"] or 0) > SESSION_TTL:
            c.execute("DELETE FROM app_session WHERE sid=?", (sid,))
            c.commit()
            return None
        c.execute("UPDATE app_session SET last_seen=? WHERE sid=?", (now, sid))
        c.commit()
        return uid
    except Exception:
        return None


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


def prune_sessions():
    try:
        c = _db()
        c.execute("DELETE FROM app_session WHERE created_at < ?",
                  (int(time.time()) - SESSION_TTL,))
        c.commit()
    except Exception:
        pass


# ---------------- 从请求取 uid（唯一可信来源） ----------------

def token_from_request(request) -> str | None:
    """
    双通道：
      1. Cookie（网页）
      2. Authorization: Bearer <token>（APK / 跨域）
    """
    t = request.cookies.get(COOKIE)
    if t:
        return t
    auth = request.headers.get("authorization") or ""
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    # 兜底：Capacitor 某些场景自定义头
    t2 = request.headers.get("x-radar-token")
    return t2.strip() if t2 else None


def uid_from_request(request) -> int:
    """无效则抛 401。所有业务路由都用这个，绝不接受客户端传的 uid。"""
    from fastapi import HTTPException
    uid = resolve_session(token_from_request(request))
    if not uid:
        raise HTTPException(status_code=401, detail="未登录")
    return uid


def is_public(request) -> bool:
    p = request.url.path
    if p in PUBLIC_PATHS or p in PUBLIC_EXACT:
        return True
    if any(p.startswith(x) for x in PUBLIC_PREFIXES):
        return True
    if not p.startswith("/api/"):
        return True
    return False
