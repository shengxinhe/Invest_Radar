# -*- coding: utf-8 -*-
"""
M2 · SSE 服务端统一协议
事件类型：start / chunk / segment / progress / warning / error / done
所有流式接口必须经此模块输出，保证前端一个解析器吃全部。
"""
import json

# ---- 事件构造 ----

def ev_start(**kw):
    return _pack("start", **kw)


def ev_chunk(text):
    return _pack("chunk", text=text)


def ev_segment(key, label, text):
    return _pack("segment", key=key, label=label, text=text)


def ev_progress(stage, percent=None, detail=""):
    return _pack("progress", stage=stage, percent=percent, detail=detail)


def ev_warning(msg):
    return _pack("warning", msg=msg)


def ev_error(msg, kind="unknown"):
    return _pack("error", msg=str(msg)[:300], kind=kind)


def ev_done(**kw):
    return _pack("done", **kw)


def _pack(t, **kw):
    payload = {"type": t}
    payload.update(kw)
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "X-Accel-Buffering": "no",
    "Connection": "keep-alive",
}


# ---- 段落解析（把 LLM 自由文本切成结构化段）----

def split_segments(full_text, specs):
    """
    specs: [(匹配前缀, key, label), ...] 按出现顺序切分
    返回 [(key, label, text), ...]
    """
    import re
    marks = []
    for pat, key, label in specs:
        m = re.search(re.escape(pat), full_text)
        if m:
            marks.append((m.start(), key, label, pat))
    marks.sort(key=lambda x: x[0])

    out = []
    for i, (pos, key, label, pat) in enumerate(marks):
        end = marks[i + 1][0] if i + 1 < len(marks) else len(full_text)
        body = full_text[pos:end]
        body = body.replace(pat, "", 1)
        # 清掉可能的 markdown 装饰与残留编号
        body = body.strip(" \t\n:：*·-—")
        body = re.sub(r"^\d+[.、]\s*", "", body)
        if body:
            out.append((key, label, body))
    return out
