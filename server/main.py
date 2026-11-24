# -*- coding: utf-8 -*-
"""M8 · FastAPI 服务：业务 API + 静态托管 PWA（本机运行版）"""
import asyncio
import io
import json
import os
import sys
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path


def _load_dotenv():
    """
    显式加载 .env，且必须在其它模块读取 os.environ 之前执行。
    之前依赖 server.llm.client 的导入副作用，顺序一变配置就丢。
    """
    env = Path(__file__).resolve().parent.parent / ".env"
    if not env.exists():
        return
    for raw in env.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k:
            os.environ.setdefault(k, v)


_load_dotenv()

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from invest_radar import analyzer, config, fetcher, store, sync
from invest_radar.universe import update_universe
from invest_radar import watcher
from invest_radar.websearch import web_search
from server import auth_routes, identity, quotes, sse, usersecret
from server.llm import client as llm
from server.llm import prompts

WEB_DIR = config.ROOT / "web_build"
DATA_ACTION_TIMEOUT = 180


@asynccontextmanager
async def lifespan(app):
    store.init()
    identity.prune_sessions()      # M3: 清理过期会话
    await quotes.start()           # M5: 共享行情轮询
    # 主数据过期就后台补（不阻塞启动）
    try:
        await asyncio.to_thread(update_universe)
    except Exception as e:
        print(f"[universe] 更新失败: {e}")
    yield
    await quotes.stop()


app = FastAPI(title="投资雷达", version="2.0.0", lifespan=lifespan)

# M1: CORS 收敛——只允许本机与 Tailscale 域名
# M8: 允许网页域名 + Capacitor WebView 的 origin（APK 走 Bearer，不依赖 Cookie）
_ALLOWED = [
    o.strip() for o in os.environ.get(
        "RADAR_ALLOWED_ORIGINS",
        "http://127.0.0.1:8000,http://localhost:8000,http://localhost:5173,"
        "https://you.xn--6or.gay,https://localhost,capacitor://localhost",
    ).split(",") if o.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Radar-Token"],
    expose_headers=["Content-Disposition"],
)


@app.middleware("http")
async def auth_guard(request: Request, call_next):
    """
    M8: 身份闸门。
    · 公共路径放行
    · 其余路径从 Cookie / Bearer 解析 uid，写入 contextvar，
      之后 store 层默认按该 uid 过滤（见 invest_radar/ctx.py）
    · 解析失败直接 401，请求体里传什么 user_id 都不会被采信
    """
    from invest_radar import ctx
    if request.method == "OPTIONS" or identity.is_public(request):
        return await call_next(request)
    uid = identity.resolve_session(identity.token_from_request(request))
    if not uid:
        return JSONResponse({"ok": False, "msg": "未登录",
                             "detail": "unauthorized"}, status_code=401)
    token = ctx.set_uid(uid)
    try:
        return await call_next(request)
    finally:
        ctx.reset(token)


app.include_router(auth_routes.router)


# ---------------- 工具 ----------------

def ok(data):
    return {"ok": True, "data": data, "ts": int(datetime.now().timestamp())}


def fail(msg, code=400):
    raise HTTPException(status_code=code, detail=msg)


def _model(kind="cheap"):
    """M8: 模型按用户设置取；用户没设就用默认。"""
    from invest_radar import ctx
    try:
        cheap, strong = usersecret.models(ctx.current_uid())
    except Exception:
        cheap, strong = llm.MODEL_CHEAP, llm.MODEL_STRONG
    return strong if kind == "strong" else cheap


def _fmt_entry(e):
    return {
        "id": e["id"],
        "code": e["code"],
        "type": e["type"],
        "title": e["title"],
        "url": e["url"],
        "level": e["level"],
        "published_at": e["published_at"],
        "date": datetime.fromtimestamp(e["published_at"]).strftime("%Y-%m-%d")
        if e.get("published_at") else "",
    }


def _kline_payload(kline, limit=120):
    if kline is None or not len(kline):
        return []
    out = []
    for _, r in kline.tail(limit).iterrows():
        out.append({
            "d": r["date"].strftime("%m-%d"),
            "o": round(float(r["open"]), 2),
            "c": round(float(r["close"]), 2),
            "h": round(float(r["high"]), 2),
            "l": round(float(r["low"]), 2),
            "v": float(r["volume"]),
        })
    return out


# ---------------- 健康检查 ----------------

@app.get("/api/health")
def health():
    """公开：仅存活状态（M1 脱敏，不再暴露库统计）"""
    return {"ok": True, "ts": int(datetime.now().timestamp()), "service": "radar", "version": "2.0.0"}


@app.get("/api/stats")
def api_stats():
    """需登录：库统计"""
    return ok(store.stats())


# ---------------- 关注池 ----------------

@app.get("/api/watch")
def api_watch():
    items = store.list_watch()
    # 补最新行情
    for it in items:
        q = store.latest_quote(it["code"])
        if q:
            it["price"] = q["price"]
            it["pct"] = q["pct"]
            it["pe"] = q["pe"]
            it["pb"] = q["pb"]
            it["mcap"] = q["mcap"]
            it["quote_ts"] = q["ts"]
    return ok(items)


class WatchIn(BaseModel):
    code: str
    thesis: str | None = None
    keywords: list[str] | None = None
    role: str | None = None
    tags: list[str] | None = None
    sort: int | None = None
    reason: str | None = None      # M4: thesis 修改原因


@app.post("/api/watch")
def api_watch_add(w: WatchIn):
    code = (w.code or "").strip()
    if not code.isdigit() or len(code) != 6:
        fail("股票代码必须是 6 位数字")
    store.init()
    store.upsert_watch(code=code, role=w.role, thesis=w.thesis,
                       keywords=w.keywords, tags=w.tags, sort=w.sort)
    return ok(store.get_watch(code))


@app.delete("/api/watch/{code}")
def api_watch_del(code: str):
    store.del_watch(code)
    return ok({"code": code, "deleted": True})


class ReorderIn(BaseModel):
    codes: list[str]


@app.put("/api/watch/reorder")
def api_watch_reorder(body: ReorderIn):
    """拖拽排序：按传入顺序写 sort（只影响自己）"""
    store.reorder_watch(body.codes[:200])
    return ok({"updated": len(body.codes[:200])})


# ---------------- 搜索 ----------------

@app.get("/api/search")
def api_search(q: str = Query("", min_length=0), limit: int = 20):
    if not q.strip():
        return ok([])
    return ok(store.search_stock(q.strip(), limit))


# ---------------- 个股 ----------------

@app.get("/api/stock/{code}")
def api_stock(code: str, refresh: bool = False):
    """概览。未关注的票首次访问自动懒抓取（只抓行情，~2s）。"""
    store.init()

    # 任意 6 位代码都接受；名字优先取主数据
    stock = store.get_stock(code) or {}
    watch = store.get_watch(code)
    name = (watch or {}).get("name") or stock.get("name") or code

    need = refresh or store.need_refresh(f"quote:{code}")
    if need:
        sync.sync_light(code, name)

    q = store.latest_quote(code)
    quote = None
    if q:
        quote = {
            "code": code, "price": q["price"], "pct": q["pct"],
            "vol_ratio": q["vol_ratio"], "pe_ttm": q["pe"], "pb": q["pb"],
            "mcap_yi": q["mcap"],
        }
        k = fetcher.get_kline(code)
        m = fetcher.build_metrics({"code": code,
                                   "price": q["price"], "pct": q["pct"],
                                   "vol_ratio": q["vol_ratio"],
                                   "pe_ttm": q["pe"], "pb": q["pb"],
                                   "mcap_yi": q["mcap"]}, k)
        if m:
            for key in ("high_1y", "low_1y", "position", "ma20", "ma60",
                        "above_ma20", "above_ma60"):
                quote[key] = m.get(key)

    return ok({
        "code": code,
        "name": name,
        "industry": stock.get("industry", ""),
        "in_watch": bool(watch),
        "watch": watch,
        "quote": quote,
        "freshness": store.quote_freshness(code),
        "sources": {
            "quote": store.data_status(f"quote:{code}")["status"],
            "notice": store.data_status(f"notice:{code}")["status"],
            "news": store.data_status(f"news:{code}")["status"],
            "kline": store.data_status(f"kline:{code}:day")["status"],
        },
        "trend": analyzer.trend_read(quote) if quote else None,
        "valuation": analyzer.valuation(quote) if quote else [],
        "entries_count": {t: len(store.list_entries(code, t, 3650, None, 500))
                          for t in ("notice", "news", "qa", "report")},
    })


@app.get("/api/stock/{code}/chart")
def api_chart(code: str, days: int = 120):
    k = fetcher.get_kline(code)
    return ok(_kline_payload(k, days))


@app.get("/api/stock/{code}/entries")
def api_entries(code: str, type: str | None = None,
                days: int = 30, level: str | None = None, limit: int = 200,
                status: str | None = None):
    rows = store.list_entries(code, type, days, level, limit)
    states = store.state_map([e["id"] for e in rows])
    out = []
    for e in rows:
        item = _fmt_entry(e)
        st = states.get(e["id"])
        item["status"] = (st or {}).get("status", "unread")
        item["is_read"] = (st or {}).get("is_read", 0)
        item["note"] = (st or {}).get("note", "")
        out.append(item)
    if status:
        out = [x for x in out if x["status"] == status]
    return ok(out)


@app.get("/api/stock/{code}/extras")
def api_extras(code: str):
    """筹码类：股东/两融/解禁/龙虎榜（这些不进 entry 表，实时抓 + 短缓存）"""
    key = f"chip:{code}"
    cached = store.last_fetched(key)
    fresh = not store.need_refresh(key)

    if fresh and cached:
        raw = store.conn().execute(
            "SELECT v FROM meta WHERE k=?", (f"chip_json:{code}",)).fetchone()
        if raw:
            try:
                return ok(json.loads(raw["v"]))
            except json.JSONDecodeError:
                pass

    data = {
        "holders": fetcher.get_holders(code),
        "margin": fetcher.get_margin(code, 10),
        "lockup": fetcher.get_lockup(code),
        "lhb": fetcher.get_lhb(code, 120),
    }
    store.mark_fetched(key)
    c = store.conn()
    c.execute("INSERT OR REPLACE INTO meta(k,v) VALUES(?,?)",
              (f"chip_json:{code}", json.dumps(data, ensure_ascii=False)))
    c.commit()
    return ok(data)


@app.get("/api/stock/{code}/reports")
def api_reports(code: str):
    rows = store.list_entries(code, "report", days=3650, limit=50)
    return ok([_fmt_entry(e) for e in rows])


@app.get("/api/market")
def api_market(days: int = 2, limit: int = 60):
    """全市场快讯（大盘背景）"""
    rows = store.list_entries("MARKET", "market", days, None, limit)
    return ok([_fmt_entry(e) for e in rows])


# ---------------- 词条 ----------------

@app.get("/api/entry/{eid}")
def api_entry(eid: str):
    e = store.get_entry(eid)
    if not e:
        fail("词条不存在", 404)
    ai = store.get_entry_ai(eid)
    return ok({
        "id": e["id"], "code": e["code"], "type": e["type"],
        "title": e["title"], "url": e["url"], "content": e["content"],
        "level": e["level"],
        "published_at": e["published_at"],
        "date": datetime.fromtimestamp(e["published_at"]).strftime("%Y-%m-%d %H:%M")
        if e.get("published_at") else "",
        "siblings": [{
            "id": s["id"], "title": s["title"], "level": s["level"],
            "date": datetime.fromtimestamp(s["published_at"]).strftime("%Y-%m-%d")
            if s.get("published_at") else "",
        } for s in e["siblings"]],
        "ai": ai,
        "watch": store.get_watch(e["code"]),
    })


# ---------------- SSE 行情（M5: 共享轮询 + 广播） ----------------

@app.get("/api/stream/quotes")
async def stream_quotes(codes: str = ""):
    """
    共享轮询模式：所有连接订阅同一个中心任务，不再各自抓上游。
    首帧发缓存快照（避免白屏），之后仅推送有变化的票 + 25s 心跳。
    """
    code_list = [c.strip() for c in codes.split(",") if c.strip()]
    if not code_list:
        # 显式取当前用户的关注池（不依赖生成器上下文）
        from invest_radar import ctx as _ctx
        uid = _ctx.current_uid()
        code_list = [w["code"] for w in store.list_watch(uid)]

    sid, queue = quotes.subscribe(code_list)

    async def gen():
        try:
            for item in quotes.snapshot(code_list):
                yield sse._pack("quote", cached=True, **item)
            yield sse.ev_start(source="shared-poller",
                               interval=quotes._interval(),
                               trading=store._is_trading_time())
            while True:
                try:
                    item = await asyncio.wait_for(queue.get(), timeout=25)
                    yield sse._pack("quote", **item)
                except asyncio.TimeoutError:
                    yield sse._pack("heartbeat",
                                    ts=int(datetime.now().timestamp()))
        except asyncio.CancelledError:
            pass
        finally:
            quotes.unsubscribe(sid)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers=sse.SSE_HEADERS)


@app.get("/api/quotes/poller")
def api_poller_stats():
    """共享轮询器状态（诊断用）"""
    return ok(quotes.stats())


# ---------------- 手动刷新 ----------------

@app.post("/api/stock/{code}/sync")
async def api_sync(code: str):
    """全量抓取并入库（后台跑，可能十几秒）"""
    watch = store.get_watch(code) or {"code": code, "name": code}
    try:
        r = await asyncio.wait_for(
            asyncio.to_thread(sync.sync_all, code, watch),
            timeout=DATA_ACTION_TIMEOUT)
    except asyncio.TimeoutError:
        fail("抓取超时，稍后重试", 504)
    return ok({"code": code, "new": r["new"], "stats": store.stats()})


# ---------------- M3 · AI 解读 ----------------

def _entry_for_ai(eid):
    """取词条 + 观察池上下文 + 行情（完整交易字段）"""
    e = store.get_entry(eid)
    if not e:
        return None, None
    stock = store.get_watch(e["code"]) or store.get_stock(e["code"]) or {"code": e["code"]}
    if "tags" not in stock:
        stock["tags"] = []
    quote = None
    q = store.latest_quote(e["code"])
    if q:
        quote = dict(q)   # 全量字段：开高低/成交额/换手/振幅/量比都进 AI
        # 补趋势指标（MA/分位）——轻量，日K已缓存
        try:
            k = fetcher.get_kline(e["code"])
            m = fetcher.build_metrics({"code": e["code"], "price": q["price"],
                                       "pct": q["pct"], "pe_ttm": q["pe"],
                                       "pb": q["pb"], "mcap_yi": q["mcap"]}, k)
            if m:
                quote.update({key: m.get(key) for key in
                              ("high_1y", "low_1y", "position", "ma20", "ma60")})
        except Exception:
            pass
    return e, {"stock": stock, "quote": quote,
               "freshness": store.quote_freshness(e["code"])}


# 代码级噪音标题（AI 调用前过滤，省 token；命中的解读直接给固定结论）
_NOISE_TITLES = (
    "证券简称变更", "简称变更", "启用新", "LOGO", "办公地址", "迁址",
    "聘任", "辞职", "离任", "投资者关系活动记录表",
)

# 例外白名单：命中噪音词但这些情形必须走 AI
_NOISE_EXCEPTIONS = (
    "变更会计师事务所", "更换会计师事务所",     # 审计变更 = 治理风险信号
    "发行股份购买资产", "重大资产重组",         # 重组相关
    "立案", "处罚", "问询函", "关注函",
)


def _is_noise_title(title: str) -> bool:
    t = title or ""
    if any(k in t for k in _NOISE_EXCEPTIONS):
        return False        # 白名单优先
    return any(k in t for k in _NOISE_TITLES)


@app.post("/api/entry/{eid}/ai")
async def api_entry_ai(eid: str, force: bool = False):
    """
    M2 AI 解读：异步流式 + 七段结构 + 版本化缓存。
    缓存键 = entry_id + model + prompt_version + thesis_hash
    thesis 或提示词变化后自动失效；旧版本留存 ai_analysis_version。
    """
    e, ctx = _entry_for_ai(eid)
    if not e:
        fail("词条不存在", 404)
    stock = ctx["stock"]
    quote = ctx["quote"]
    freshness = ctx["freshness"]
    th_hash = store.thesis_hash(stock.get("thesis"))
    thesis_ver = store.thesis_version(e["code"])

    cached = store.get_entry_ai(eid, model=_model("cheap"),
                                prompt_version=llm.PROMPT_VERSION,
                                th_hash=th_hash)
    if cached and not force:
        def cached_gen():
            yield sse.ev_start(cached=True, model=cached.get("model"))
            for key, label, text in (
                ("conclusion", "核心结论", cached.get("summary")),
                ("impact", "潜在影响", cached.get("why_matters")),
                ("thesis_impact", "对 thesis 的影响", cached.get("thesis_impact")),
                ("todo", "待核查事项", cached.get("read_hint")),
            ):
                if text:
                    yield sse.ev_segment(key, label, text)
            yield sse.ev_done(cached=True, tokens=cached.get("tokens", 0))
        return StreamingResponse(cached_gen(), media_type="text/event-stream",
                                 headers=sse.SSE_HEADERS)

    if _is_noise_title(e.get("title")):
        noise = {
            "conclusion": "程序规则判定为低信息量条目（例行/名称类），尚未经人工核实。",
            "impact": "规则仅做优先级降级处理，不代表对基本面没有影响。",
            "thesis_impact": "暂时无法判断。需人工确认是否涉及业务实质变化。",
            "todo": "如需确认，请点开原文核对是否涉及经营、资产或股权变动。",
        }
        store.save_entry_ai(eid, "rule-based", noise["conclusion"],
                            noise["impact"], noise["thesis_impact"],
                            noise["todo"], 0, "rule", th_hash)

        def noise_gen():
            yield sse.ev_start(model="rule-based")
            yield sse.ev_warning("该条目命中降噪规则，未调用 AI")
            for k, label in (("conclusion", "核心结论"), ("impact", "潜在影响"),
                             ("thesis_impact", "对 thesis 的影响"),
                             ("todo", "待核查事项")):
                yield sse.ev_segment(k, label, noise[k])
            yield sse.ev_done(tokens=0)
        return StreamingResponse(noise_gen(), media_type="text/event-stream",
                                 headers=sse.SSE_HEADERS)

    if not llm.available():
        fail("LLM 未配置：在 .env 填入 DEEPSEEK_API_KEY 后重启", 503)

    async def gen():
        messages = prompts.entry_messages(stock, e, e.get("content"),
                                          quote=quote, freshness=freshness,
                                          thesis_ver=thesis_ver)
        yield sse.ev_start(model=_model("cheap"),
                           prompt_version=llm.PROMPT_VERSION)
        buf = []
        usage = {}
        try:
            async for piece in llm.chat_stream(messages, model=_model("cheap"),
                                               max_tokens=1200, usage_out=usage):
                buf.append(piece)
                yield sse.ev_chunk(piece)
        except llm.LLMError as ex:
            yield sse.ev_error(str(ex), kind=ex.kind)
            return
        except Exception as ex:
            yield sse.ev_error(str(ex)[:200], kind="internal")
            return

        full = "".join(buf)
        segs = sse.split_segments(full, prompts.ENTRY_SEGMENTS)
        d = {k: t for k, _l, t in segs}
        for key, label, text in segs:
            yield sse.ev_segment(key, label, text)

        store.save_entry_ai(
            eid, _model("cheap"),
            d.get("conclusion", ""), d.get("impact", ""),
            d.get("thesis_impact", ""), d.get("todo", ""),
            usage.get("tokens", 0), llm.PROMPT_VERSION, th_hash)
        yield sse.ev_done(tokens=usage.get("tokens", 0), segments=len(segs))

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers=sse.SSE_HEADERS)






class ChatIn(BaseModel):
    question: str
    model: str | None = None   # 默认 strong（追问用深度模型）


@app.post("/api/entry/{eid}/chat")
async def api_entry_chat(eid: str, body: ChatIn):
    """M2 追问：异步流式 + 统一 SSE"""
    e, ctx = _entry_for_ai(eid)
    if not e:
        fail("词条不存在", 404)
    if not llm.available():
        fail("LLM 未配置", 503)

    scope = f"entry:{eid}"
    store.add_chat(scope, "user", body.question)
    history = store.list_chat(scope)

    async def gen():
        messages = prompts.followup_messages(
            ctx["stock"], e, e.get("content"), history[:-1], body.question,
            quote=ctx["quote"], freshness=ctx["freshness"],
            thesis_ver=store.thesis_version(e["code"]))
        yield sse.ev_start()
        buf = []
        try:
            async for piece in llm.chat_stream(
                    messages, model=body.model or _model("strong"),
                    max_tokens=1000):
                buf.append(piece)
                yield sse.ev_chunk(piece)
        except llm.LLMError as ex:
            yield sse.ev_error(str(ex), kind=ex.kind)
            return
        except Exception as ex:
            yield sse.ev_error(str(ex)[:200], kind="internal")
            return
        store.add_chat(scope, "assistant", "".join(buf))
        yield sse.ev_done()

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers=sse.SSE_HEADERS)




class BatchIn(BaseModel):
    entry_ids: list[str]


@app.post("/api/ai/batch")
async def api_ai_batch(body: BatchIn):
    """M2 批量点评：异步流式"""
    if not body.entry_ids:
        fail("entry_ids 为空")
    if not llm.available():
        fail("LLM 未配置", 503)

    entries = []
    code = None
    for eid in body.entry_ids[:20]:
        e = store.get_entry(eid)
        if not e:
            continue
        entries.append(e)
        code = e["code"]
    if not entries:
        fail("词条全部无效")
    stock = store.get_watch(code) or store.get_stock(code) or {"code": code}

    async def gen():
        messages = prompts.batch_messages(stock, entries)
        yield sse.ev_start(count=len(entries))
        buf = []
        try:
            async for piece in llm.chat_stream(messages, model=_model("cheap"),
                                               max_tokens=900):
                buf.append(piece)
                yield sse.ev_chunk(piece)
        except llm.LLMError as ex:
            yield sse.ev_error(str(ex), kind=ex.kind)
            return
        except Exception as ex:
            yield sse.ev_error(str(ex)[:200], kind="internal")
            return
        yield sse.ev_done()

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers=sse.SSE_HEADERS)



@app.post("/api/watcher/tick")
async def api_watcher_tick():
    """跑一轮风险轮询。schedule 定时唤醒时调用。"""
    try:
        r = await asyncio.wait_for(asyncio.to_thread(watcher.watch_tick, True),
                                   timeout=DATA_ACTION_TIMEOUT)
    except asyncio.TimeoutError:
        fail("轮询超时", 504)
    return ok(r)


@app.get("/api/watcher/queue")
def api_watcher_queue():
    q = config.DATA_DIR / "alerts_queue.json"
    try:
        return ok(json.loads(q.read_text(encoding="utf-8")))
    except Exception:
        return ok([])


# ---------------- M5 · 三级通知 ----------------

@app.get("/api/notify/stats")
def api_notify_stats():
    from invest_radar import notify
    return ok({"by_level": notify.stats(),
               "pending_p1": len(notify.pending_by_level("p1")),
               "pending_p2": len(notify.pending_by_level("p2")),
               "quota": notify.daily_quota_ok()[1] or "ok"})


class NotifyMarkIn(BaseModel):
    id: int
    status: str = "sent"


@app.post("/api/notify/mark")
def api_notify_mark(body: NotifyMarkIn):
    from invest_radar import notify
    if body.status == "sent":
        notify.mark_sent(body.id)
    elif body.status == "failed":
        notify.mark_failed(body.id)
    else:
        fail("status 只能是 sent/failed", 400)
    return ok({"id": body.id, "status": body.status})


@app.get("/api/daily")
async def api_daily():
    """晨报数据"""
    try:
        b = await asyncio.wait_for(asyncio.to_thread(watcher.make_daily_brief),
                                   timeout=DATA_ACTION_TIMEOUT)
    except asyncio.TimeoutError:
        fail("生成超时", 504)
    return ok(b)


@app.post("/api/ai/daily-brief")
async def api_ai_daily_brief():
    """M2 AI 晨报：异步流式 + 存档"""
    if not llm.available():
        fail("LLM 未配置", 503)
    b = await asyncio.to_thread(watcher.make_daily_brief)

    lines_in = []
    for s in b["stocks"]:
        q = s.get("price")
        lines_in.append(f"{s['name']}（{s['code']}）现价{q}，"
                        f"PE={s.get('pe')} PB={s.get('pb')}，thesis：{s['thesis']}")
        for label in ("公告", "新闻", "互动", "研报"):
            for it in s.get(label) or []:
                mark = "⚠" if it["level"] == "risk" else ("✓" if it["level"] == "positive" else "")
                lines_in.append(f"  {label}{mark}: {it['title'][:60]}")
    today = datetime.now().strftime("%Y-%m-%d %A")
    prompt = (
        f"今天是 {today}。以下是我关注池的最新快照。请输出一份 ≤500 字的晨报，"
        f"开头写『晨报（{datetime.now().strftime('%Y-%m-%d')}）』，按每股一节：\n"
        "1. 一句话现状（价格+估值水平，数据缺失就写缺失）\n"
        "2. 近24h值得注意的信息（引用具体标题，标风险/利好）\n"
        "3. 结合 thesis 给今日观察点（条件化表述，不给无依据的价位）\n"
        "最后一段：今日整体风险提示 ≤2 行。\n"
        "资料不足的地方直接说'无新信息'，不要编。\n\n" + "\n".join(lines_in)
    )

    async def gen():
        yield sse.ev_start()
        buf = []
        try:
            async for piece in llm.chat_stream(
                    [{"role": "user", "content": prompt}],
                    model=_model("cheap"), max_tokens=1000):
                buf.append(piece)
                yield sse.ev_chunk(piece)
        except llm.LLMError as ex:
            yield sse.ev_error(str(ex), kind=ex.kind)
            return
        except Exception as ex:
            yield sse.ev_error(str(ex)[:200], kind="internal")
            return
        content = "".join(buf)
        try:
            ts = datetime.now().strftime("%Y%m%d")
            (config.OUT_DIR / f"daily_{ts}.md").write_text(content, encoding="utf-8")
        except Exception:
            pass
        try:
            store.save_report(kind="daily_brief", code="",
                              title=f"晨报 {datetime.now().strftime('%Y-%m-%d')}",
                              content=content,
                              meta=json.dumps({"model": _model("cheap")},
                                              ensure_ascii=False))
        except Exception:
            pass
        yield sse.ev_done()

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers=sse.SSE_HEADERS)




def _cursor_encode(level_rank, type_rank, published_at, eid):
    """复合游标：与展示序完全同源的定位键"""
    return f"{level_rank}:{type_rank}:{published_at}:{eid}"


def _cursor_decode(cur):
    """解析游标，非法返回 None"""
    if not cur:
        return None
    parts = str(cur).split(":")
    if len(parts) != 4:
        return None
    try:
        return (int(parts[0]), int(parts[1]), int(parts[2]), parts[3])
    except (ValueError, TypeError):
        return None


@app.get("/api/feed")
async def api_feed(cursor: str = "", limit: int = 25, filter: str | None = None):
    """
    全来源混合资讯流。
    展示序 = (level_rank ASC, type_rank ASC, published_at DESC, id DESC)
    SQL 端完成排序与复合 keyset 分页，与游标同源 → 不重复、不遗漏、同时间戳可正确切页。
    """
    c = store.conn()
    limit = max(1, min(limit, 60))

    level_expr = "CASE e.level WHEN 'risk' THEN 0 WHEN 'positive' THEN 1 ELSE 2 END"
    type_expr = ("CASE e.type WHEN 'notice' THEN 0 WHEN 'qa' THEN 1 "
                 "WHEN 'news' THEN 2 WHEN 'report' THEN 3 ELSE 9 END")

    where = ["e.code != 'MARKET'"]
    args = []
    if filter in ("risk", "positive"):
        where.append("e.level = ?")
        args.append(filter)

    cur = _cursor_decode(cursor)
    if cur:
        cl, ct, cp, cid = cur
        where.append(f"""(
            ({level_expr}) > ?
            OR (({level_expr}) = ? AND ({type_expr}) > ?)
            OR (({level_expr}) = ? AND ({type_expr}) = ? AND e.published_at < ?)
            OR (({level_expr}) = ? AND ({type_expr}) = ? AND e.published_at = ? AND e.id < ?)
        )""")
        args.extend([cl, cl, ct, cl, ct, cp, cl, ct, cp, cid])

    sql = f"""
        SELECT e.*, COALESCE(NULLIF(s.name,''), e.code) AS stock_name,
               ({level_expr}) AS lv_rank, ({type_expr}) AS tp_rank
        FROM entry e
        LEFT JOIN stock s ON s.code = e.code
        WHERE {' AND '.join(where)}
        ORDER BY lv_rank ASC, tp_rank ASC, e.published_at DESC, e.id DESC
        LIMIT ?
    """
    args.append(limit + 1)

    rows = c.execute(sql, args).fetchall()
    has_more = len(rows) > limit
    rows = rows[:limit]

    items = []
    for r in rows:
        ts = r["published_at"]
        items.append({
            "id": r["id"], "code": r["code"], "name": r["stock_name"],
            "type": r["type"], "title": r["title"], "url": r["url"],
            "level": r["level"], "published_at": ts,
            "date": datetime.fromtimestamp(ts).strftime("%m-%d %H:%M") if ts else "",
        })

    next_cursor = None
    if has_more and rows:
        last = rows[-1]
        next_cursor = _cursor_encode(last["lv_rank"], last["tp_rank"],
                                     last["published_at"], last["id"])

    return ok({"items": items, "next_cursor": next_cursor})


@app.get("/api/pulse")
def api_pulse():
    """今日脉搏：关注池风险/利好计数（顶栏呼吸点数据源）"""
    c = store.conn()
    day_ago = store.now() - 86400
    risk = c.execute(
        "SELECT COUNT(*) n FROM entry WHERE level='risk' AND published_at > ?",
        (day_ago,)).fetchone()["n"]
    positive = c.execute(
        "SELECT COUNT(*) n FROM entry WHERE level='positive' AND published_at > ?",
        (day_ago,)).fetchone()["n"]
    q = config.DATA_DIR / "alerts_queue.json"
    queued = 0
    try:
        queued = len(json.loads(q.read_text(encoding="utf-8")))
    except Exception:
        pass
    return ok({"risk": risk, "positive": positive, "queued": queued})


# ---------------- M3 · 市场概览（真实指数） ----------------

_INDEX_CODES = [("sh000001", "上证指数"), ("sz399001", "深证成指"),
                ("sz399006", "创业板指")]
_index_cache = {"ts": 0, "data": None}
_INDEX_TTL = 60


@app.get("/api/market/overview")
def api_market_overview():
    """
    大盘概览：三大指数 + 关注池涨跌 + 全市场涨跌家数。
    真实腾讯接口；失败 available=False（前端显示"暂无数据"，不编造）。
    """
    import time as _t
    now_ts = _t.time()
    if _index_cache["data"] and now_ts - _index_cache["ts"] < _INDEX_TTL:
        payload = dict(_index_cache["data"])
        payload["cached"] = True
        return ok(payload)

    indices = []
    err = ""
    for code, name in _INDEX_CODES:
        try:
            r = fetcher.sess_get(f"https://qt.gtimg.cn/q={code}",
                                 headers={"Referer": "https://gu.qq.com/"})
            r.encoding = "gbk"
            parts = r.text.split("~")
            if len(parts) > 32:
                indices.append({
                    "code": code[-6:], "name": name,
                    "price": float(parts[3]) if parts[3] else None,
                    "pct": float(parts[32]) if parts[32] else None,
                    "change": float(parts[31]) if parts[31] else None,
                })
        except Exception as e:
            err = str(e)[:80]

    # 关注池涨跌
    up = down = flat = 0
    for w in store.list_watch():
        q = store.latest_quote(w["code"])
        if not q or q.get("pct") is None:
            continue
        if q["pct"] > 0:
            up += 1
        elif q["pct"] < 0:
            down += 1
        else:
            flat += 1

    data = {
        "available": bool(indices),
        "indices": indices,
        "watch_stat": {"up": up, "down": down, "flat": flat},
        "at": datetime.now().strftime("%H:%M:%S"),
        "error": err,
    }
    if indices:
        _index_cache.update({"ts": now_ts, "data": data})
    return ok(data)


# ---------------- M3 · AI 今日研究建议 ----------------

@app.post("/api/ai/today-focus")
async def api_ai_today_focus():
    """
    今日最值得研究的三件事。
    依据：近 24h 词条（风险优先）+ 关注池行情。无数据时明确拒绝生成。
    """
    if not llm.available():
        fail("LLM 未配置", 503)

    c = store.conn()
    # 窗口：优先近 24h；不足 2 条时自动放宽到 7 天（避免收盘后永远无内容）
    window_h = 24
    rows = []
    for win in (24, 72, 168):
        cutoff = store.now() - win * 3600
        rows = c.execute("""
            SELECT e.*, COALESCE(NULLIF(s.name,''), e.code) AS nm
            FROM entry e LEFT JOIN stock s ON s.code=e.code
            WHERE e.code!='MARKET' AND e.published_at > ?
            ORDER BY CASE e.level WHEN 'risk' THEN 0 WHEN 'positive' THEN 1 ELSE 2 END,
                     e.published_at DESC LIMIT 20
        """, (cutoff,)).fetchall()
        if len(rows) >= 2:
            window_h = win
            break

    if len(rows) < 2:
        return ok({"available": False,
                   "msg": "近 7 天可分析信息不足（少于 2 条），暂不生成研究建议。"})

    items = []
    for r in rows[:12]:
        d = datetime.fromtimestamp(r["published_at"]).strftime("%m-%d")
        items.append(f"[{d}][{r['level']}][{r['type']}] {r['nm']}: {r['title'][:60]}")

    watch_lines = []
    for w in store.list_watch():
        q = store.latest_quote(w["code"])
        if q and q.get("price"):
            watch_lines.append(f"{w['name']}({w['code']}) {q['price']} "
                               f"{q['pct']:+.2f}%，thesis：{(w['thesis'] or '未设定')[:60]}")

    prompt = (
        f"以下是我关注池近 {window_h} 小时的信息和行情。"
        "请挑出**今天最值得我研究的三件事**。\n\n"
        f"【行情】\n" + "\n".join(watch_lines) + "\n\n"
        f"【信息】\n" + "\n".join(items) + "\n\n"
        "输出格式（每件事 ≤3 行）：\n"
        "1. 什么事（引用具体标题和日期）\n"
        "2. 为什么今天值得研究（对 thesis 的影响路径）\n"
        "3. 具体查什么（可执行的核查动作）\n\n"
        "要求：\n"
        "- 只从上面资料里挑，不许引入资料外的信息\n"
        "- 若信息量不足以支撑三件事，就只给能支撑的条数，并说明原因\n"
        "- 若全部是低信息量噪音，直接说'今日无值得优先研究的事项'\n"
        "- 不给买卖建议"
    )

    async def gen():
        yield sse.ev_start()
        buf = []
        try:
            async for piece in llm.chat_stream(
                    [{"role": "user", "content": prompt}],
                    model=_model("cheap"), max_tokens=900):
                buf.append(piece)
                yield sse.ev_chunk(piece)
        except llm.LLMError as ex:
            yield sse.ev_error(str(ex), kind=ex.kind)
            return
        except Exception as ex:
            yield sse.ev_error(str(ex)[:200], kind="internal")
            return
        yield sse.ev_done()

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers=sse.SSE_HEADERS)


# ---------------- M5 · 全局助手 / thesis 编辑 / 成本 ----------------

class GlobalChatIn(BaseModel):
    question: str
    web: bool = True     # 默认联网检索


@app.post("/api/ai/global")
async def api_ai_global(body: GlobalChatIn):
    """
    全局 AI 助手：RAG + 可选联网检索（巨潮公告库 + 东财快讯）。
    多轮对话存 chat 表（scope=global）。
    """
    if not llm.available():
        fail("LLM 未配置", 503)
    q = (body.question or "").strip()
    if not q:
        fail("问题不能为空")

    ctx = await asyncio.to_thread(store.rag_context, q)

    # 联网检索（后台线程，10s 超时保护）
    web_lines = []
    if body.web:
        try:
            web_results = await asyncio.wait_for(
                asyncio.to_thread(web_search, q), timeout=12)
            if web_results:
                web_lines = ["【外部检索结果】"]
                for w in web_results[:8]:
                    web_lines.append(f"- [外部][{w['source']}][{w['date']}] {w['title']}")
        except Exception:
            pass

    scope = "global"
    store.add_chat(scope, "user", q)
    history = store.list_chat(scope, limit=8)

    # 组装本地上下文（行情块用完整交易字段）
    lines = ["【我的关注池（含实时行情）】"]
    for w in ctx["watch"]:
        qq = ctx["quotes"].get(w["code"])
        if qq and qq.get("price"):
            qb = prompts.quote_block(qq)
            lines.append(f"- {w['name']}（{w['code']}）{qb}")
        else:
            lines.append(f"- {w['name']}（{w['code']}）无行情，thesis：{w['thesis'] or '未设定'}")
        if w.get("thesis"):
            lines.append(f"  └ thesis：{w['thesis']}")
    if ctx["hits"]:
        lines.append("\n【相关词条（本地检索命中）】")
        import datetime as _dt
        for h in ctx["hits"][:12]:
            d = _dt.datetime.fromtimestamp(h["published_at"]).strftime("%m-%d") if h.get("published_at") else ""
            lv = {"risk": "⚠风险", "positive": "✓利好"}.get(h["level"], "")
            lines.append(f"- [{d}][{h['type']}] {h['title']} {lv}")
    lines.append(f"\n（库内共 {ctx['total_entries']} 条词条）")

    system = prompts.global_system(
        "\n".join(lines) + ("\n\n" + "\n".join(web_lines) if web_lines else "")
    )

    async def gen():
        yield sse.ev_start(web_hits=len(web_lines) - 1 if web_lines else 0)
        msgs = [{"role": "system", "content": system}]
        for h in history[:-1]:
            msgs.append({"role": h["role"], "content": h["content"]})
        msgs.append({"role": "user", "content": q})
        buf = []
        try:
            async for piece in llm.chat_stream(msgs, model=_model("cheap"),
                                               max_tokens=900):
                buf.append(piece)
                yield sse.ev_chunk(piece)
        except llm.LLMError as ex:
            yield sse.ev_error(str(ex), kind=ex.kind)
            return
        except Exception as ex:
            yield sse.ev_error(str(ex)[:200], kind="internal")
            return
        store.add_chat(scope, "assistant", "".join(buf))
        yield sse.ev_done()

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers=sse.SSE_HEADERS)


# ---------------- 多空辩论 ----------------
# 结构借鉴 TradingAgents（https://github.com/TauricResearch/TradingAgents, Apache-2.0）
#   看多研究员 -> 看空研究员 -> 裁决者
# 未引入其框架与数据层（其 yfinance 面向美股，A股需巨潮/互动易/龙虎榜）
# 详见 CREDITS.md

@app.post("/api/stock/{code}/debate")
async def api_stock_debate(code: str):
    """
    深度论证：看多研究员 → 看空研究员 → 交易员裁决。
    三阶段 SSE，全部引用已抓数据（公告/研报/互动/行情），可选外部检索补充。
    """
    if not llm.available():
        fail("LLM 未配置", 503)
    stock = store.get_watch(code) or store.get_stock(code) or {"code": code, "name": code}
    if "tags" not in stock:
        stock["tags"] = []

    # 行情（全量交易字段 + 趋势指标）
    quote_obj = None
    q0 = store.latest_quote(code)
    if q0:
        quote_obj = dict(q0)
        try:
            k = fetcher.get_kline(code)
            m = fetcher.build_metrics({"code": code, "price": q0["price"], "pct": q0["pct"],
                                       "pe_ttm": q0["pe"], "pb": q0["pb"], "mcap_yi": q0["mcap"]}, k)
            if m:
                quote_obj.update({key: m.get(key) for key in
                                  ("high_1y", "low_1y", "position", "ma20", "ma60")})
        except Exception:
            pass

    # 收集本地资料（M7 修复：正文不再截断到 120 字，财报/重组等重要内容要完整进上下文）
    c = store.conn()
    import datetime as _dt
    qb = prompts.quote_block(quote_obj)
    mat_lines = [f"行情：{qb}"]

    # M7: 有色/铜相关股自动带铜价（主变量）
    ind = (stock.get("industry") or "") + " " + (stock.get("name") or "")
    wants_copper = any(k in ind for k in
                       ("铜", "有色", "金属", "岭南", "锌", "铅"))
    try:
        # 行业字段为空时，用公司名兜底判断不了的，也查一次铜（成本低）
        cu = fetcher.get_copper_futures(30) if wants_copper or not stock.get("industry") else None
        if cu:
            mat_lines.append(
                f"沪铜主连（{cu['date']}）：{cu['latest']:,.0f}，"
                f"日{cu['chg_1d']:+.2f}% 5日{cu['chg_5d']:+.2f}% "
                f"20日{cu['chg_20d']:+.2f}%，MA20 {cu['ma20']:,.0f} "
                f"MA60 {cu['ma60']:,.0f}，距年内高 "
                f"{(cu['latest']/cu['high_1y']-1)*100:.1f}%")
    except Exception:
        pass

    BUDGET = 14000          # 总字符预算，防超长
    used = len(qb)
    for t in ("notice", "report", "qa"):
        rows = store.list_entries(code, t, days=90, limit=10)
        for r in rows:
            d = _dt.datetime.fromtimestamp(r["published_at"]).strftime("%m-%d") if r.get("published_at") else ""
            body = (r.get("content") or "").strip()
            # 财报/季报/年报给足篇幅，其他词条 300 字
            is_fin = any(k in (r["title"] or "") for k in
                         ("季度报告", "年度报告", "半年度报告", "业绩", "重组"))
            cap = 6000 if is_fin else 300
            body = body[:cap]
            if used + len(body) > BUDGET:
                body = body[:max(0, BUDGET - used)] + "…"
            if not body:
                continue
            used += len(body)
            mat_lines.append(f"[{d}][{t}] {r['title']}\n{body}")
            if used >= BUDGET:
                break
        if used >= BUDGET:
            break
    # 外部补充
    try:
        web = await asyncio.wait_for(asyncio.to_thread(web_search, stock.get("name") or code), timeout=12)
        for w in web[:6]:
            mat_lines.append(f"[外部][{w['source']}][{w['date']}] {w['title']}")
    except Exception:
        pass
    material = "\n".join(mat_lines)

    async def gen():
        name = stock.get("name") or code
        thesis = stock.get("thesis") or "（未设定）"
        stage1, stage2, _ = prompts.debate_messages(stock, material)
        bull_text, bear_text = "", ""

        # 阶段一：看多
        yield sse.ev_progress("bull", detail="看多研究员")
        try:
            async for piece in llm.chat_stream(stage1, model=_model("cheap"),
                                               max_tokens=500):
                bull_text += piece
                yield sse._pack("bull", text=piece)
        except llm.LLMError as ex:
            yield sse.ev_error(str(ex), kind=ex.kind)
            return

        # 阶段二：看空
        yield sse.ev_progress("bear", detail="看空研究员")
        try:
            async for piece in llm.chat_stream(stage2, model=_model("cheap"),
                                               max_tokens=500):
                bear_text += piece
                yield sse._pack("bear", text=piece)
        except llm.LLMError as ex:
            yield sse.ev_error(str(ex), kind=ex.kind)
            return

        # 阶段三：裁决
        yield sse.ev_progress("judge", detail="交易员裁决")
        jmsgs = prompts.judge_messages(name, code, thesis, bull_text, bear_text,
                                       quote=quote_obj)
        judge = []
        try:
            async for piece in llm.chat_stream(jmsgs, model=_model("cheap"),
                                               max_tokens=700):
                judge.append(piece)
                yield sse._pack("judge", text=piece)
        except llm.LLMError as ex:
            yield sse.ev_error(str(ex), kind=ex.kind)
            return

        scope = f"debate:{code}:{_dt.datetime.now().strftime('%Y%m%d')}"
        store.add_chat(scope, "bull", bull_text)
        store.add_chat(scope, "bear", bear_text)
        store.add_chat(scope, "judge", "".join(judge))
        # M6: 辩论归档
        try:
            store.save_report(
                kind="debate", code=code,
                title=f"{name} 多空辩论 {datetime.now().strftime('%m-%d')}",
                content=f"【看多】\n{bull_text}\n\n【看空】\n{bear_text}\n\n【裁决】\n{''.join(judge)}",
                meta=json.dumps({"model": _model("cheap")}, ensure_ascii=False))
        except Exception:
            pass
        yield sse.ev_done()

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers=sse.SSE_HEADERS)


@app.get("/api/websearch")
async def api_websearch(q: str, limit: int = 10):
    """纯搜索接口（给前端"外部资料"页签用）"""
    if not q.strip():
        return ok([])
    r = await asyncio.wait_for(asyncio.to_thread(web_search, q.strip()), timeout=15)
    return ok(r[:limit])


class ThesisIn(BaseModel):
    """M8: code 由路径给，body 只需 thesis（兼容旧前端多传 code 也不报错）"""
    thesis: str | None = None
    keywords: list[str] | None = None
    role: str | None = None
    tags: list[str] | None = None
    reason: str | None = None
    code: str | None = None


@app.put("/api/watch/{code}/thesis")
def api_update_thesis(code: str, w: ThesisIn):
    """M4: 在线编辑 thesis，旧值写入 thesis_history（AI 缓存随之失效）"""
    exist = store.get_watch(code)
    if not exist:
        fail("该票不在关注池", 404)
    old = exist.get("thesis") or ""
    new = w.thesis if w.thesis is not None else old
    store.upsert_watch(code=code, thesis=w.thesis, keywords=w.keywords,
                       role=w.role, tags=w.tags)
    if (new or "").strip() != (old or "").strip():
        store.save_thesis_change(code, old, new, w.reason or "")
    return ok({**(store.get_watch(code) or {}),
               "thesis_version": store.thesis_version(code)})


@app.get("/api/watch/{code}/thesis/history")
def api_thesis_history(code: str):
    return ok(store.list_thesis_history(code, 30))


# ---------------- M4 · 资讯处理状态 ----------------

class EntryStateIn(BaseModel):
    status: str | None = None
    is_read: bool | None = None
    note: str | None = None


class BulkStateIn(BaseModel):
    entry_ids: list[str]
    status: str | None = None
    is_read: bool | None = None


@app.post("/api/entry/{eid}/state")
def api_set_entry_state(eid: str, body: EntryStateIn):
    if body.status and body.status not in store.STATUS_LABEL:
        fail(f"未知状态 {body.status}", 400)
    return ok(store.set_entry_state(eid, body.status, body.is_read, body.note))


@app.post("/api/entries/state")
def api_bulk_state(body: BulkStateIn):
    if body.status and body.status not in store.STATUS_LABEL:
        fail(f"未知状态 {body.status}", 400)
    n = store.bulk_set_state(body.entry_ids[:200], body.status, body.is_read)
    return ok({"updated": n})


@app.get("/api/entries/states")
def api_state_counts():
    return ok(store.state_counts())


# ---------------- M6 · 研究笔记与报告 ----------------

class ResearchIn(BaseModel):
    code: str
    title: str
    content: str = ""
    tags: str = ""
    entry_ids: str = ""


class ResearchUpdIn(BaseModel):
    title: str | None = None
    content: str | None = None
    tags: str | None = None
    entry_ids: str | None = None


@app.post("/api/research")
def api_add_research(body: ResearchIn):
    if not body.title.strip():
        fail("标题不能为空", 400)
    rid = store.add_research(body.code, body.title.strip(), body.content,
                             body.tags, body.entry_ids)
    return ok(store.get_research(rid))


@app.put("/api/research/{rid}")
def api_upd_research(rid: int, body: ResearchUpdIn):
    if not store.get_research(rid):
        fail("笔记不存在", 404)
    store.update_research(rid, body.title, body.content, body.tags, body.entry_ids)
    return ok(store.get_research(rid))


@app.delete("/api/research/{rid}")
def api_del_research(rid: int):
    store.delete_research(rid)
    return ok({"deleted": rid})


@app.get("/api/research")
def api_list_research(code: str = "", q: str = "", limit: int = 50, offset: int = 0):
    return ok(store.list_research(code, q, min(limit, 100), offset))


@app.get("/api/research/{rid}")
def api_get_research(rid: int):
    r = store.get_research(rid)
    if not r:
        fail("笔记不存在", 404)
    return ok(r)


@app.get("/api/reports")
def api_list_reports(kind: str = "", code: str = "", period: str = "",
                     limit: int = 30, offset: int = 0):
    return ok(store.list_reports(kind, code, period, min(limit, 100), offset))


@app.get("/api/reports/{rid}")
def api_get_report(rid: int):
    r = store.get_report(rid)
    if not r:
        fail("报告不存在", 404)
    return ok(r)


@app.delete("/api/reports/{rid}")
def api_del_report(rid: int):
    c = store.conn()
    c.execute("DELETE FROM research_report WHERE id=?", (rid,))
    c.commit()
    return ok({"deleted": rid})


@app.get("/api/reports/{rid}/export")
def api_export_report(rid: int):
    """导出 Markdown"""
    r = store.get_report(rid)
    if not r:
        fail("报告不存在", 404)
    md = f"# {r['title']}\n\n"
    md += f"> 类型：{r['kind']} ｜ 期间：{r['period'] or '—'} ｜ "
    md += f"生成：{datetime.fromtimestamp(r['created_at']).strftime('%Y-%m-%d %H:%M')}\n\n"
    md += r["content"] + "\n"
    return Response(content=md, media_type="text/markdown; charset=utf-8",
                    headers={"Content-Disposition":
                             f"attachment; filename=report_{rid}.md"})


# ---------------- M6 · 月度研究复盘 ----------------

@app.post("/api/ai/monthly-review")
async def api_monthly_review(body: dict):
    """
    按公司生成月度复盘。严格按时间顺序引用资料（不事后伪装）。
    body: {code: "000001", period: "2026-11"}
    """
    if not llm.available():
        fail("LLM 未配置", 503)
    code = body.get("code", "")
    period = body.get("period") or datetime.now().strftime("%Y-%m")
    if not code:
        fail("缺少 code", 400)
    stock = store.get_watch(code) or store.get_stock(code) or {"code": code, "name": code}

    start_ts, end_ts = store.monthly_window(period)
    rows = store.conn().execute("""
        SELECT e.*, COALESCE(NULLIF(s.name,''), e.code) AS nm
        FROM entry e LEFT JOIN stock s ON s.code=e.code
        WHERE e.code=? AND e.published_at>=? AND e.published_at<?
        ORDER BY e.published_at ASC
    """, (code, start_ts, end_ts)).fetchall()

    if not rows:
        return ok({"available": False,
                   "msg": f"{period} 期间 {stock.get('name') or code} 无任何资料，无法复盘。"})

    # 按时间正序列出（复盘必须按历史时间顺序）
    items = []
    for r in rows:
        d = datetime.fromtimestamp(r["published_at"]).strftime("%m-%d")
        items.append(f"[{d}][{r['type']}][{r['level']}] {r['title'][:60]}")

    # 该月 thesis 变更史
    th_changes = [h for h in store.list_thesis_history(code, 50)
                  if start_ts <= (h["changed_at"] or 0) < end_ts]
    th_lines = []
    for h in th_changes:
        d = datetime.fromtimestamp(h["changed_at"]).strftime("%m-%d")
        th_lines.append(f"[{d}] 修改为：{h['thesis_new'][:60]}"
                        + (f"（原因：{h['reason']}）" if h["reason"] else ""))

    # 该月已有的研究报告（晨报等）
    reports = store.list_reports(code=code, limit=20)
    rep_lines = [f"- {r['title']}" for r in reports
                 if start_ts <= (r["created_at"] or 0) < end_ts]

    prompt = (
        f"公司：{stock.get('name') or code}（{code}）\n"
        f"复盘期间：{period}（{len(rows)} 条资料，按时间正序）\n\n"
        f"【当月资料时间线】\n" + "\n".join(items) + "\n\n"
    )
    if th_lines:
        prompt += f"【当月 thesis 变更】\n" + "\n".join(th_lines) + "\n\n"
    if rep_lines:
        prompt += f"【当月已生成的研究记录】\n" + "\n".join(rep_lines[:8]) + "\n\n"

    prompt += (
        "请输出月度复盘（≤600 字，严格依据上面时间线，不引入资料外信息）：\n"
        "1. 本月重要变化（按时间顺序列举 2-4 条，引用具体日期和标题）\n"
        "2. 当前 thesis 得到哪些支持 / 被哪些信息削弱（分别列点）\n"
        "3. 哪些风险得到确认 / 哪些问题仍未解决\n"
        "4. 下月研究重点（2-3 条可执行动作）\n\n"
        "资料不足以判断的部分明确写'资料未覆盖'。不给买卖建议。\n"
    )

    async def gen():
        yield sse.ev_start(period=period, code=code, entries=len(rows))
        buf = []
        try:
            async for piece in llm.chat_stream(
                    [{"role": "user", "content": prompt}],
                    model=_model("cheap"), max_tokens=1200):
                buf.append(piece)
                yield sse.ev_chunk(piece)
        except llm.LLMError as ex:
            yield sse.ev_error(str(ex), kind=ex.kind)
            return
        except Exception as ex:
            yield sse.ev_error(str(ex)[:200], kind="internal")
            return
        content = "".join(buf)
        rid = store.save_report(
            kind="monthly_review", code=code,
            title=f"{stock.get('name') or code} · {period} 月度复盘",
            content=content, period=period,
            meta=json.dumps({"entries": len(rows), "model": _model("cheap")},
                            ensure_ascii=False))
        yield sse.ev_done(report_id=rid)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers=sse.SSE_HEADERS)


@app.get("/api/ai/status")
def api_ai_status():
    """1.0 兼容端点：该用户是否已配 Key"""
    return ok({"available": llm.available(), "prompt_version": llm.PROMPT_VERSION})


@app.get("/api/ai/usage")
def api_ai_usage():
    """成本面板：只统计当前用户自己的用量"""
    from invest_radar import ctx
    uid = ctx.current_uid()
    c = store.conn()
    n_cache = c.execute("SELECT COUNT(*) n FROM entry_ai WHERE user_id=?",
                        (uid,)).fetchone()["n"]
    n_chat = c.execute(
        "SELECT COUNT(*) n FROM chat WHERE user_id=? AND role='user'",
        (uid,)).fetchone()["n"]
    n_chat_msg = c.execute("SELECT COUNT(*) n FROM chat WHERE user_id=?",
                           (uid,)).fetchone()["n"]
    models = c.execute(
        "SELECT model, COUNT(*) n FROM entry_ai WHERE user_id=? GROUP BY model",
        (uid,)).fetchall()
    # 估算（deepseek-chat 输入1元/1M 输出2元/1M；解读约 in 900 + out 500 tok）
    est_calls = n_cache + n_chat
    est_tokens = est_calls * 1400
    est_cost = est_tokens / 1e6 * 1.5   # 混合均价近似
    return ok({
        "cached_interpretations": n_cache,
        "chat_rounds": n_chat,
        "chat_messages": n_chat_msg,
        "by_model": [{"model": r["model"], "count": r["n"]} for r in models],
        "est_total_calls": est_calls,
        "est_tokens": est_tokens,
        "est_cost_cny": round(est_cost, 2),
        "note": "估算值：按每条解读/追问约1400 tokens、混合单价1.5元/1M tokens 计",
    })


# ---------------- M8 · 每个人的 DeepSeek Key ----------------

class KeyIn(BaseModel):
    api_key: str


class AiSettingsIn(BaseModel):
    model_cheap: str | None = None
    model_strong: str | None = None
    ai_enabled: bool | None = None


@app.get("/api/me/key")
def api_get_key():
    """只返回是否已配 + 脱敏提示，绝不返回明文"""
    from invest_radar import ctx
    return ok(usersecret.get_public(ctx.current_uid()))


@app.put("/api/me/key")
def api_put_key(body: KeyIn):
    from invest_radar import ctx
    uid = ctx.current_uid()
    try:
        return ok(usersecret.save_key(uid, body.api_key))
    except ValueError as e:
        fail(str(e), 400)


@app.delete("/api/me/key")
def api_del_key():
    from invest_radar import ctx
    return ok(usersecret.delete_key(ctx.current_uid()))


@app.post("/api/me/key/test")
async def api_test_key():
    """用该用户自己的 Key 发一次最小请求，验证连通性"""
    from invest_radar import ctx
    uid = ctx.current_uid()
    if not llm.available(uid):
        fail("还没配置 Key", 400)
    try:
        r = await llm.chat(
            [{"role": "user", "content": "回复两个字：可用"}],
            model=_model("cheap"), max_tokens=16, timeout=30, uid=uid)
        usersecret.mark_tested(uid, True)
        return ok({"ok": True, "reply": (r.get("text") or "")[:40],
                   "tokens": r.get("tokens", 0)})
    except llm.LLMError as e:
        usersecret.mark_tested(uid, False)
        return {"ok": False, "msg": f"{e.kind}: {e}"}


@app.put("/api/me/ai-settings")
def api_put_ai_settings(body: AiSettingsIn):
    from invest_radar import ctx
    return ok(usersecret.save_settings(
        ctx.current_uid(), body.model_cheap, body.model_strong, body.ai_enabled))


@app.get("/api/chat/global")
def api_chat_global(limit: int = 30):
    return ok(store.list_chat("global", limit))


@app.delete("/api/chat/global")
def api_chat_global_clear():
    store.clear_chat("global")
    return ok({"cleared": True})


# ---------------- B3 · K线接口 ----------------

def _compute_ma(bars, n):
    closes = [b["c"] for b in bars]
    out = []
    for i in range(len(closes)):
        if i < n - 1:
            out.append(None)
        else:
            out.append(round(sum(closes[i - n + 1:i + 1]) / n, 3))
    return out


@app.get("/api/stock/{code}/kline")
def api_kline(code: str, period: str = "day", limit: int = 250):
    """
    K线。period: day/week/month/5m/15m/30m/60m（OHLC）
    返回 klinecharts 兼容 bars + 后端算好的 MA。
    """
    from invest_radar import klinefetch
    if period not in ("day", "week", "month", "5m", "15m", "30m", "60m"):
        fail(f"不支持的周期 {period}", 400)
    r = klinefetch.get_kline_bars(code, period)
    bars = r["bars"][-limit:]
    out = [{
        "timestamp": b["ts"],
        "open": b["o"], "high": b["h"], "low": b["l"], "close": b["c"],
        "volume": b.get("volume"), "turnover": b.get("amount"),
    } for b in bars]
    return ok({
        "period": period, "adjust": "qfq", "bars": out,
        "ma": {"MA5": _compute_ma(bars, 5), "MA10": _compute_ma(bars, 10),
               "MA20": _compute_ma(bars, 20), "MA60": _compute_ma(bars, 60)},
    })


@app.get("/api/stock/{code}/timeline")
def api_timeline(code: str, days: int = 1):
    """
    分时。days=1 当日（带均价+昨收基准），days=5 五日。
    横轴按交易日分钟序号（中午压缩由前端处理）。
    """
    from invest_radar import klinefetch
    period = "minute" if days == 1 else "5day"
    r = klinefetch.get_kline_bars(code, period)
    pts = r["bars"]
    bars = [{
        "timestamp": p["ts"], "price": p["price"],
        "avg_price": p.get("avg"), "volume": p.get("volume"),
    } for p in pts]
    # 昨收：用日K最后一根的昨收（前一交易日收盘）
    pre_close = r.get("pre_close")
    if not pre_close:
        k = klinefetch.get_kline_bars(code, "day")
        closes = [b["c"] for b in k["bars"]]
        pre_close = closes[-2] if len(closes) >= 2 else (closes[-1] if closes else None)
    return ok({"period": period, "bars": bars, "pre_close": pre_close})


# ---------------- 静态托管 ----------------

def _web_file(rel: str):
    return WEB_DIR / rel


@app.get("/api/manifest.webmanifest", include_in_schema=False)
def manifest_api():
    return manifest()


@app.get("/manifest.webmanifest", include_in_schema=False)
def manifest():
    f = _web_file("manifest.webmanifest")
    if not f.exists():
        fail("manifest 不存在", 404)
    return FileResponse(f, media_type="application/manifest+json")


@app.get("/sw.js", include_in_schema=False)
def sw():
    f = _web_file("sw.js")
    if not f.exists():
        fail("sw.js 不存在", 404)
    return FileResponse(f, media_type="application/javascript",
                        headers={"Service-Worker-Allowed": "/"})


@app.get("/", include_in_schema=False)
def index():
    f = _web_file("index.html")
    if not f.exists():
        return JSONResponse(
            {"ok": False, "msg": "web/index.html 不存在，先构建前端: cd web && npm run build"},
            status_code=503)
    return FileResponse(f)


@app.get("/{path:path}", include_in_schema=False)
def spa(path: str):
    if path.startswith("api/"):
        fail("not found", 404)
    f = _web_file(path)
    if f.is_file():
        return FileResponse(f)
    idx = _web_file("index.html")
    if idx.exists():
        return FileResponse(idx)
    fail("not found", 404)


def main():
    import argparse
    import uvicorn

    # M8: 从 .env 读默认值，命令行参数优先
    def _env(k, d):
        v = (os.environ.get(k) or "").strip()
        return v or d

    p = argparse.ArgumentParser()
    # 默认只监听本机（配 Tailscale Serve）；局域网直连用 --host 0.0.0.0
    p.add_argument("--host", default=_env("RADAR_HOST", "127.0.0.1"))
    p.add_argument("--port", type=int, default=int(_env("RADAR_PORT", "8000")))
    p.add_argument("--reload", action="store_true")
    a = p.parse_args()
    uvicorn.run("server.main:app", host=a.host, port=a.port, reload=a.reload)


if __name__ == "__main__":
    main()
