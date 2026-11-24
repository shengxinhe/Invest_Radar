# -*- coding: utf-8 -*-
"""
M8 · 多用户改造：名字即账户（无密码）

设计要点
--------
1. 新增 app_user：name（显示用原样）+ name_key（归一化唯一键）
   —— 归一化包含 NFKC（全角→半角）、去首尾空白、折叠连续空白、ASCII 小写，
      避免「张三」「张三 」「 张三 」被当成三个账户导致数据割裂。
2. app_session 增加 user_id：会话凭据与用户绑定，后端不再信任客户端传的 user_id。
3. 私有表加 user_id：
   - watch / entry_user_state / entry_ai 三张表主键含 code|entry_id，
     必须重建（SQLite 不支持改主键）→ 走 CREATE new → INSERT SELECT → DROP → RENAME。
   - 其余表（thesis_history / ai_analysis_version / chat / research_record /
     research_report / notification_log）主键是自增 id 或有独立 id，直接 ADD COLUMN。
4. 存量数据全部归到 user_id=1（"房主"），不丢任何一行。
5. 幂等：检测列/表是否已存在则跳过，便于重复执行与全新库共存。

红线：只 CREATE / ALTER / RENAME；重建表时数据先搬再换名，全程单事务。
"""
DESCRIPTION = "multiuser: app_user + session.user_id + private tables scoped by user_id"

OWNER_UID = 1
OWNER_NAME = "房主"


# ---------------- 工具 ----------------

def _cols(c, table):
    try:
        return {r[1] for r in c.execute(f"PRAGMA table_info({table})").fetchall()}
    except Exception:
        return set()


def _has_table(c, table):
    return bool(c.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone())


def _pk_cols(c, table):
    return [r[1] for r in c.execute(f"PRAGMA table_info({table})").fetchall() if r[5]]


# ---------------- 建用户表 ----------------

SQL_USER = """
CREATE TABLE IF NOT EXISTS app_user (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  name          TEXT NOT NULL,              -- 显示名（原样，允许中文/空格）
  name_key      TEXT NOT NULL UNIQUE,       -- 归一化唯一键
  created_at    INTEGER,
  last_seen_at  INTEGER
);
CREATE INDEX IF NOT EXISTS idx_user_key ON app_user(name_key);
"""


def upgrade(c):
    c.executescript(SQL_USER)

    # ---- 存量数据归属：确保 user_id=1 存在 ----
    import time
    now = int(time.time())
    row = c.execute("SELECT id FROM app_user WHERE id=?", (OWNER_UID,)).fetchone()
    if not row:
        c.execute(
            "INSERT INTO app_user(id,name,name_key,created_at,last_seen_at) VALUES(?,?,?,?,?)",
            (OWNER_UID, OWNER_NAME, OWNER_NAME.lower(), now, now))

    # ---- 1) app_session 加 user_id ----
    if "user_id" not in _cols(c, "app_session"):
        c.execute("ALTER TABLE app_session ADD COLUMN user_id INTEGER DEFAULT 0")
        c.execute("UPDATE app_session SET user_id=? WHERE user_id IS NULL OR user_id=0",
                  (OWNER_UID,))
        c.execute("CREATE INDEX IF NOT EXISTS idx_sess_user "
                  "ON app_session(user_id, last_seen DESC)")

    # ---- 2) watch 重建：code PK → (user_id, code) PK，并补 grp 分组字段 ----
    if "user_id" not in _cols(c, "watch"):
        has_grp = "grp" in _cols(c, "watch")
        grp_expr = "COALESCE(grp,'')" if has_grp else "''"
        c.executescript("""
CREATE TABLE watch_v2 (
  user_id    INTEGER NOT NULL,
  code       TEXT NOT NULL,
  role       TEXT,
  tags       TEXT,
  thesis     TEXT,
  keywords   TEXT,
  sort       INTEGER DEFAULT 0,
  grp        TEXT DEFAULT '',
  created_at INTEGER,
  PRIMARY KEY (user_id, code)
);
""")
        c.execute(f"""
INSERT INTO watch_v2 (user_id, code, role, tags, thesis, keywords, sort, grp, created_at)
SELECT ?, code, role, tags, thesis, keywords, COALESCE(sort,0), {grp_expr}, created_at
FROM watch
""", (OWNER_UID,))
        c.execute("DROP TABLE watch")
        c.execute("ALTER TABLE watch_v2 RENAME TO watch")
    # 新版也可能缺 grp（全新库由 SCHEMA 建表时已含）
    if "grp" not in _cols(c, "watch"):
        c.execute("ALTER TABLE watch ADD COLUMN grp TEXT DEFAULT ''")
    c.execute("CREATE INDEX IF NOT EXISTS idx_watch_user_sort ON watch(user_id, sort, code)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_watch_user_grp ON watch(user_id, grp, sort)")

    # ---- 3) entry_user_state 重建：entry_id PK → (user_id, entry_id) PK ----
    if "user_id" not in _cols(c, "entry_user_state"):
        c.executescript("""
CREATE TABLE eus_v2 (
  user_id    INTEGER NOT NULL,
  entry_id   TEXT NOT NULL,
  status     TEXT DEFAULT 'unread',
  is_read    INTEGER DEFAULT 0,
  note       TEXT DEFAULT '',
  updated_at INTEGER,
  PRIMARY KEY (user_id, entry_id)
);
""")
        c.execute("""
INSERT INTO eus_v2 (user_id, entry_id, status, is_read, note, updated_at)
SELECT ?, entry_id, COALESCE(status,'unread'), COALESCE(is_read,0),
       COALESCE(note,''), updated_at
FROM entry_user_state
""", (OWNER_UID,))
        c.execute("DROP TABLE entry_user_state")
        c.execute("ALTER TABLE eus_v2 RENAME TO entry_user_state")
    c.execute("CREATE INDEX IF NOT EXISTS idx_eus_user_status "
              "ON entry_user_state(user_id, status, updated_at DESC)")

    # ---- 4) entry_ai 重建：entry_id PK → (user_id, entry_id) PK ----
    if "user_id" not in _cols(c, "entry_ai"):
        c.executescript("""
CREATE TABLE entry_ai_v2 (
  user_id       INTEGER NOT NULL,
  entry_id      TEXT NOT NULL,
  model         TEXT,
  summary       TEXT,
  why_matters   TEXT,
  thesis_impact TEXT,
  read_hint     TEXT,
  tokens        INTEGER,
  created_at    INTEGER,
  thesis_hash   TEXT DEFAULT '',
  prompt_version TEXT DEFAULT 'v0',
  cache_key     TEXT DEFAULT '',
  PRIMARY KEY (user_id, entry_id)
);
""")
        c.execute("""
INSERT INTO entry_ai_v2
  (user_id, entry_id, model, summary, why_matters, thesis_impact, read_hint,
   tokens, created_at, thesis_hash, prompt_version, cache_key)
SELECT ?, entry_id, model, summary, why_matters, thesis_impact, read_hint,
       tokens, created_at, COALESCE(thesis_hash,''),
       COALESCE(prompt_version,'v0'), COALESCE(cache_key,'')
FROM entry_ai
""", (OWNER_UID,))
        c.execute("DROP TABLE entry_ai")
        c.execute("ALTER TABLE entry_ai_v2 RENAME TO entry_ai")

    # ---- 5) 其余私有表：只加列 ----
    for table in ("thesis_history", "ai_analysis_version", "chat",
                  "research_record", "research_report", "notification_log"):
        if not _has_table(c, table):
            continue
        if "user_id" not in _cols(c, table):
            c.execute(f"ALTER TABLE {table} ADD COLUMN user_id INTEGER DEFAULT {OWNER_UID}")
            c.execute(f"UPDATE {table} SET user_id=? WHERE user_id IS NULL", (OWNER_UID,))

    # ---- 6) 私有数据索引 ----
    c.executescript("""
CREATE INDEX IF NOT EXISTS idx_th_user  ON thesis_history(user_id, code, changed_at DESC);
CREATE INDEX IF NOT EXISTS idx_aav_user ON ai_analysis_version(user_id, entry_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_chat_user ON chat(user_id, scope, created_at);
CREATE INDEX IF NOT EXISTS idx_rr_user  ON research_record(user_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_rep_user ON research_report(user_id, kind, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_nl_user  ON notification_log(user_id, status, created_at DESC);
""")
