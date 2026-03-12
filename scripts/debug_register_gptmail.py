#!/usr/bin/env python3
"""
兼容入口：GPTMail 调试脚本。

已迁移到更通用脚本：
    scripts/debug_register_mail.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main() -> int:
    script_path = Path(__file__).with_name("debug_register_mail.py")
    cmd = [sys.executable, str(script_path), "--mail-provider", "gptmail", *sys.argv[1:]]
    return subprocess.call(cmd)


if __name__ == "__main__":
    raise SystemExit(main())
