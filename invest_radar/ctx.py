# -*- coding: utf-8 -*-
"""
M8 · 请求级用户上下文

为什么要 contextvar
------------------
store 层有 20 多个私有函数需要 uid。若在每个路由里显式传，main.py 要改 60 处调用，
既易漏又易错（漏一处就是越权）。

做法：中间件在认证通过后 set 当前 uid；store 的公开函数若没收到 uid 参数，
自动从 contextvar 取。这样：
  · 路由代码几乎不用改
  · 后台任务（无请求上下文）落到默认 uid=1（房主），不会崩
  · 显式传 uid 时以显式为准（后台批处理用）

安全性：外部请求必经认证中间件，中间件不 set 就直接 401，
所以默认值 1 不会把某个访客的数据错认成房主。
"""
import contextvars

OWNER_UID = 1

_uid: contextvars.ContextVar[int] = contextvars.ContextVar("radar_uid", default=OWNER_UID)


def set_uid(uid: int):
    """返回 token，用于 finally 里 reset。"""
    return _uid.set(int(uid))


def reset(token):
    try:
        _uid.reset(token)
    except Exception:
        pass


def current_uid() -> int:
    return _uid.get()
