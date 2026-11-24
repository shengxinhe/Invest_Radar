# -*- coding: utf-8 -*-
"""Session 落库：重启服务保持登录"""
DESCRIPTION = "sessions table for persistent login"

upgrade_sql = """
CREATE TABLE IF NOT EXISTS app_session (
  sid TEXT PRIMARY KEY,
  created_at INTEGER NOT NULL,
  last_seen INTEGER,
  ip TEXT DEFAULT '',
  ua TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_sess_last ON app_session(last_seen DESC);
"""


def upgrade(c):
    c.executescript(upgrade_sql)
