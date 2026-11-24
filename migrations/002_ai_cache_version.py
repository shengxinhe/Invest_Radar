# -*- coding: utf-8 -*-
"""AI 缓存版本化：entry_ai 历史表 + 版本字段（保留旧数据，主键不动）"""
DESCRIPTION = "ai cache versioning: thesis_hash/prompt_version on entry_ai + history table"

upgrade_sql = """
ALTER TABLE entry_ai ADD COLUMN thesis_hash TEXT DEFAULT '';
ALTER TABLE entry_ai ADD COLUMN prompt_version TEXT DEFAULT 'v0';
ALTER TABLE entry_ai ADD COLUMN cache_key TEXT DEFAULT '';

-- 历史版本表：同一词条多次解读全部保留
CREATE TABLE IF NOT EXISTS ai_analysis_version (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  entry_id TEXT NOT NULL,
  cache_key TEXT NOT NULL,
  model TEXT,
  summary TEXT, why_matters TEXT, thesis_impact TEXT, read_hint TEXT,
  tokens INTEGER DEFAULT 0,
  thesis_hash TEXT,
  prompt_version TEXT,
  created_at INTEGER
);
CREATE INDEX IF NOT EXISTS idx_aav_entry ON ai_analysis_version(entry_id, created_at DESC);
"""


def upgrade(c):
    c.executescript(upgrade_sql)
    # 存量为历史记录补 cache_key（等价于旧逻辑 entry_id 单键）
    c.execute("""
        UPDATE entry_ai SET
          prompt_version = CASE WHEN model='rule-based' THEN 'rule' ELSE 'v0' END,
          cache_key = entry_id || '|v0'
    """)
    # 把存量灌入历史表（幂等：只在历史表为空时）
    n = c.execute("SELECT COUNT(*) FROM ai_analysis_version").fetchone()[0]
    if n == 0:
        c.execute("""
            INSERT INTO ai_analysis_version
              (entry_id, cache_key, model, summary, why_matters, thesis_impact, read_hint, tokens, prompt_version, created_at)
            SELECT entry_id, entry_id || '|v0', model, summary, why_matters, thesis_impact, read_hint, tokens, 'v0', created_at
            FROM entry_ai
        """)
