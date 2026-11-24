# -*- coding: utf-8 -*-
"""FTS5 同步触发器 + trigram 重建 + fetch_log 扩展（数据新鲜度）

FTS 分词器决策（实测 2026-11-17，SQLite 3.49.1）：
- 默认 unicode61：连续中文整串成单 token，子串查询（岭南→中金岭南）全不命中
- trigram：≥3 字中文子串全命中；2 字查不到（token 最小 3 字符）
- 方案：entry_fts/stock_fts 重建为 trigram；store.search_entries 对 <3 字
  查询降级 LIKE。业务表 entry/stock 一行不动（fts 是虚拟表，随便重建）。
"""
DESCRIPTION = "fts trigram rebuild + sync triggers + fetch_log freshness"

upgrade_sql = """
-- ============ fetch_log 新鲜度字段 ============
ALTER TABLE fetch_log ADD COLUMN source TEXT DEFAULT '';
ALTER TABLE fetch_log ADD COLUMN status TEXT DEFAULT 'ok';
ALTER TABLE fetch_log ADD COLUMN error TEXT DEFAULT '';
"""


def upgrade(c):
    c.executescript(upgrade_sql)

    # ---- entry_fts 重建为 trigram（虚拟表，业务数据不动）----
    c.executescript("""
DROP TRIGGER IF EXISTS trg_entry_ai;
DROP TRIGGER IF EXISTS trg_entry_ad;
DROP TRIGGER IF EXISTS trg_entry_au;
DROP TABLE IF EXISTS entry_fts;
CREATE VIRTUAL TABLE entry_fts USING fts5(
  title, content, tokenize='trigram', content='entry', content_rowid='rowid'
);

CREATE TRIGGER trg_entry_ai AFTER INSERT ON entry BEGIN
  INSERT INTO entry_fts(rowid, title, content)
  VALUES (new.rowid, new.title, new.content);
END;
CREATE TRIGGER trg_entry_ad AFTER DELETE ON entry BEGIN
  INSERT INTO entry_fts(entry_fts, rowid, title, content)
  VALUES ('delete', old.rowid, old.title, old.content);
END;
CREATE TRIGGER trg_entry_au AFTER UPDATE ON entry BEGIN
  INSERT INTO entry_fts(entry_fts, rowid, title, content)
  VALUES ('delete', old.rowid, old.title, old.content);
  INSERT INTO entry_fts(rowid, title, content)
  VALUES (new.rowid, new.title, new.content);
END;
INSERT INTO entry_fts(entry_fts) VALUES('rebuild');

-- ---- stock_fts 重建为 trigram ----
DROP TRIGGER IF EXISTS trg_stock_ai;
DROP TRIGGER IF EXISTS trg_stock_ad;
DROP TRIGGER IF EXISTS trg_stock_au;
DROP TABLE IF EXISTS stock_fts;
CREATE VIRTUAL TABLE stock_fts USING fts5(
  code, name, pinyin, concepts, tokenize='trigram',
  content='stock', content_rowid='rowid'
);

CREATE TRIGGER trg_stock_ai AFTER INSERT ON stock BEGIN
  INSERT INTO stock_fts(rowid, code, name, pinyin, concepts)
  VALUES (new.rowid, new.code, new.name, new.pinyin, new.concepts);
END;
CREATE TRIGGER trg_stock_ad AFTER DELETE ON stock BEGIN
  INSERT INTO stock_fts(stock_fts, rowid, code, name, pinyin, concepts)
  VALUES ('delete', old.rowid, old.code, old.name, old.pinyin, old.concepts);
END;
CREATE TRIGGER trg_stock_au AFTER UPDATE ON stock BEGIN
  INSERT INTO stock_fts(stock_fts, rowid, code, name, pinyin, concepts)
  VALUES ('delete', old.rowid, old.code, old.name, old.pinyin, old.concepts);
  INSERT INTO stock_fts(rowid, code, name, pinyin, concepts)
  VALUES (new.rowid, new.code, new.name, new.pinyin, new.concepts);
END;
INSERT INTO stock_fts(stock_fts) VALUES('rebuild');
""")

    # 既有 fetch_log 行补默认 source
    c.execute("UPDATE fetch_log SET source='unknown' WHERE source IS NULL OR source=''")
