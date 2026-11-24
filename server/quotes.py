# -*- coding: utf-8 -*-
"""
M5 · 共享行情轮询器
问题：原实现每个 SSE 连接各自 while True 调腾讯接口 → N 设备 × M 页面 = N×M 倍上游请求（违反防封红线）

方案：
  中心轮询任务（单例）→ 内存行情缓存 → 多客户端订阅广播
  · 每只股票同一时刻只有一个有效上游请求
  · 数据无变化不推送
  · 客户端断开自动释放订阅
  · 抓取失败不覆盖旧有效值
  · 交易时段 5s / 非交易 60s
"""
import asyncio
import logging
import time
from datetime import datetime

from invest_radar import fetcher, store

log = logging.getLogger("quotes")

# 订阅者：{subscriber_id: asyncio.Queue}
_subs: dict[str, asyncio.Queue] = {}
# 行情缓存：{code: {price, pct, pe, pb, mcap, vol_ratio, ts, stale}}
_cache: dict[str, dict] = {}
# 正在被关注/订阅的代码（动态集合）
_wanted: set[str] = set()
_task: asyncio.Task | None = None
_lock = asyncio.Lock()

MAX_SUBS = 32            # 最大订阅数（单人使用远够）
STATS = {"polls": 0, "pushes": 0, "errors": 0, "last_poll": 0, "last_error": ""}


def _interval() -> int:
    return 5 if store._is_trading_time() else 60


def snapshot(codes=None) -> list[dict]:
    """当前缓存快照（供首帧与 API 使用）"""
    cs = codes if codes else list(_cache.keys())
    out = []
    for c in cs:
        d = _cache.get(c)
        if d:
            out.append(dict(d))
    return out


def subscribe(codes: list[str]) -> tuple[str, asyncio.Queue]:
    """注册订阅者，返回 (sid, queue)。首帧由调用方从 snapshot 取。"""
    if len(_subs) >= MAX_SUBS:
        raise RuntimeError("订阅数已达上限")
    sid = f"sub_{int(time.time()*1000)}_{len(_subs)}"
    q: asyncio.Queue = asyncio.Queue(maxsize=64)
    _subs[sid] = q
    for c in codes:
        _wanted.add(c)
    return sid, q


def unsubscribe(sid: str):
    _subs.pop(sid, None)
    # 没有订阅者引用该票时从 wanted 移除（保留关注池内的票）
    still_needed = set()
    for c in _wanted:
        # 关注池里的票始终保留
        pass
    watch_codes = {w["code"] for w in store.list_watch()}
    _wanted &= watch_codes


async def _broadcast(payloads: list[dict]):
    """向所有订阅者推送（队列满则丢弃最旧）"""
    if not payloads:
        return
    dead = []
    for sid, q in list(_subs.items()):
        for p in payloads:
            try:
                q.put_nowait(p)
            except asyncio.QueueFull:
                try:
                    q.get_nowait()      # 丢最旧
                    q.put_nowait(p)
                except Exception:
                    dead.append(sid)
                    break
    for sid in dead:
        _subs.pop(sid, None)
    STATS["pushes"] += len(payloads)


async def _poll_once():
    """抓一轮 wanted 里的票（串行，遵循抓取红线）"""
    codes = list(_wanted) or [w["code"] for w in store.list_watch()]
    if not codes:
        return
    changed = []
    for code in codes:
        try:
            q = await asyncio.to_thread(fetcher.get_quote, code)
            if not q or not q.get("price"):
                continue
            prev = _cache.get(code)
            payload = {
                "code": code,
                "price": q["price"],
                "pct": q.get("pct"),
                "pe": q.get("pe_ttm"),
                "pb": q.get("pb"),
                "mcap": q.get("mcap_yi"),
                "vol_ratio": q.get("vol_ratio"),
                "turnover": q.get("turnover_pct"),
                "ts": int(time.time()),
            }
            # 只有实际变化才推送（价格/涨跌幅）
            if (prev is None
                    or prev.get("price") != payload["price"]
                    or prev.get("pct") != payload["pct"]):
                changed.append(payload)
            _cache[code] = payload
            # 落库（供 AI 上下文/新鲜度使用）
            await asyncio.to_thread(store.save_quote, {**q, "code": code})
        except Exception as e:
            STATS["errors"] += 1
            STATS["last_error"] = f"{code}: {str(e)[:80]}"
            log.warning("quote poll failed %s: %s", code, e)
    STATS["polls"] += 1
    STATS["last_poll"] = int(time.time())
    if changed:
        await _broadcast(changed)


async def _loop():
    """中心轮询主循环（含运维：WAL checkpoint 每小时 / quote 清理每 6 小时）"""
    last_maint = 0
    last_wal = 0
    while True:
        try:
            await _poll_once()
            import time as _t
            now_ts = _t.time()
            # WAL checkpoint：每小时（防膨胀）
            if now_ts - last_wal > 3600:
                try:
                    await asyncio.to_thread(store.wal_checkpoint)
                except Exception as e:
                    log.warning("wal checkpoint failed: %s", e)
                last_wal = now_ts
            # quote 明细清理：每 6 小时
            if now_ts - last_maint > 6 * 3600:
                try:
                    removed = await asyncio.to_thread(store.prune_quotes, 7)
                    if removed:
                        log.info("pruned %d old quote rows", removed)
                except Exception as e:
                    log.warning("maintenance failed: %s", e)
                last_maint = now_ts
        except asyncio.CancelledError:
            raise
        except Exception as e:
            log.exception("poll loop error: %s", e)
        await asyncio.sleep(_interval())


async def start():
    """启动中心轮询（lifespan 调用，幂等）"""
    global _task
    if _task and not _task.done():
        return
    _task = asyncio.create_task(_loop())
    log.info("shared quote poller started")


async def stop():
    global _task
    if _task:
        _task.cancel()
        try:
            await _task
        except asyncio.CancelledError:
            pass
        _task = None


def stats():
    return {**STATS, "subscribers": len(_subs), "cached": len(_cache),
            "interval": _interval(), "trading": store._is_trading_time()}
