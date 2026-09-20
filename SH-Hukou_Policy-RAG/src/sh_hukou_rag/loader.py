"""读取 data/*.md 并解析 YAML front-matter。

修复了原实现的两个问题：
1. 原实现用非贪婪正则删 front-matter，一旦正文里出现 `---` 分隔线就会误删；
   这里改成"仅当文件以 --- 开头时"精确切分。
2. 原实现丢弃了 front-matter（文号、生效日期、状态），
   而 data_card.md 明确要求靠元数据做版本消歧，这里把元数据取回来。
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

FRONT_MATTER_RE = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n", re.DOTALL)
DOC_FILENAME_RE = re.compile(r"^(?P<seq>\d{2})_(?P<rest>.+)\.md$")


@dataclass
class Document:
    """一份政策文件。"""

    source: str                      # 文件名，作为溯源标识
    title: str                       # 正文一级标题（真正的文档名）
    body: str                        # 去掉 front-matter 的正文
    meta: dict[str, Any] = field(default_factory=dict)
    sha256: str = ""                 # 正文指纹，用于数据集溯源

    @property
    def doc_no(self) -> str:
        return str(self.meta.get("doc_no", ""))

    @property
    def status(self) -> str:
        return str(self.meta.get("status", "unknown"))

    @property
    def effective_date(self) -> str:
        return str(self.meta.get("effective_date", ""))

    @property
    def seq(self) -> str:
        m = DOC_FILENAME_RE.match(self.source)
        return m.group("seq") if m else ""


def _parse_front_matter(raw: str) -> tuple[dict[str, Any], str]:
    """返回 (元数据, 正文)。没有 front-matter 时元数据为空字典。"""
    m = FRONT_MATTER_RE.match(raw)
    if not m:
        return {}, raw
    try:
        meta = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        meta = {}
    if not isinstance(meta, dict):
        meta = {}
    return meta, raw[m.end():]


def _document_title(body: str, fallback: str) -> str:
    """取正文中第一个一级标题作为文档名，没有就用文件名兜底。"""
    m = re.search(r"^#\s+(.+)$", body, flags=re.MULTILINE)
    return m.group(1).strip() if m else fallback


def load_docs(path: str | Path | None = None) -> list[Document]:
    """加载目录下所有 `NN_*.md` 文件，按文件名排序。"""
    from .config import DATA_DIR

    directory = Path(path) if path is not None else DATA_DIR
    if not directory.is_dir():
        raise FileNotFoundError(f"数据目录不存在：{directory}")

    docs: list[Document] = []
    for f in sorted(directory.glob("*.md")):
        if not DOC_FILENAME_RE.match(f.name):
            continue  # 跳过 README 等非编号文件
        raw = f.read_text(encoding="utf-8")
        meta, body = _parse_front_matter(raw)
        docs.append(
            Document(
                source=f.name,
                title=_document_title(body, fallback=f.stem),
                body=body,
                meta=meta,
                sha256=hashlib.sha256(body.encode("utf-8")).hexdigest()[:16],
            )
        )
    return docs
