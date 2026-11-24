# -*- coding: utf-8 -*-
"""M6: 研究笔记 + 研究报告归档"""
DESCRIPTION = "research_record + research_report tables"

upgrade_sql = """
-- 个人研究笔记
CREATE TABLE IF NOT EXISTS research_record (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  code TEXT NOT NULL,
  title TEXT NOT NULL,
  content TEXT DEFAULT '',
  tags TEXT DEFAULT '',            -- 逗号分隔
  entry_ids TEXT DEFAULT '',       -- 关联词条 id，逗号分隔
  created_at INTEGER,
  updated_at INTEGER
);
CREATE INDEX IF NOT EXISTS idx_rr_code ON research_record(code, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_rr_updated ON research_record(updated_at DESC);

-- 研究报告（AI 生成：晨报/复盘/今日重点/辩论等归档）
CREATE TABLE IF NOT EXISTS research_report (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  kind TEXT NOT NULL,              -- daily_brief / monthly_review / today_focus / debate / entry_ai
  code TEXT DEFAULT '',            -- 个股相关时记录
  title TEXT NOT NULL,
  content TEXT DEFAULT '',
  meta TEXT DEFAULT '',            -- JSON：模型/耗时/引用来源等
  period TEXT DEFAULT '',          -- 如 2026-11 用于月度
  created_at INTEGER
);
CREATE INDEX IF NOT EXISTS idx_rep_kind ON research_report(kind, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_rep_code ON research_report(code, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_rep_period ON research_report(period, created_at DESC);
"""


def upgrade(c):
    c.executescript(upgrade_sql)
