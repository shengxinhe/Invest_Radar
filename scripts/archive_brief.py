from pathlib import Path

p = Path("server/main.py")
t = p.read_text(encoding="utf-8")

# 晨报归档到 research_report（保留旧的 out/ 文件写入）
old = '''        try:
            ts = datetime.now().strftime("%Y%m%d")
            (config.OUT_DIR / f"daily_{ts}.md").write_text("".join(buf), encoding="utf-8")
        except Exception:
            pass
        yield sse.ev_done()'''
new = '''        content = "".join(buf)
        try:
            ts = datetime.now().strftime("%Y%m%d")
            (config.OUT_DIR / f"daily_{ts}.md").write_text(content, encoding="utf-8")
        except Exception:
            pass
        try:
            store.save_report(kind="daily_brief", code="",
                              title=f"晨报 {datetime.now().strftime('%Y-%m-%d')}",
                              content=content,
                              meta=json.dumps({"model": llm.MODEL_CHEAP},
                                              ensure_ascii=False))
        except Exception:
            pass
        yield sse.ev_done()'''
assert old in t, "daily brief archive block not found"
t = t.replace(old, new)
p.write_text(t, encoding="utf-8")
print("daily brief now archives to research_report")
