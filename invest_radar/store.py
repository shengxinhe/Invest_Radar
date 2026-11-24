# -*- coding: utf-8 -*-
"""
SQLite 存储层 —— M0
职责：
  - 建表 / 迁移
  - 词条 upsert（去重靠 id = sha1(code+type+source_id)）
  - 行情快照
  - TTL 判断（need_refresh）
  - watch 表（替代 config.WATCHLIST）

设计原则：全部同步 API，单连接 + WAL，不做并发花活。
"""
import hashlib
import json
import sqlite3
import threading
import time
from pathlib import Path

from . import config

DB_PATH = config.DATA_DIR / "radar.db"

_local = threading.local()


# ---------------- 连接 ----------------

def conn():
    """每线程一个连接（uvicorn 多线程安全）"""
    c = getattr(_local, "conn", None)
    if c is None:
        c = sqlite3.connect(str(DB_PATH), check_same_thread=False, timeout=30)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA synchronous=NORMAL")
        c.execute("PRAGMA foreign_keys=ON")
        _local.conn = c
    return c


def _uid(uid):
    """M8: 未显式传 uid 时，取当前请求身份（见 invest_radar/ctx.py）"""
    if uid is None:
        from . import ctx
        return ctx.current_uid()
    return int(uid)



SCHEMA = """
CREATE TABLE IF NOT EXISTS stock (
  code TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  pinyin TEXT,
  market TEXT,
  industry TEXT,
  concepts TEXT,
  updated_at INTEGER
);

CREATE VIRTUAL TABLE IF NOT EXISTS stock_fts USING fts5(
  code, name, pinyin, concepts, content='stock', content_rowid='rowid'
);

-- M8 多用户：名字即账户（无密码）
CREATE TABLE IF NOT EXISTS app_user (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  name          TEXT NOT NULL,
  name_key      TEXT NOT NULL UNIQUE,
  created_at    INTEGER,
  last_seen_at  INTEGER
);
CREATE INDEX IF NOT EXISTS idx_user_key ON app_user(name_key);

-- M8 私有表：自选股按 (user_id, code) 隔离，grp 为分组
CREATE TABLE IF NOT EXISTS watch (  user_id INTEGER NOT NULL DEFAULT 1,
  code TEXT NOT NULL,
  role TEXT,
  tags TEXT,
  thesis TEXT,
  keywords TEXT,
  sort INTEGER DEFAULT 0,
  grp TEXT DEFAULT '',
  created_at INTEGER,
  PRIMARY KEY (user_id, code)
);
CREATE INDEX IF NOT EXISTS idx_watch_user_sort ON watch(user_id, sort, code);
CREATE INDEX IF NOT EXISTS idx_watch_user_grp ON watch(user_id, grp, sort);

-- M8 每人独立 DeepSeek Key（Fernet 密文，密钥走环境变量）
CREATE TABLE IF NOT EXISTS user_secret (
  user_id          INTEGER PRIMARY KEY,
  deepseek_key_enc TEXT DEFAULT '',
  key_hint         TEXT DEFAULT '',
  model_cheap      TEXT DEFAULT 'deepseek-chat',
  model_strong     TEXT DEFAULT 'deepseek-reasoner',
  ai_enabled       INTEGER DEFAULT 1,
  updated_at       INTEGER,
  tested_at        INTEGER DEFAULT 0,
  test_ok          INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS entry (
  id TEXT PRIMARY KEY,
  code TEXT NOT NULL,
  type TEXT NOT NULL,
  source_id TEXT,
  title TEXT,
  url TEXT,
  published_at INTEGER,
  content TEXT,
  level TEXT,
  created_at INTEGER
);
CREATE INDEX IF NOT EXISTS idx_entry_code_type
  ON entry(code, type, published_at DESC);
CREATE INDEX IF NOT EXISTS idx_entry_level
  ON entry(level, published_at DESC);

CREATE VIRTUAL TABLE IF NOT EXISTS entry_fts USING fts5(
  title, content, content='entry', content_rowid='rowid'
);

-- M8: 一条词条可存 N 个用户各自的解读
CREATE TABLE IF NOT EXISTS entry_ai (
  user_id INTEGER NOT NULL DEFAULT 1,
  entry_id TEXT NOT NULL,
  model TEXT,
  summary TEXT,
  why_matters TEXT,
  thesis_impact TEXT,
  read_hint TEXT,
  tokens INTEGER,
  created_at INTEGER,
  thesis_hash TEXT DEFAULT '',
  prompt_version TEXT DEFAULT 'v0',
  cache_key TEXT DEFAULT '',
  PRIMARY KEY (user_id, entry_id)
);

CREATE TABLE IF NOT EXISTS chat (
  id TEXT PRIMARY KEY,
  scope TEXT,
  role TEXT,
  content TEXT,
  created_at INTEGER,
  user_id INTEGER DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_chat_scope ON chat(scope, created_at);
CREATE INDEX IF NOT EXISTS idx_chat_user ON chat(user_id, scope, created_at);

CREATE TABLE IF NOT EXISTS quote (
  code TEXT, ts INTEGER, price REAL, pct REAL,
  volume_ratio REAL, pe REAL, pb REAL, mcap REAL,
  open REAL, high REAL, low REAL, prev_close REAL,
  amount_wan REAL, turnover_pct REAL, amplitude_pct REAL,
  PRIMARY KEY (code, ts)
);

CREATE TABLE IF NOT EXISTS fetch_log (
  key TEXT PRIMARY KEY,
  fetched_at INTEGER,
  source TEXT DEFAULT '',
  status TEXT DEFAULT 'ok',
  error TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS kline (
  code   TEXT NOT NULL,
  period TEXT NOT NULL,
  ts     INTEGER NOT NULL,
  o REAL, h REAL, l REAL, c REAL,
  volume REAL, amount REAL,
  PRIMARY KEY (code, period, ts)
);
CREATE INDEX IF NOT EXISTS idx_kline ON kline(code, period, ts DESC);

CREATE TABLE IF NOT EXISTS meta (
  k TEXT PRIMARY KEY,
  v TEXT
);

-- ============ M8: 以下表原本只由 migrations 创建，补齐以保证全新库可用 ============

CREATE TABLE IF NOT EXISTS app_session (
  sid        TEXT PRIMARY KEY,
  created_at INTEGER NOT NULL,
  last_seen  INTEGER,
  ip         TEXT DEFAULT '',
  ua         TEXT DEFAULT '',
  user_id    INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_sess_last ON app_session(last_seen DESC);
CREATE INDEX IF NOT EXISTS idx_sess_user ON app_session(user_id, last_seen DESC);

CREATE TABLE IF NOT EXISTS entry_user_state (
  user_id    INTEGER NOT NULL DEFAULT 1,
  entry_id   TEXT NOT NULL,
  status     TEXT DEFAULT 'unread',
  is_read    INTEGER DEFAULT 0,
  note       TEXT DEFAULT '',
  updated_at INTEGER,
  PRIMARY KEY (user_id, entry_id)
);
CREATE INDEX IF NOT EXISTS idx_eus_user_status
  ON entry_user_state(user_id, status, updated_at DESC);

CREATE TABLE IF NOT EXISTS thesis_history (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id    INTEGER DEFAULT 1,
  code       TEXT NOT NULL,
  thesis_old TEXT,
  thesis_new TEXT,
  reason     TEXT DEFAULT '',
  changed_at INTEGER
);
CREATE INDEX IF NOT EXISTS idx_th_user ON thesis_history(user_id, code, changed_at DESC);

CREATE TABLE IF NOT EXISTS ai_analysis_version (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id         INTEGER DEFAULT 1,
  entry_id        TEXT NOT NULL,
  cache_key       TEXT NOT NULL,
  model           TEXT,
  summary         TEXT, why_matters TEXT, thesis_impact TEXT, read_hint TEXT,
  tokens          INTEGER DEFAULT 0,
  thesis_hash     TEXT,
  prompt_version  TEXT,
  created_at      INTEGER
);
CREATE INDEX IF NOT EXISTS idx_aav_user
  ON ai_analysis_version(user_id, entry_id, created_at DESC);

CREATE TABLE IF NOT EXISTS notification_log (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id    INTEGER DEFAULT 1,
  level      TEXT,
  code       TEXT,
  title      TEXT,
  entry_id   TEXT,
  channel    TEXT DEFAULT 'wechat',
  status     TEXT DEFAULT 'queued',
  created_at INTEGER,
  sent_at    INTEGER
);
CREATE INDEX IF NOT EXISTS idx_nl_user ON notification_log(user_id, status, created_at DESC);

CREATE TABLE IF NOT EXISTS research_record (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id    INTEGER DEFAULT 1,
  code       TEXT NOT NULL,
  title      TEXT NOT NULL,
  content    TEXT DEFAULT '',
  tags       TEXT DEFAULT '',
  entry_ids  TEXT DEFAULT '',
  created_at INTEGER,
  updated_at INTEGER
);
CREATE INDEX IF NOT EXISTS idx_rr_user ON research_record(user_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS research_report (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id    INTEGER DEFAULT 1,
  kind       TEXT NOT NULL,
  code       TEXT DEFAULT '',
  title      TEXT NOT NULL,
  content    TEXT DEFAULT '',
  meta       TEXT DEFAULT '',
  period     TEXT DEFAULT '',
  created_at INTEGER
);
CREATE INDEX IF NOT EXISTS idx_rep_user ON research_report(user_id, kind, created_at DESC);

CREATE TABLE IF NOT EXISTS quote_daily (
  code TEXT, date TEXT, price REAL, pct REAL,
  open REAL, high REAL, low REAL, prev_close REAL,
  amount_wan REAL, turnover_pct REAL, pe REAL, pb REAL, mcap REAL,
  PRIMARY KEY (code, date)
);
CREATE INDEX IF NOT EXISTS idx_qd_code ON quote_daily(code, date DESC);

CREATE TABLE IF NOT EXISTS schema_migrations (
  version    TEXT PRIMARY KEY,
  name       TEXT,
  applied_at INTEGER
);
"""


def init():
    """建表 + 首次导入 WATCHLIST"""
    c = conn()
    c.executescript(SCHEMA)
    c.commit()

    # M8: 保证房主账户（user_id=1）存在，存量数据都归它
    if not c.execute("SELECT 1 FROM app_user WHERE id=1").fetchone():
        c.execute("INSERT INTO app_user(id,name,name_key,created_at,last_seen_at) "
                  "VALUES(1,?,?,?,?)", ("房主", "房主", now(), now()))
        c.commit()

    # 首次启动：把 config.WATCHLIST 导入 watch 表 + stock 表（保证有名字显示）
    if not c.execute("SELECT 1 FROM meta WHERE k='watch_seeded'").fetchone():
        for i, s in enumerate(config.WATCHLIST):
            upsert_watch(
                code=s["code"],
                role=s.get("role", ""),
                thesis=s.get("thesis", ""),
                keywords=s.get("keywords", []),
                tags=s.get("alias", []),
                sort=i,
                uid=1,
            )
            # 同步 stock 主数据，避免 UI 显示成代码
            if not c.execute("SELECT 1 FROM stock WHERE code=?", (s["code"],)).fetchone():
                from .pyutil import to_pinyin
                nm = s.get("name", s["code"])
                c.execute(
                    "INSERT INTO stock(code,name,pinyin,market,industry,concepts,updated_at)"
                    " VALUES(?,?,?,?,?,?,?)",
                    (s["code"], nm, to_pinyin(nm),
                     "sh" if s["code"].startswith(("6", "9")) else "sz",
                     "", "[]", now()))
        c.commit()
        c.execute("INSERT INTO stock_fts(stock_fts) VALUES('rebuild')")
        c.execute("INSERT OR REPLACE INTO meta(k,v) VALUES('watch_seeded',?)",
                  (str(int(time.time())),))
        c.commit()


# ---------------- 工具 ----------------

def make_entry_id(code, type_, source_id):
    raw = f"{code}|{type_}|{source_id}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def now():
    return int(time.time())


# ---------------- watch（M8: 按 user_id 隔离） ----------------

def upsert_watch(code, role=None, thesis=None, keywords=None, tags=None, sort=None,
                 uid=None, grp=None):
    uid = _uid(uid)
    c = conn()
    row = c.execute("SELECT * FROM watch WHERE user_id=? AND code=?",
                    (uid, code)).fetchone()
    if row is None:
        c.execute(
            "INSERT INTO watch(user_id,code,role,tags,thesis,keywords,sort,grp,created_at) "
            "VALUES(?,?,?,?,?,?,?,?,?)",
            (uid, code, role or "", json.dumps(tags or [], ensure_ascii=False),
             thesis or "", json.dumps(keywords or [], ensure_ascii=False),
             sort or 0, grp or "", now()))
    else:
        sets, vals = [], []
        for k, v in (("role", role), ("thesis", thesis), ("sort", sort), ("grp", grp)):
            if v is not None:
                sets.append(f"{k}=?")
                vals.append(v)
        if keywords is not None:
            sets.append("keywords=?")
            vals.append(json.dumps(keywords, ensure_ascii=False))
        if tags is not None:
            sets.append("tags=?")
            vals.append(json.dumps(tags, ensure_ascii=False))
        if sets:
            vals.extend([uid, code])
            c.execute(f"UPDATE watch SET {','.join(sets)} "
                      f"WHERE user_id=? AND code=?", vals)
    c.commit()


def list_watch(uid=None):
    """返回该用户的关注池（带股票名称）"""
    uid = _uid(uid)
    c = conn()
    rows = c.execute("""
        SELECT w.*, COALESCE(s.name,'') AS name, COALESCE(s.industry,'') AS industry
        FROM watch w LEFT JOIN stock s ON s.code = w.code
        WHERE w.user_id = ?
        ORDER BY w.sort, w.code
    """, (uid,)).fetchall()
    out = []
    for r in rows:
        out.append({
            "code": r["code"],
            "name": r["name"] or r["code"],
            "role": r["role"] or "",
            "thesis": r["thesis"] or "",
            "keywords": json.loads(r["keywords"] or "[]"),
            "tags": json.loads(r["tags"] or "[]"),
            "industry": r["industry"] or "",
            "sort": r["sort"] or 0,
            "grp": r["grp"] or "",
        })
    return out


def get_watch(code, uid=None):
    uid = _uid(uid)
    c = conn()
    r = c.execute("""
        SELECT w.*, COALESCE(s.name,'') AS name
        FROM watch w LEFT JOIN stock s ON s.code=w.code
        WHERE w.user_id=? AND w.code=?
    """, (uid, code)).fetchone()
    if not r:
        return None
    return {
        "code": r["code"],
        "name": r["name"] or r["code"],
        "role": r["role"] or "",
        "thesis": r["thesis"] or "",
        "keywords": json.loads(r["keywords"] or "[]"),
        "tags": json.loads(r["tags"] or "[]"),
        "grp": r["grp"] or "",
    }


def del_watch(code, uid=None):
    uid = _uid(uid)
    c = conn()
    c.execute("DELETE FROM watch WHERE user_id=? AND code=?", (uid, code))
    c.commit()


def reorder_watch(codes, uid=None):
    """按给定顺序批量写 sort（拖拽排序用）"""
    uid = _uid(uid)
    c = conn()
    for i, code in enumerate(codes):
        c.execute("UPDATE watch SET sort=? WHERE user_id=? AND code=?", (i, uid, code))
    c.commit()


def all_watch_codes():
    """公共采集用：所有用户关注过的股票并集（去重），不涉及隐私"""
    c = conn()
    rows = c.execute("SELECT DISTINCT code FROM watch").fetchall()
    return [r["code"] for r in rows]


# ---------------- 股票主数据 ----------------

def upsert_stock(code, name, pinyin="", market="", industry="", concepts=None):
    c = conn()
    c.execute("""
        INSERT INTO stock(code,name,pinyin,market,industry,concepts,updated_at)
        VALUES(?,?,?,?,?,?,?)
        ON CONFLICT(code) DO UPDATE SET
          name=excluded.name, pinyin=excluded.pinyin, market=excluded.market,
          industry=excluded.industry, concepts=excluded.concepts,
          updated_at=excluded.updated_at
    """, (code, name, pinyin, market, industry,
          json.dumps(concepts or [], ensure_ascii=False), now()))
    c.commit()


def bulk_upsert_stocks(rows):
    """rows: [(code,name,pinyin,market,industry,concepts_json)]"""
    c = conn()
    t = now()
    c.executemany("""
        INSERT INTO stock(code,name,pinyin,market,industry,concepts,updated_at)
        VALUES(?,?,?,?,?,?,?)
        ON CONFLICT(code) DO UPDATE SET
          name=excluded.name, pinyin=excluded.pinyin, market=excluded.market,
          industry=excluded.industry, concepts=excluded.concepts,
          updated_at=excluded.updated_at
    """, [(*r, t) for r in rows])
    c.commit()
    # 重建 FTS 索引
    c.execute("INSERT INTO stock_fts(stock_fts) VALUES('rebuild')")
    c.commit()


def get_stock(code):
    c = conn()
    r = c.execute("SELECT * FROM stock WHERE code=?", (code,)).fetchone()
    if not r:
        return None
    return {"code": r["code"], "name": r["name"], "pinyin": r["pinyin"],
            "market": r["market"], "industry": r["industry"],
            "concepts": json.loads(r["concepts"] or "[]")}


def search_stock(q, limit=20):
    """代码前缀 / 名称模糊 / 拼音首字母。结果按相关度排序。"""
    c = conn()
    q = (q or "").strip()
    if not q:
        return []

    out = []
    seen = set()

    def add(rows):
        for r in rows:
            if r["code"] not in seen:
                seen.add(r["code"])
                out.append({"code": r["code"], "name": r["name"],
                            "market": r["market"], "industry": r["industry"]})

    # 1) 代码精确 / 前缀（最高优先）
    add(c.execute("SELECT * FROM stock WHERE code = ? LIMIT 3", (q,)).fetchall())
    add(c.execute("SELECT * FROM stock WHERE code LIKE ? ORDER BY code LIMIT ?",
                  (q + "%", limit)).fetchall())
    # 2) 名称前缀
    if len(out) < limit:
        add(c.execute("SELECT * FROM stock WHERE name LIKE ? LIMIT ?",
                      (q + "%", limit)).fetchall())
    # 3) 拼音前缀（全拼或首字母，pinyin 形如 "zhongjinlingnan zjln"）
    if len(out) < limit:
        ql = q.lower()
        add(c.execute(
            "SELECT * FROM stock WHERE pinyin LIKE ? OR pinyin LIKE ? LIMIT ?",
            (ql + "%", "% " + ql + "%", limit)).fetchall())
    # 4) 名称包含
    if len(out) < limit:
        add(c.execute("SELECT * FROM stock WHERE name LIKE ? ORDER BY code LIMIT ?",
                      ("%" + q + "%", limit)).fetchall())
    # 5) 拼音包含
    if len(out) < limit:
        ql = q.lower()
        add(c.execute("SELECT * FROM stock WHERE pinyin LIKE ? LIMIT ?",
                      ("%" + ql + "%", limit)).fetchall())

    return out[:limit]


def count_stocks():
    r = conn().execute("SELECT COUNT(*) AS n FROM stock").fetchone()
    return r["n"] if r else 0


# ---------------- 词条 ----------------

def upsert_entry(code, type_, source_id, title, url="", published_at=None,
                 content="", level="neutral"):
    """返回 (entry_id, is_new)"""
    eid = make_entry_id(code, type_, source_id)
    c = conn()
    exist = c.execute("SELECT 1 FROM entry WHERE id=?", (eid,)).fetchone()
    c.execute("""
        INSERT INTO entry(id,code,type,source_id,title,url,published_at,content,level,created_at)
        VALUES(?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(id) DO UPDATE SET
          title=excluded.title, url=excluded.url,
          published_at=excluded.published_at, content=excluded.content,
          level=excluded.level
    """, (eid, code, type_, source_id, title, url,
          published_at or now(), content, level, now()))
    c.commit()
    return eid, exist is None


def bulk_upsert_entries(items):
    """
    items: list of dict(code,type,source_id,title,url,published_at,content,level)
    返回 (新增数, 总处理数)
    """
    c = conn()
    new = 0
    t = now()
    rows = []
    for it in items:
        eid = make_entry_id(it["code"], it["type"], it["source_id"])
        exist = c.execute("SELECT 1 FROM entry WHERE id=?", (eid,)).fetchone()
        if exist is None:
            new += 1
        rows.append((eid, it["code"], it["type"], it.get("source_id", ""),
                     it.get("title", ""), it.get("url", ""),
                     it.get("published_at") or t, it.get("content", ""),
                     it.get("level", "neutral"), t))
    c.executemany("""
        INSERT INTO entry(id,code,type,source_id,title,url,published_at,content,level,created_at)
        VALUES(?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(id) DO UPDATE SET
          title=excluded.title, url=excluded.url,
          published_at=excluded.published_at, content=excluded.content,
          level=excluded.level
    """, rows)
    c.commit()
    return new, len(rows)


def list_entries(code, type_=None, days=30, level=None, limit=200):
    c = conn()
    sql = "SELECT * FROM entry WHERE code=?"
    args = [code]
    if type_:
        sql += " AND type=?"
        args.append(type_)
    if days:
        sql += " AND published_at >= ?"
        args.append(now() - days * 86400)
    if level:
        sql += " AND level=?"
        args.append(level)
    sql += " ORDER BY published_at DESC LIMIT ?"
    args.append(limit)

    return [{
        "id": r["id"], "code": r["code"], "type": r["type"],
        "title": r["title"], "url": r["url"],
        "published_at": r["published_at"], "level": r["level"],
        "content": r["content"],
    } for r in c.execute(sql, args).fetchall()]


def get_entry(eid):
    c = conn()
    r = c.execute("SELECT * FROM entry WHERE id=?", (eid,)).fetchone()
    if not r:
        return None
    d = {k: r[k] for k in r.keys()}
    # 同公司前后 5 条
    d["siblings"] = [{
        "id": x["id"], "title": x["title"],
        "published_at": x["published_at"], "level": x["level"],
    } for x in c.execute("""
        SELECT id,title,published_at,level FROM entry
        WHERE code=? AND id<>? ORDER BY published_at DESC LIMIT 5
    """, (d["code"], eid)).fetchall()]
    return d


def count_entries(code=None):
    c = conn()
    if code:
        r = c.execute("SELECT COUNT(*) n FROM entry WHERE code=?", (code,)).fetchone()
    else:
        r = c.execute("SELECT COUNT(*) n FROM entry").fetchone()
    return r["n"] if r else 0


def search_entries(q, limit=20):
    """
    全文检索。entry_fts 为 trigram 分词（迁移 001）：
      · ≥3 字符查询走 FTS（中文子串、英文、代码都命中）
      · <3 字符 trigram 无 token，降级 LIKE
    异常一律退 LIKE，绝不让搜索 500。
    """
    c = conn()
    q = (q or "").strip()
    if not q:
        return []

    def _like():
        return c.execute(
            "SELECT * FROM entry WHERE title LIKE ? OR content LIKE ? "
            "ORDER BY published_at DESC LIMIT ?",
            (f"%{q}%", f"%{q}%", limit)).fetchall()

    rows = []
    if len(q) >= 3:
        try:
            rows = c.execute("""
                SELECT e.* FROM entry_fts f
                JOIN entry e ON e.rowid = f.rowid
                WHERE entry_fts MATCH ?
                ORDER BY e.published_at DESC LIMIT ?
            """, (q, limit)).fetchall()
        except sqlite3.OperationalError:
            rows = []
    if not rows:
        rows = _like()

    return [{"id": r["id"], "code": r["code"], "type": r["type"],
             "title": r["title"], "published_at": r["published_at"],
             "level": r["level"]} for r in rows]


def rag_context(q, limit=12, uid=None):
    """
    M5 · RAG 检索：为全局 AI 助手收集上下文。
    组合：该用户关注池 thesis + 全文检索命中的词条 + 各票最新行情。
    """
    uid = _uid(uid)
    c = conn()
    watch = list_watch(uid)

    # 1) 关键词抽取：q 里的中文词直接 LIKE 命中标题
    hits = []
    seen = set()
    q_clean = (q or "").strip()
    if q_clean:
        # 全文检索（FTS 对中文按字分词可能不佳，同时做 LIKE 兜底）
        for r in search_entries(q_clean, 12):
            if r["id"] not in seen:
                seen.add(r["id"])
                hits.append(r)
        # 逐段 2-4 字滑窗再补一轮
        terms = set()
        L = len(q_clean)
        for n in (4, 3, 2):
            for i in range(0, max(0, L - n + 1)):
                t = q_clean[i:i + n]
                if any('\u4e00' <= ch <= '\u9fff' for ch in t):
                    terms.add(t)
        for t in list(terms)[:8]:
            for r in c.execute(
                "SELECT id,code,type,title,published_at,level FROM entry "
                "WHERE title LIKE ? ORDER BY published_at DESC LIMIT 8",
                (f"%{t}%",)).fetchall():
                d = dict(r)
                if d["id"] not in seen:
                    seen.add(d["id"])
                    hits.append(d)

    # 2) 每只关注票的最新 3 条词条（保证上下文不偏科）
    for w in watch:
        for r in c.execute(
            "SELECT id,code,type,title,published_at,level FROM entry "
            "WHERE code=? ORDER BY published_at DESC LIMIT 3",
            (w["code"],)).fetchall():
            d = dict(r)
            if d["id"] not in seen:
                seen.add(d["id"])
                hits.append(d)

    # 3) 行情快照
    quotes = {}
    for w in watch:
        quotes[w["code"]] = latest_quote(w["code"])

    return {
        "watch": watch,
        "hits": hits[:limit],
        "quotes": quotes,
        "total_entries": count_entries(),
    }


# ---------------- AI 缓存（M2 版本化） ----------------

def thesis_hash(thesis):
    """thesis 指纹：内容变化 → 缓存失效"""
    import hashlib
    t = (thesis or "").strip()
    return hashlib.sha1(t.encode("utf-8")).hexdigest()[:16] if t else ""



def make_cache_key(entry_id, model="", prompt_version="", th_hash=""):
    """缓存键：同一条词条，模型/提示词/thesis 任一变化都不复用旧结果"""
    return f"{entry_id}|{model}|{prompt_version}|{th_hash}"


def get_entry_ai(entry_id, model=None, prompt_version=None, th_hash=None, uid=None):
    """
    精确取缓存（版本匹配才返回），按 user_id 隔离。
    不传版本参数时退化为旧行为（返回最新一条），仅用于展示。
    """
    uid = _uid(uid)
    c = conn()
    r = c.execute("SELECT * FROM entry_ai WHERE user_id=? AND entry_id=?",
                  (uid, entry_id)).fetchone()
    if not r:
        return None
    d = {k: r[k] for k in r.keys()}
    if model is not None or prompt_version is not None or th_hash is not None:
        want = make_cache_key(entry_id,
                              model if model is not None else d.get("model", ""),
                              prompt_version if prompt_version is not None else d.get("prompt_version", ""),
                              th_hash if th_hash is not None else d.get("thesis_hash", ""))
        if (d.get("cache_key") or "") != want:
            return None      # 版本不匹配 → 视为未缓存
    return d


def save_entry_ai(entry_id, model, summary, why_matters, thesis_impact,
                  read_hint, tokens=0, prompt_version="v0", th_hash="",
                  extra=None, uid=None):
    """
    写入缓存 + 归档历史版本（ai_analysis_version 保留全部），按 user_id 隔离。
    """
    uid = _uid(uid)
    ckey = make_cache_key(entry_id, model, prompt_version, th_hash)
    c = conn()
    c.execute("""
        INSERT INTO entry_ai(user_id,entry_id,model,summary,why_matters,thesis_impact,
                             read_hint,tokens,created_at,thesis_hash,prompt_version,cache_key)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(user_id,entry_id) DO UPDATE SET
          model=excluded.model, summary=excluded.summary,
          why_matters=excluded.why_matters, thesis_impact=excluded.thesis_impact,
          read_hint=excluded.read_hint, tokens=excluded.tokens,
          created_at=excluded.created_at, thesis_hash=excluded.thesis_hash,
          prompt_version=excluded.prompt_version, cache_key=excluded.cache_key
    """, (uid, entry_id, model, summary, why_matters, thesis_impact, read_hint,
          tokens, now(), th_hash, prompt_version, ckey))
    # 归档历史（同一用户下同 cache_key 不重复归档）
    dup = c.execute("SELECT 1 FROM ai_analysis_version WHERE user_id=? AND cache_key=?",
                    (uid, ckey)).fetchone()
    if not dup:
        c.execute("""
            INSERT INTO ai_analysis_version
              (user_id,entry_id,cache_key,model,summary,why_matters,thesis_impact,
               read_hint,tokens,thesis_hash,prompt_version,created_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
        """, (uid, entry_id, ckey, model, summary, why_matters, thesis_impact,
              read_hint, tokens, th_hash, prompt_version, now()))
    c.commit()


def list_entry_ai_versions(entry_id, limit=10, uid=None):
    uid = _uid(uid)
    rows = conn().execute("""
        SELECT cache_key, model, thesis_hash, prompt_version, created_at, summary
        FROM ai_analysis_version WHERE user_id=? AND entry_id=?
        ORDER BY created_at DESC LIMIT ?
    """, (uid, entry_id, limit)).fetchall()
    return [dict(r) for r in rows]


def thesis_version(code, uid=None):
    """当前 thesis 版本号（该用户历史修改次数 + 1）"""
    uid = _uid(uid)
    r = conn().execute(
        "SELECT COUNT(*) n FROM thesis_history WHERE user_id=? AND code=?",
        (uid, code)).fetchone()
    return (r["n"] if r else 0) + 1


def save_thesis_change(code, old, new, reason="", uid=None):
    uid = _uid(uid)
    c = conn()
    c.execute("""INSERT INTO thesis_history(user_id,code,thesis_old,thesis_new,reason,changed_at)
                 VALUES(?,?,?,?,?,?)""",
              (uid, code, old or "", new or "", reason or "", now()))
    c.commit()


def list_thesis_history(code, limit=20, uid=None):
    uid = _uid(uid)
    rows = conn().execute(
        "SELECT * FROM thesis_history WHERE user_id=? AND code=? "
        "ORDER BY changed_at DESC LIMIT ?",
        (uid, code, limit)).fetchall()
    return [dict(r) for r in rows]


# ---------------- 词条用户状态（M4） ----------------

STATUS_LABEL = {
    "unread": "未读",
    "reading": "研究中",
    "pending": "待核查",
    "processed": "已处理",
    "ignored": "已忽略",
    "saved": "稍后研究",
}


def set_entry_state(entry_id, status=None, is_read=None, note=None, uid=None):
    """更新词条用户状态（不存在则创建），按 user_id 隔离"""
    uid = _uid(uid)
    c = conn()
    row = c.execute("SELECT * FROM entry_user_state WHERE user_id=? AND entry_id=?",
                    (uid, entry_id)).fetchone()
    if row is None:
        c.execute("""INSERT INTO entry_user_state
                     (user_id,entry_id,status,is_read,note,updated_at) VALUES(?,?,?,?,?,?)""",
                  (uid, entry_id, status or "unread", 1 if is_read else 0,
                   note or "", now()))
    else:
        sets, vals = [], []
        if status is not None:
            sets.append("status=?")
            vals.append(status)
        if is_read is not None:
            sets.append("is_read=?")
            vals.append(1 if is_read else 0)
        if note is not None:
            sets.append("note=?")
            vals.append(note)
        if sets:
            sets.append("updated_at=?")
            vals.append(now())
            vals.extend([uid, entry_id])
            c.execute(f"UPDATE entry_user_state SET {','.join(sets)} "
                      f"WHERE user_id=? AND entry_id=?", vals)
    c.commit()
    return get_entry_state(entry_id, uid)


def get_entry_state(entry_id, uid=None):
    uid = _uid(uid)
    r = conn().execute(
        "SELECT * FROM entry_user_state WHERE user_id=? AND entry_id=?",
        (uid, entry_id)).fetchone()
    if not r:
        return {"entry_id": entry_id, "status": "unread", "is_read": 0,
                "note": "", "updated_at": None}
    return dict(r)


def bulk_set_state(entry_ids, status=None, is_read=None, uid=None):
    uid = _uid(uid)
    for eid in entry_ids:
        set_entry_state(eid, status=status, is_read=is_read, uid=uid)
    return len(entry_ids)


def state_map(entry_ids, uid=None):
    """批量取状态：{entry_id: state}"""
    uid = _uid(uid)
    if not entry_ids:
        return {}
    qs = ",".join("?" * len(entry_ids))
    rows = conn().execute(
        f"SELECT * FROM entry_user_state WHERE user_id=? AND entry_id IN ({qs})",
        [uid, *entry_ids]).fetchall()
    return {r["entry_id"]: dict(r) for r in rows}


def state_counts(uid=None):
    """各状态计数（资讯管理页用），按用户隔离"""
    uid = _uid(uid)
    rows = conn().execute(
        "SELECT status, COUNT(*) n FROM entry_user_state WHERE user_id=? GROUP BY status",
        (uid,)).fetchall()
    out = {k: 0 for k in STATUS_LABEL}
    for r in rows:
        out[r["status"]] = r["n"]
    total = count_entries()
    marked = sum(v for k, v in out.items() if k != "unread")
    out["unread"] = max(0, total - marked) + out.get("unread", 0)
    return out


# ---------------- 研究笔记与报告（M6） ----------------

def add_research(code, title, content="", tags="", entry_ids="", uid=None):
    uid = _uid(uid)
    c = conn()
    c.execute("""INSERT INTO research_record
                 (user_id,code,title,content,tags,entry_ids,created_at,updated_at)
                 VALUES(?,?,?,?,?,?,?,?)""",
              (uid, code, title, content, tags, entry_ids, now(), now()))
    c.commit()
    return c.execute("SELECT last_insert_rowid() id").fetchone()["id"]


def update_research(rid, title=None, content=None, tags=None, entry_ids=None, uid=None):
    uid = _uid(uid)
    c = conn()
    sets, vals = [], []
    if title is not None:
        sets.append("title=?"); vals.append(title)
    if content is not None:
        sets.append("content=?"); vals.append(content)
    if tags is not None:
        sets.append("tags=?"); vals.append(tags)
    if entry_ids is not None:
        sets.append("entry_ids=?"); vals.append(entry_ids)
    if sets:
        sets.append("updated_at=?"); vals.append(now())
        vals.extend([rid, uid])
        c.execute(f"UPDATE research_record SET {','.join(sets)} "
                  f"WHERE id=? AND user_id=?", vals)
        c.commit()
        return True
    return False


def delete_research(rid, uid=None):
    uid = _uid(uid)
    c = conn()
    c.execute("DELETE FROM research_record WHERE id=? AND user_id=?", (rid, uid))
    c.commit()


def list_research(code="", q="", limit=50, offset=0, uid=None):
    """code 为空时列出该用户全部；q 支持标题/内容/标签 LIKE"""
    uid = _uid(uid)
    c = conn()
    where, vals = ["user_id=?"], [uid]
    if code:
        where.append("code=?"); vals.append(code)
    if q:
        where.append("(title LIKE ? OR content LIKE ? OR tags LIKE ?)")
        vals.extend([f"%{q}%"] * 3)
    rows = c.execute(
        f"SELECT * FROM research_record WHERE {' AND '.join(where)} "
        f"ORDER BY updated_at DESC LIMIT ? OFFSET ?",
        (*vals, limit, offset)).fetchall()
    return [dict(r) for r in rows]


def get_research(rid, uid=None):
    uid = _uid(uid)
    r = conn().execute("SELECT * FROM research_record WHERE id=? AND user_id=?",
                       (rid, uid)).fetchone()
    return dict(r) if r else None


def save_report(kind, title, content, code="", meta="", period="", uid=None):
    uid = _uid(uid)
    c = conn()
    c.execute("""INSERT INTO research_report
                 (user_id,kind,code,title,content,meta,period,created_at)
                 VALUES(?,?,?,?,?,?,?,?)""",
              (uid, kind, code, title, content, meta, period, now()))
    c.commit()
    return c.execute("SELECT last_insert_rowid() id").fetchone()["id"]


def list_reports(kind="", code="", period="", limit=30, offset=0, uid=None):
    uid = _uid(uid)
    c = conn()
    where, vals = ["user_id=?"], [uid]
    if kind:
        where.append("kind=?"); vals.append(kind)
    if code:
        where.append("code=?"); vals.append(code)
    if period:
        where.append("period=?"); vals.append(period)
    rows = c.execute(
        f"SELECT id,kind,code,title,period,created_at FROM research_report "
        f"WHERE {' AND '.join(where)} ORDER BY created_at DESC LIMIT ? OFFSET ?",
        (*vals, limit, offset)).fetchall()
    return [dict(r) for r in rows]


def get_report(rid, uid=None):
    uid = _uid(uid)
    r = conn().execute("SELECT * FROM research_report WHERE id=? AND user_id=?",
                       (rid, uid)).fetchone()
    return dict(r) if r else None


def delete_report(rid, uid=None):
    uid = _uid(uid)
    c = conn()
    c.execute("DELETE FROM research_report WHERE id=? AND user_id=?", (rid, uid))
    c.commit()


def monthly_window(period):
    """period 'YYYY-MM' → (start_ts, end_ts)"""
    import datetime as _dt
    y, m = period.split("-")
    start = _dt.datetime(int(y), int(m), 1)
    if int(m) == 12:
        end = _dt.datetime(int(y) + 1, 1, 1)
    else:
        end = _dt.datetime(int(y), int(m) + 1, 1)
    return int(start.timestamp()), int(end.timestamp())


# ---------------- chat ----------------

def add_chat(scope, role, content, uid=None):
    uid = _uid(uid)
    cid = hashlib.sha1(f"{uid}|{scope}|{role}|{content}|{time.time()}".encode()).hexdigest()
    c = conn()
    c.execute("INSERT INTO chat(id,scope,role,content,created_at,user_id) "
              "VALUES(?,?,?,?,?,?)",
              (cid, scope, role, content, now(), uid))
    c.commit()
    return cid


def list_chat(scope, limit=50, uid=None):
    uid = _uid(uid)
    rows = conn().execute(
        "SELECT * FROM chat WHERE user_id=? AND scope=? ORDER BY created_at DESC LIMIT ?",
        (uid, scope, limit)).fetchall()
    return [{"role": r["role"], "content": r["content"],
             "created_at": r["created_at"]} for r in reversed(rows)]


def clear_chat(scope, uid=None):
    uid = _uid(uid)
    c = conn()
    c.execute("DELETE FROM chat WHERE user_id=? AND scope=?", (uid, scope))
    c.commit()
    return True


# ---------------- 行情 ----------------

def save_quote(q):
    if not q or not q.get("price"):
        return
    c = conn()
    c.execute("""
        INSERT OR REPLACE INTO quote(code,ts,price,pct,volume_ratio,pe,pb,mcap,
          open,high,low,prev_close,amount_wan,turnover_pct,amplitude_pct)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (q["code"], now(), q["price"], q.get("pct"),
          q.get("vol_ratio"), q.get("pe_ttm"), q.get("pb"), q.get("mcap_yi"),
          q.get("open"), q.get("high"), q.get("low"), q.get("prev_close"),
          q.get("amount_wan"), q.get("turnover_pct"), q.get("amplitude_pct")))
    c.commit()


def latest_quote(code):
    r = conn().execute(
        "SELECT * FROM quote WHERE code=? ORDER BY ts DESC LIMIT 1",
        (code,)).fetchone()
    if not r:
        return None
    return {"code": r["code"], "ts": r["ts"], "price": r["price"], "pct": r["pct"],
            "vol_ratio": r["volume_ratio"], "pe": r["pe"], "pb": r["pb"],
            "mcap": r["mcap"],
            "open": r["open"], "high": r["high"], "low": r["low"],
            "prev_close": r["prev_close"], "amount_wan": r["amount_wan"],
            "turnover_pct": r["turnover_pct"], "amplitude_pct": r["amplitude_pct"]}


def prune_quotes(days=30):
    c = conn()
    c.execute("DELETE FROM quote WHERE ts < ?", (now() - days * 86400,))
    c.commit()


# ---------------- TTL ----------------

TTL = {
    "universe": 24 * 3600,
    "quote_open": 30,
    "quote_closed": 3600,
    "notice": 15 * 60,
    "qa": 15 * 60,
    "news": 30 * 60,
    "report": 6 * 3600,
    "chip": 6 * 3600,
    "kline_day": 6 * 3600,
    "kline_week": 6 * 3600,
    "kline_month": 6 * 3600,
    "kline_minute": 60,
    "kline_5m": 5 * 60,
    "kline_15m": 5 * 60,
    "kline_30m": 5 * 60,
    "kline_60m": 5 * 60,
    "kline_5day": 30 * 60,
}


def mark_fetched(key, source="", status="ok", error=""):
    """记录抓取时间与状态（M1 新鲜度体系）"""
    c = conn()
    c.execute("""INSERT OR REPLACE INTO fetch_log(key,fetched_at,source,status,error)
                 VALUES(?,?,?,?,?)""",
              (key, now(), source or key.split(":")[0], status, error or ""))
    c.commit()


def mark_failed(key, error, source=""):
    """抓取失败：保留旧 fetched_at 不动，只记 error/status（旧有效数据不被覆盖）"""
    c = conn()
    row = c.execute("SELECT fetched_at FROM fetch_log WHERE key=?", (key,)).fetchone()
    ts = row["fetched_at"] if row else 0
    c.execute("""INSERT OR REPLACE INTO fetch_log(key,fetched_at,source,status,error)
                 VALUES(?,?,?,?,?)""",
              (key, ts, source or key.split(":")[0], "failed", str(error)[:300]))
    c.commit()


def data_status(key):
    """返回 fresh/stale/failed/missing/unknown"""
    r = conn().execute(
        "SELECT * FROM fetch_log WHERE key=?", (key,)).fetchone()
    if not r:
        return {"key": key, "status": "missing", "fetched_at": 0,
                "source": "", "error": "", "age": None}
    age = now() - (r["fetched_at"] or 0)
    if r["status"] == "failed":
        st = "failed"
    elif r["fetched_at"] and not need_refresh(key):
        st = "fresh"
    elif r["fetched_at"]:
        st = "stale"
    else:
        st = "unknown"
    return {"key": key, "status": st, "fetched_at": r["fetched_at"],
            "source": r["source"] or "", "error": r["error"] or "", "age": age}


def last_fetched(key):
    r = conn().execute("SELECT fetched_at FROM fetch_log WHERE key=?", (key,)).fetchone()
    return r["fetched_at"] if r else 0


def quote_freshness(code):
    """行情新鲜度（详情页与 AI 上下文标注数据时间用）"""
    import datetime as _dt
    q = latest_quote(code)
    if not q:
        return {"status": "missing", "age_sec": None, "at": None}
    age = now() - q["ts"]
    if age <= 60:
        st = "fresh"
    elif age <= 30 * 60:
        st = "delayed"
    else:
        st = "stale"
    return {"status": st, "age_sec": age,
            "at": _dt.datetime.fromtimestamp(q["ts"]).strftime("%H:%M:%S")}


def prune_quotes(days=7):
    """
    清理 quote 明细：保留最近 days 天。
    清理前先把每只票每天的最后一条存入 quote_daily（永久保留）。
    只对交易日生成快照（周末/节假日产生的重复值无意义）。
    """
    import datetime as _dt
    c = conn()
    cutoff = now() - days * 86400

    # 1. 待删区间内的每日快照先落库（仅周一到周五）
    rows = c.execute("""
        SELECT q.code, date(q.ts,'unixepoch','localtime') d,
               q.price,q.pct,q.open,q.high,q.low,q.prev_close,
               q.amount_wan,q.turnover_pct,q.pe,q.pb,q.mcap
        FROM quote q
        INNER JOIN (
            SELECT code, date(ts,'unixepoch','localtime') d, MAX(ts) mx
            FROM quote WHERE ts < ? GROUP BY code, d
        ) t ON t.code=q.code AND t.mx=q.ts
    """, (cutoff,)).fetchall()

    for r in rows:
        try:
            wd = _dt.datetime.strptime(r["d"], "%Y-%m-%d").weekday()
        except Exception:
            continue
        if wd >= 5:      # 周六日跳过
            continue
        c.execute("""
            INSERT OR REPLACE INTO quote_daily
              (code,date,price,pct,open,high,low,prev_close,
               amount_wan,turnover_pct,pe,pb,mcap)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (r["code"], r["d"], r["price"], r["pct"], r["open"], r["high"],
              r["low"], r["prev_close"], r["amount_wan"], r["turnover_pct"],
              r["pe"], r["pb"], r["mcap"]))

    # 2. 删明细
    n = c.execute("SELECT COUNT(*) FROM quote WHERE ts < ?", (cutoff,)).fetchone()[0]
    c.execute("DELETE FROM quote WHERE ts < ?", (cutoff,))
    c.commit()
    return n


def quant_daily(code, limit=120):
    """每日收盘快照（长周期历史）"""
    rows = conn().execute(
        "SELECT * FROM quote_daily WHERE code=? ORDER BY date DESC LIMIT ?",
        (code, limit)).fetchall()
    return [dict(r) for r in rows]


def wal_checkpoint():
    """WAL 合并（防堆积膨胀）"""
    try:
        c = conn()
        r = c.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchall()
        return r
    except Exception:
        return None


def need_refresh(key):
    """key 形如 quote:000060 / notice:000060 / universe / kline:000060:day"""
    kind = key.split(":")[0]
    if kind == "quote":
        ttl = TTL["quote_open"] if _is_trading_time() else TTL["quote_closed"]
    elif kind == "kline":
        period = key.split(":")[2]
        ttl = TTL.get(f"kline_{period}", 3600)
        # 日/周/月 K 盘中不刷新（收盘后才更新）
        if period in ("day", "week", "month"):
            return (now() - last_fetched(key)) > ttl
    else:
        ttl = TTL.get(kind, 3600)
    return (now() - last_fetched(key)) > ttl


def _is_trading_time():
    """粗略判断：工作日 9:15-15:05"""
    import datetime
    n = datetime.datetime.now()
    if n.weekday() >= 5:
        return False
    t = n.hour * 60 + n.minute
    return (9 * 60 + 15) <= t <= (15 * 60 + 5)


# ---------------- K线 ----------------

def save_kline(code, period, bars):
    """bars: [{ts,o,h,l,c,volume,amount}]"""
    if not bars:
        return
    c = conn()
    c.executemany("""
        INSERT OR REPLACE INTO kline(code,period,ts,o,h,l,c,volume,amount)
        VALUES(?,?,?,?,?,?,?,?,?)
    """, [(code, period, b["ts"], b["o"], b["h"], b["l"], b["c"],
           b.get("volume"), b.get("amount")) for b in bars])
    c.commit()


def load_kline(code, period, limit=250):
    rows = conn().execute(
        "SELECT * FROM kline WHERE code=? AND period=? ORDER BY ts DESC LIMIT ?",
        (code, period, limit)).fetchall()
    return [{
        "ts": r["ts"], "o": r["o"], "h": r["h"], "l": r["l"], "c": r["c"],
        "volume": r["volume"], "amount": r["amount"],
    } for r in reversed(rows)]


# 分时点存储（minute/5day）：JSON 快照存 meta 表
def save_timeline(code, period, points):
    import json as _json
    c = conn()
    c.execute("INSERT OR REPLACE INTO meta(k,v) VALUES(?,?)",
              (f"timeline:{code}:{period}",
               _json.dumps(points[-1500:], ensure_ascii=False)))
    c.commit()


def load_timeline(code, period):
    import json as _json
    r = conn().execute("SELECT v FROM meta WHERE k=?",
                       (f"timeline:{code}:{period}",)).fetchone()
    if not r:
        return []
    try:
        return _json.loads(r["v"])
    except Exception:
        return []


# ---------------- 统计 ----------------

def stats():
    c = conn()
    return {
        "stocks": c.execute("SELECT COUNT(*) n FROM stock").fetchone()["n"],
        "watch": c.execute("SELECT COUNT(*) n FROM watch").fetchone()["n"],
        "entries": c.execute("SELECT COUNT(*) n FROM entry").fetchone()["n"],
        "entry_ai": c.execute("SELECT COUNT(*) n FROM entry_ai").fetchone()["n"],
        "quotes": c.execute("SELECT COUNT(*) n FROM quote").fetchone()["n"],
        "db_mb": round(DB_PATH.stat().st_size / 1e6, 2) if DB_PATH.exists() else 0,
    }


if __name__ == "__main__":
    init()
    print("DB:", DB_PATH)
    print(stats())
