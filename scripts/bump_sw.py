# -*- coding: utf-8 -*-
"""构建后处理：给 sw.js 注入版本号（每次构建必变，触发客户端 SW 更新）"""
import re
import sys
import time
from datetime import datetime
from pathlib import Path

BUILD_DIR = Path(__file__).resolve().parent.parent / "web_build"


def bump():
    sw = BUILD_DIR / "sw.js"
    if not sw.exists():
        print("sw.js not found"); sys.exit(1)
    version = "v" + datetime.now().strftime("%Y%m%d%H%M")
    text = sw.read_text(encoding="utf-8")
    new = re.sub(r'const VERSION = "[^"]*"', f'const VERSION = "{version}"', text)
    sw.write_text(new, encoding="utf-8")
    print(f"sw.js bumped -> {version}")


if __name__ == "__main__":
    bump()
