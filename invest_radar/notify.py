# -*- coding: utf-8 -*-
"""
M5 · 三级通知分级与去重
  一级 P1：重要风险（停产/事故/立案/退市/业绩预亏等）→ 立即推送
  二级 P2：值得研究的变化（担保/解禁/大额减持/事务所变更等）→ 定时汇总
  三级 P3：普通资讯 → 仅入库，不推送
"""
import json
from datetime import datetime

from . import config, store

QUEUE = config.DATA_DIR / "alerts_queue.json"

# P1 关键词（真·重大风险）
P1_KEYWORDS = (
    "停产", "事故", "立案", "调查", "退市", "暂停上市", "亏损", "预亏",
    "违约", "债务", "爆雷", "被查封", "冻结", "重大诉讼", "仲裁",
    "终止", "失败", "下调", "减值", "非标意见", "无法表示意见",
    "控制权变更", "实际控制人变更", "董事长", "总经理辞职",
)
# P2 关键词（值得关注但不必立刻打扰）
P2_KEYWORDS = (
    "担保", "解禁", "减持", "增持", "回购", "股权激励", "定增",
    "重大合同", "中标", "投产", "产能", "涨价", "提价",
    "会计师事务所", "审计机构", "分红", "业绩预告", "业绩快报",
)
# P3 降噪（名称类，仅入库）
P3_KEYWORDS = (
    "证券简称", "简称变更", "LOGO", "办公地址", "迁址", "投资者关系活动记录表",
    "聘任", "离任", "选举",
)


def classify(title: str, level: str = "neutral") -> str:
    """返回 p1 / p2 / p3"""
    t = title or ""
    if any(k in t for k in P1_KEYWORDS):
        return "p1"
    if any(k in t for k in P2_KEYWORDS):
        return "p2"
    if any(k in t for k in P3_KEYWORDS):
        return "p3"
    # 词条 level 兜底：risk 至少 p2
    if level == "risk":
        return "p2"
    if level == "positive":
        return "p2"
    return "p3"


def dedup_key(code: str, title: str) -> str:
    """去重键：同公司 + 标题（去掉空白与标点差异）"""
    import re
    t = re.sub(r"[\s:：，,。.、（）()【】\-—]", "", title or "")
    return f"{code}:{t[:60]}"


def already_notified(code: str, title: str, within_hours: int = 72) -> bool:
    """72h 内是否推过同一条（防重复打扰）"""
    import time
    k = dedup_key(code, title)
    c = store.conn()
    rows = c.execute("""
        SELECT title FROM notification_log
        WHERE code=? AND created_at > ?
    """, (code, int(time.time()) - within_hours * 3600)).fetchall()
    return any(dedup_key(code, r["title"]) == k for r in rows)


def log_notification(level, code, title, entry_id="", status="queued", channel="wechat"):
    import time
    c = store.conn()
    c.execute("""INSERT INTO notification_log
                 (level,code,title,entry_id,channel,status,created_at)
                 VALUES(?,?,?,?,?,?,?)""",
              (level, code, title, entry_id, channel, status, int(time.time())))
    c.commit()
    return c.execute("SELECT last_insert_rowid() id").fetchone()["id"]


def mark_sent(nid: int):
    import time
    c = store.conn()
    c.execute("UPDATE notification_log SET status='sent', sent_at=? WHERE id=?",
              (int(time.time()), nid))
    c.commit()


def mark_failed(nid: int):
    c = store.conn()
    c.execute("UPDATE notification_log SET status='failed' WHERE id=?", (nid,))
    c.commit()


def daily_quota_ok(limit_p1=10, limit_p2=5) -> tuple[bool, str]:
    """每日推送量控制"""
    import time
    c = store.conn()
    day_start = int(datetime.now().replace(hour=0, minute=0, second=0,
                                           microsecond=0).timestamp())
    p1 = c.execute("""SELECT COUNT(*) n FROM notification_log
                      WHERE level='p1' AND created_at>=?""", (day_start,)).fetchone()["n"]
    p2 = c.execute("""SELECT COUNT(*) n FROM notification_log
                      WHERE level='p2' AND created_at>=?""", (day_start,)).fetchone()["n"]
    if p1 >= limit_p1:
        return False, f"P1 今日已达上限（{p1}/{limit_p1}）"
    if p2 >= limit_p2:
        return False, f"P2 今日已达上限（{p2}/{limit_p2}）"
    return True, ""


def pending_by_level(level: str, limit: int = 20) -> list[dict]:
    """取待推送的通知"""
    c = store.conn()
    rows = c.execute("""SELECT * FROM notification_log
                        WHERE level=? AND status='queued'
                        ORDER BY created_at DESC LIMIT ?""",
                     (level, limit)).fetchall()
    return [dict(r) for r in rows]


def stats():
    c = store.conn()
    rows = c.execute("""SELECT level, status, COUNT(*) n FROM notification_log
                        GROUP BY level, status""").fetchall()
    out = {}
    for r in rows:
        out.setdefault(r["level"], {})[r["status"]] = r["n"]
    return out
