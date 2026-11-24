# -*- coding: utf-8 -*-
"""
M7 运维修复：quote 表无限增长 + WAL 膨胀

问题：共享轮询每 5s 落一次库 × 4 只 × 4h = 1.2 万行/天，DB 一月涨到 100MB+
方案：
  · quote 只保留最近 N 天明细（AI 上下文与新鲜度只需最新值）
  · 每天保留每只票 1 条收盘快照（供历史对比）
  · WAL 定期 checkpoint 防堆积
"""
DESCRIPTION = "quote retention: keep 7d detail + daily close snapshot"

upgrade_sql = """
-- 每日收盘快照表（长周期保留，永久不删）
CREATE TABLE IF NOT EXISTS quote_daily (
  code TEXT, date TEXT, price REAL, pct REAL,
  open REAL, high REAL, low REAL, prev_close REAL,
  amount_wan REAL, turnover_pct REAL, pe REAL, pb REAL, mcap REAL,
  PRIMARY KEY (code, date)
);
CREATE INDEX IF NOT EXISTS idx_qd_code ON quote_daily(code, date DESC);

-- quote 明细表加索引优化清理
CREATE INDEX IF NOT EXISTS idx_quote_ts ON quote(ts);
"""


def upgrade(c):
    c.executescript(upgrade_sql)
    # 回填历史：每天每只票取最后一条作为收盘快照
    c.execute("""
        INSERT OR REPLACE INTO quote_daily
          (code, date, price, pct, open, high, low, prev_close,
           amount_wan, turnover_pct, pe, pb, mcap)
        SELECT q.code,
               date(q.ts,'unixepoch','localtime') AS d,
               q.price, q.pct, q.open, q.high, q.low, q.prev_close,
               q.amount_wan, q.turnover_pct, q.pe, q.pb, q.mcap
        FROM quote q
        INNER JOIN (
            SELECT code, date(ts,'unixepoch','localtime') d, MAX(ts) mx
            FROM quote GROUP BY code, d
        ) t ON t.code=q.code AND t.mx=q.ts
    """)
