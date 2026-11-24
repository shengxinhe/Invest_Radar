# -*- coding: utf-8 -*-
"""
单用户模式 · 数据归属上下文

历史上这里用 contextvar 支撑多用户隔离（M8）。现在改为个人单用户：
所有数据固定归属 uid=1（OWNER_UID），不再有登录与会话。

保留 set_uid/reset 接口以兼容后台任务的调用形式；显式传 uid 的调用
也仍然有效。若未来要恢复多用户，从 git 历史恢复 server/identity.py
与 migrations/007_multiuser.py 即可。
"""
import contextvars

OWNER_UID = 1

_uid: contextvars.ContextVar[int] = contextvars.ContextVar("radar_uid", default=OWNER_UID)


def set_uid(uid: int):
    """返回 token，用于 finally 里 reset。单用户模式下一般不需要调用。"""
    return _uid.set(int(uid))


def reset(token):
    try:
        _uid.reset(token)
    except Exception:
        pass


def current_uid() -> int:
    return _uid.get()
