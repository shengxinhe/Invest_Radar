# -*- coding: utf-8 -*-
"""词条用户处理状态 + thesis 历史 + 通知日志"""
DESCRIPTION = "entry_user_state + thesis_history + notification_log"

upgrade_sql = """
CREATE TABLE IF NOT EXISTS entry_user_state (
  entry_id TEXT PRIMARY KEY,
  status TEXT DEFAULT 'unread',     -- unread/reading/pending/processed/ignored/saved
  is_read INTEGER DEFAULT 0,
  note TEXT DEFAULT '',
  updated_at INTEGER
);
CREATE INDEX IF NOT EXISTS idx_eus_status ON entry_user_state(status, updated_at DESC);

CREATE TABLE IF NOT EXISTS thesis_history (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  code TEXT NOT NULL,
  thesis_old TEXT,
  thesis_new TEXT,
  reason TEXT DEFAULT '',
  changed_at INTEGER
);
CREATE INDEX IF NOT EXISTS idx_th_code ON thesis_history(code, changed_at DESC);

CREATE TABLE IF NOT EXISTS notification_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  level TEXT,                       -- p1/p2/p3
  code TEXT,
  title TEXT,
  entry_id TEXT,
  channel TEXT DEFAULT 'wechat',
  status TEXT DEFAULT 'queued',     -- queued/sent/failed/read/processed
  created_at INTEGER,
  sent_at INTEGER
);
CREATE INDEX IF NOT EXISTS idx_nl_status ON notification_log(status, created_at DESC);
"""


def upgrade(c):
    c.executescript(upgrade_sql)
