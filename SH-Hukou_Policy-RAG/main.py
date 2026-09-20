"""兼容旧入口：python main.py 仍可交互问答。

真正的实现已拆分到 src/sh_hukou_rag/ 下，这里只做转发。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from sh_hukou_rag.cli import main  # noqa: E402

if __name__ == "__main__":
    main()
