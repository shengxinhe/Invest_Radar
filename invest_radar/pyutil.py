# -*- coding: utf-8 -*-
"""拼音工具：全拼 + 首字母"""

try:
    from pypinyin import lazy_pinyin
    _HAS = True
except ImportError:
    _HAS = False


def to_pinyin(text):
    """中金岭南 → 'zhongjinlingnan zjln'（全拼 + 首字母，空格分隔，都小写）"""
    if not text:
        return ""
    if not _HAS:
        return ""
    try:
        full = "".join(lazy_pinyin(text)).lower()
        initials = "".join([p[0] for p in lazy_pinyin(text) if p]).lower()
        return f"{full} {initials}"
    except Exception:
        return ""
