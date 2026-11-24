# -*- coding: utf-8 -*-
"""
轻量版本化迁移框架
- migrations/001_xxx.py 形式，每个迁移一个 upgrade(conn)
- 已应用版本记录在 schema_migrations 表
- 幂等：已应用跳过；重复执行安全
- 红线：绝不 DROP/重建业务表，只 ALTER/CREATE 新对象
"""
import importlib.util
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from invest_radar import store

MIGRATIONS_DIR = Path(__file__).resolve().parent


def _ensure_meta(c):
    c.execute("""CREATE TABLE IF NOT EXISTS schema_migrations(
        version TEXT PRIMARY KEY,
        name TEXT,
        applied_at INTEGER
    )""")
    c.commit()


def applied_versions(c):
    _ensure_meta(c)
    return {r["version"] for r in c.execute("SELECT version FROM schema_migrations").fetchall()}


def _load_module(path: Path):
    spec = importlib.util.spec_from_file_location(f"mig_{path.stem}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def run_migrations(db_path=None, dry=False):
    """按文件名序执行未应用迁移。返回 (applied_now, skipped)"""
    store.init()   # 保证基础表存在
    c = store.conn()
    _ensure_meta(c)
    done = applied_versions(c)

    files = sorted(MIGRATIONS_DIR.glob("0*.py"))
    applied_now, skipped = [], []

    for f in files:
        if f.name == "__init__.py":
            continue
        version = f.stem.split("_", 1)[1] if "_" in f.stem else f.stem
        # 文件名格式 001_description.py → version=001_description
        key = f.stem
        if key in done:
            skipped.append(key)
            continue
        mod = _load_module(f)
        if dry:
            print(f"[dry] would apply: {key} ({getattr(mod, 'DESCRIPTION', '')})")
            continue
        print(f"applying: {key} ...")
        try:
            mod.upgrade(c)
            c.execute("INSERT INTO schema_migrations(version,name,applied_at) VALUES(?,?,strftime('%s','now'))",
                      (key, getattr(mod, "DESCRIPTION", "")))
            c.commit()
            applied_now.append(key)
            print(f"  ok")
        except Exception as e:
            c.rollback()
            print(f"  FAILED: {e}")
            raise

    return applied_now, skipped


def backup_before_migrate():
    """迁移前强制备份（带完整性校验）"""
    import shutil
    import sqlite3
    from datetime import datetime
    src = store.DB_PATH
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dst = src.parent / "backups" / f"radar_premigrate_{stamp}.db"
    dst.parent.mkdir(exist_ok=True)
    # checkpoint 后拷贝
    tmp = sqlite3.connect(str(src))
    tmp.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    integrity = tmp.execute("PRAGMA integrity_check").fetchone()[0]
    tmp.close()
    assert integrity == "ok", f"integrity not ok: {integrity}"
    shutil.copy2(src, dst)
    return dst


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--dry", action="store_true")
    a = p.parse_args()
    if not a.dry:
        print("pre-migrate backup:", backup_before_migrate())
    applied, skipped = run_migrations(dry=a.dry)
    print(f"applied: {applied}")
    print(f"skipped(已应用): {skipped}")
