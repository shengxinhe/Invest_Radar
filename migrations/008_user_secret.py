# -*- coding: utf-8 -*-
"""
M8 · 每个用户自己的 DeepSeek Key 与 AI 设置

设计
----
- user_secret 每个 user_id 一行
- deepseek_key_enc 只存 Fernet 密文；加密密钥来自环境变量 RADAR_SECRET_KEY
- key_hint 只存脱敏提示（sk-…abcd），供 UI 回显，不足以还原
- 不记录明文到日志（调用侧一律用 mask_key 输出）

幂等：CREATE TABLE IF NOT EXISTS。
"""
DESCRIPTION = "user_secret: per-user encrypted deepseek key + ai settings"

SQL = """
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
"""


def upgrade(c):
    c.executescript(SQL)
