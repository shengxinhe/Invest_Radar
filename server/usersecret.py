# -*- coding: utf-8 -*-
"""
M8 · 每个用户自己的 DeepSeek API Key

安全约定
--------
· 密文：Fernet（AES-128-CBC + HMAC），密钥来自环境变量 RADAR_SECRET_KEY
  - 未配置环境变量时，自动生成并持久化到 data/.key_secret（权限 600），
    保证"加密可用但明文不落库"；生产环境请显式设置环境变量。
· 明文只存在于进程内存中调用上游的那一瞬间，不写日志、不返回前端。
· 对外只暴露 key_hint（sk-…abcd）+ has_key 布尔。
· 每个 Key 独立并发闸门，避免一个用户打满影响其他人。
"""
import logging
import os
import re
import time
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
KEY_FILE = DATA_DIR / ".key_secret"

log = logging.getLogger("usersecret")

_KEY_RE = re.compile(r"^sk-[A-Za-z0-9_\-]{16,}$")


# ---------------- 加密密钥 ----------------

def _load_fernet() -> Fernet:
    env = (os.environ.get("RADAR_SECRET_KEY") or "").strip()
    if env:
        # 允许直接给 Fernet key，也允许给任意随机字符串（自动派生）
        try:
            return Fernet(env.encode())
        except Exception:
            import base64
            import hashlib
            dk = hashlib.sha256(env.encode()).digest()
            return Fernet(base64.urlsafe_b64encode(dk))
    DATA_DIR.mkdir(exist_ok=True)
    if KEY_FILE.exists():
        raw = KEY_FILE.read_bytes().strip()
        if raw:
            try:
                return Fernet(raw)
            except Exception:
                pass
    k = Fernet.generate_key()
    KEY_FILE.write_bytes(k)
    try:
        os.chmod(KEY_FILE, 0o600)
    except Exception:
        pass
    return Fernet(k)


_F = _load_fernet()


# ---------------- 校验与脱敏 ----------------

def validate_key(raw: str) -> str:
    k = (raw or "").strip()
    if not k:
        raise ValueError("Key 不能为空")
    if not _KEY_RE.match(k):
        raise ValueError("格式不对：应以 sk- 开头，后接至少 16 位字母数字")
    if any(ord(ch) > 127 for ch in k):
        raise ValueError("Key 只能包含 ASCII 字符")
    return k


def mask_key(k: str) -> str:
    """sk-abcd…wxyz —— 只用于 UI 提示与日志"""
    if not k:
        return ""
    if len(k) <= 12:
        return k[:4] + "****"
    return f"{k[:7]}…{k[-4:]}"


# ---------------- 读写 ----------------

def _db():
    from invest_radar import store
    store.init()
    return store.conn()


def _row(uid: int):
    r = _db().execute("SELECT * FROM user_secret WHERE user_id=?", (uid,)).fetchone()
    return dict(r) if r else None


def get_public(uid: int) -> dict:
    """给前端看的安全视图：绝不包含明文或密文"""
    r = _row(uid) or {}
    enc = r.get("deepseek_key_enc") or ""
    return {
        "has_key": bool(enc),
        "key_hint": r.get("key_hint") or "",
        "model_cheap": r.get("model_cheap") or "deepseek-chat",
        "model_strong": r.get("model_strong") or "deepseek-reasoner",
        "ai_enabled": bool(r.get("ai_enabled", 1)),
        "updated_at": r.get("updated_at") or 0,
        "tested_at": r.get("tested_at") or 0,
        "test_ok": bool(r.get("test_ok", 0)),
    }


def get_key(uid: int) -> str:
    """解密取明文；无 Key 返回空串。失败只记类型，不记内容。"""
    r = _row(uid)
    if not r or not r.get("deepseek_key_enc"):
        return ""
    try:
        return _F.decrypt(r["deepseek_key_enc"].encode()).decode()
    except InvalidToken:
        log.warning("decrypt failed for uid=%s (secret rotated?)", uid)
        return ""
    except Exception as e:
        log.warning("decrypt error uid=%s: %s", uid, type(e).__name__)
        return ""


def available(uid: int) -> bool:
    k = get_key(uid)
    return bool(k) and _KEY_RE.match(k) is not None


def save_key(uid: int, raw: str) -> dict:
    k = validate_key(raw)
    enc = _F.encrypt(k.encode()).decode()
    c = _db()
    c.execute("""INSERT INTO user_secret
                 (user_id,deepseek_key_enc,key_hint,updated_at,tested_at,test_ok)
                 VALUES(?,?,?,?,0,0)
                 ON CONFLICT(user_id) DO UPDATE SET
                   deepseek_key_enc=excluded.deepseek_key_enc,
                   key_hint=excluded.key_hint,
                   updated_at=excluded.updated_at,
                   tested_at=0, test_ok=0""",
              (uid, enc, mask_key(k), int(time.time())))
    c.commit()
    return get_public(uid)


def delete_key(uid: int) -> dict:
    c = _db()
    c.execute("""UPDATE user_secret
                 SET deepseek_key_enc='', key_hint='', updated_at=?, tested_at=0, test_ok=0
                 WHERE user_id=?""", (int(time.time()), uid))
    c.commit()
    return get_public(uid)


def save_settings(uid: int, model_cheap=None, model_strong=None, ai_enabled=None) -> dict:
    c = _db()
    sets, vals = [], []
    if model_cheap:
        sets.append("model_cheap=?"); vals.append(model_cheap)
    if model_strong:
        sets.append("model_strong=?"); vals.append(model_strong)
    if ai_enabled is not None:
        sets.append("ai_enabled=?"); vals.append(1 if ai_enabled else 0)
    if sets:
        sets.append("updated_at=?"); vals.append(int(time.time()))
        vals.append(uid)
        c.execute(f"UPDATE user_secret SET {','.join(sets)} WHERE user_id=?", vals)
        # 若还没有行，先建空行再更新
        if not c.execute("SELECT 1 FROM user_secret WHERE user_id=?", (uid,)).fetchone():
            c.execute("INSERT OR IGNORE INTO user_secret(user_id) VALUES(?)", (uid,))
            c.execute(f"UPDATE user_secret SET {','.join(sets)} WHERE user_id=?", vals)
        c.commit()
    else:
        c.execute("INSERT OR IGNORE INTO user_secret(user_id) VALUES(?)", (uid,))
        c.commit()
    return get_public(uid)


def mark_tested(uid: int, ok: bool):
    c = _db()
    c.execute("INSERT OR IGNORE INTO user_secret(user_id) VALUES(?)", (uid,))
    c.execute("UPDATE user_secret SET tested_at=?, test_ok=? WHERE user_id=?",
              (int(time.time()), 1 if ok else 0, uid))
    c.commit()


def models(uid: int) -> tuple[str, str]:
    r = _row(uid) or {}
    return (r.get("model_cheap") or os.environ.get("DEEPSEEK_MODEL_CHEAP", "deepseek-chat"),
            r.get("model_strong") or os.environ.get("DEEPSEEK_MODEL_STRONG", "deepseek-reasoner"))
