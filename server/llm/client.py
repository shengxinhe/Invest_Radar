# -*- coding: utf-8 -*-
"""
M2 · DeepSeek 客户端（异步版）
- httpx.AsyncClient：不阻塞 FastAPI 事件循环
- 并发限制（信号量）、超时、取消、错误分类、token 统计
- Key 只从服务端 .env 读取
"""
import asyncio
import json
import logging
import os
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent.parent
ENV_PATH = ROOT / ".env"

log = logging.getLogger("llm")

# ---------------- .env ----------------

def load_env():
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


load_env()

BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")

MODEL_CHEAP = os.environ.get("DEEPSEEK_MODEL_CHEAP", "deepseek-chat")
MODEL_STRONG = os.environ.get("DEEPSEEK_MODEL_STRONG", "deepseek-reasoner")

# 提示词版本号：改动 prompts.py 语义时必须 bump（用于 AI 缓存失效）
PROMPT_VERSION = "t2.0-1"

# 并发闸门：同时最多 3 个上游请求（单用户场景足够，防打爆 provider）
_SEM = asyncio.Semaphore(3)

# 用量统计（进程内累计）
_usage = {"calls": 0, "tokens": 0, "errors": 0, "last_error": ""}


class LLMError(Exception):
    def __init__(self, kind, msg):
        self.kind = kind     # auth/rate/timeout/network/bad_response/cancelled
        super().__init__(msg)


def available():
    k = (API_KEY or "").strip()
    return (k.startswith("sk-") and len(k) > 20
            and all(ord(ch) < 128 for ch in k))


def usage_snapshot():
    return dict(_usage)


def _headers():
    if not available():
        raise LLMError("auth", "DEEPSEEK_API_KEY 未配置或格式不正确")
    return {"Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json"}


def _classify(exc) -> LLMError:
    if isinstance(exc, (asyncio.CancelledError, httpx.ReadTimeout,
                        httpx.ConnectTimeout, httpx.WriteTimeout,
                        httpx.PoolTimeout)):
        return LLMError("timeout" if "Timeout" in type(exc).__name__ else "cancelled",
                        f"{type(exc).__name__}")
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        if code in (401, 403):
            return LLMError("auth", f"HTTP {code}")
        if code == 429:
            return LLMError("rate", "HTTP 429 限流")
        return LLMError("bad_response", f"HTTP {code}: {exc.response.text[:160]}")
    if isinstance(exc, (httpx.ConnectError, httpx.RemoteProtocolError, OSError)):
        return LLMError("network", str(exc)[:160])
    return LLMError("bad_response", str(exc)[:160])


# ---------------- 非流式 ----------------

async def chat(messages, model=None, temperature=0.3, max_tokens=800,
               timeout=120):
    url = f"{BASE_URL}/chat/completions"
    body = {"model": model or MODEL_CHEAP, "messages": messages,
            "temperature": temperature, "max_tokens": max_tokens, "stream": False}
    async with _SEM:
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                r = await client.post(url, json=body, headers=_headers())
                r.raise_for_status()
                d = r.json()
        except Exception as e:
            _usage["errors"] += 1
            err = _classify(e)
            _usage["last_error"] = str(err)
            raise err from e
    _usage["calls"] += 1
    tok = (d.get("usage") or {}).get("total_tokens", 0)
    _usage["tokens"] += tok
    return {"text": d["choices"][0]["message"]["content"], "tokens": tok}


# ---------------- 流式（异步生成器） ----------------

async def chat_stream(messages, model=None, temperature=0.3, max_tokens=800,
                      timeout=180, usage_out=None):
    """
    异步流式：逐片 yield 文本。
    usage_out: 可选 dict，函数结束时回填 tokens。
    取消（客户端断开）会抛 asyncio.CancelledError，由调用方处理。
    """
    url = f"{BASE_URL}/chat/completions"
    body = {"model": model or MODEL_CHEAP, "messages": messages,
            "temperature": temperature, "max_tokens": max_tokens, "stream": True}

    async with _SEM:
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                async with client.stream("POST", url, json=body,
                                         headers=_headers()) as r:
                    if r.status_code != 200:
                        raw = (await r.aread()).decode("utf-8", "replace")[:200]
                        _usage["errors"] += 1
                        if r.status_code in (401, 403):
                            raise LLMError("auth", f"HTTP {r.status_code}")
                        if r.status_code == 429:
                            raise LLMError("rate", "HTTP 429 限流")
                        raise LLMError("bad_response",
                                       f"HTTP {r.status_code}: {raw}")

                    buf = b""
                    total_chars = 0
                    async for chunk in r.aiter_bytes():
                        buf += chunk
                        while b"\n" in buf:
                            line, buf = buf.split(b"\n", 1)
                            s = line.decode("utf-8", "replace").strip()
                            if not s.startswith("data:"):
                                continue
                            payload = s[5:].strip()
                            if payload == "[DONE]":
                                _usage["calls"] += 1
                                # 粗估 token（深层统计需 provider usage）
                                est = max(1, total_chars // 2)
                                _usage["tokens"] += est
                                if usage_out is not None:
                                    usage_out["tokens"] = est
                                return
                            try:
                                d = json.loads(payload)
                                piece = (d["choices"][0].get("delta") or {}).get("content")
                                if piece:
                                    total_chars += len(piece)
                                    yield piece
                            except (json.JSONDecodeError, KeyError, IndexError):
                                continue
                    _usage["calls"] += 1
                    if usage_out is not None:
                        usage_out["tokens"] = max(1, total_chars // 2)
        except LLMError:
            raise
        except asyncio.CancelledError:
            log.info("LLM stream cancelled by client")
            raise
        except Exception as e:
            _usage["errors"] += 1
            err = _classify(e)
            _usage["last_error"] = str(err)
            raise err from e
