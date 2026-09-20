"""条款级切分。

修复了原实现的三个问题：
1. **H1 被静默丢弃**：原代码用 `re.split(r"(\\r?\\n##\\s+)", ...)` 只切 `##`，
   第一段（H1 + 通知前言）在遇到首个 `##` 时被 `buf = seg.lstrip()` 直接覆盖，
   导致 02/03/04 三份文件的文档名从未进入向量（53 个 chunk 里 40 个
   检索文本不含文档名），"居转户"这类简称因此只能靠文件名兜底。
   这里显式保留 H1，并把文档名拼进每个 chunk 的检索文本。
2. **通知前言被当成条款**：01 号文的印发通知（"现将……印发给你们"）
   被切成一个 chunk，会污染"由谁提交/怎么办理"这类问题的召回。
   这里标记 is_article=False，默认不参与检索。
3. **切分函数里塞了检索逻辑**：原实现同时构造 search_text 和 context，
   职责混乱。这里只产出结构化的 Chunk，拼装交给 retriever。
"""

from __future__ import annotations

import re

from .loader import Document

# 以 H1/H2 标题开头的行
HEADING_RE = re.compile(r"^(#{1,2})\s+(.+)$")

# 实施细则类文件用"一、二、三"，办法类文件用"第一条、第二条"
ARTICLE_NO_RE = re.compile(r"^(第[一二三四五六七八九十百零〇\d]+条|[一二三四五六七八九十]+、)")


class Chunk:
    """一个条款（或前言）chunk。"""

    __slots__ = ("source", "doc_title", "doc_no", "status", "effective_date",
                 "seq", "offset", "title", "content", "is_article", "sha256")

    def __init__(self, *, source: str, doc_title: str, doc_no: str, status: str,
                 effective_date: str, seq: str, offset: int, title: str,
                 content: str, is_article: bool, sha256: str = "") -> None:
        self.source = source
        self.doc_title = doc_title
        self.doc_no = doc_no
        self.status = status
        self.effective_date = effective_date
        self.seq = seq
        self.offset = offset
        self.title = title
        self.content = content
        self.is_article = is_article
        self.sha256 = sha256

    # ---- 检索文本：文档名 + 条款号 + 正文，避免语义漂移 ----
    @property
    def search_text(self) -> str:
        head = f"{self.doc_title} {self.title}".strip()
        return f"{head}\n{self.content}".strip()

    # ---- 引用标签，用于 prompt 与评测 ----
    @property
    def citation(self) -> str:
        return f"{self.source} {self.title}"

    # ---- 唯一键，用于去重 ----
    @property
    def key(self) -> tuple[str, int]:
        return (self.source, self.offset)

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "doc_title": self.doc_title,
            "doc_no": self.doc_no,
            "status": self.status,
            "effective_date": self.effective_date,
            "seq": self.seq,
            "offset": self.offset,
            "title": self.title,
            "is_article": self.is_article,
        }

    def __repr__(self) -> str:  # pragma: no cover - 调试用
        kind = "art" if self.is_article else "pre"
        return f"<Chunk {self.seq}/{kind}#{self.offset} {self.title[:16]!r}>"


def split_document(doc: Document) -> list[Chunk]:
    """把一份文档切成 chunk：H1 是文档标题，H2 是条款边界。"""
    lines = doc.body.split("\n")

    preamble: list[str] = []
    sections: list[tuple[str, list[str]]] = []
    current: tuple[str, list[str]] | None = None
    seen_h1 = False

    for line in lines:
        m = HEADING_RE.match(line)
        if m:
            level, text = m.group(1), m.group(2).strip()
            if level == "#":
                if not seen_h1:
                    seen_h1 = True      # 第一个 H1 就是文档名，不再计入正文
                    continue
                # 文档内后续的 H1（如 01 号文的"通知"标题）并入前言
                preamble.append(text)
                continue
            # level == "##"
            current = (text, [])
            sections.append(current)
            continue
        (current[1] if current else preamble).append(line)

    chunks: list[Chunk] = []

    preamble_text = "\n".join(preamble).strip()
    if preamble_text:
        chunks.append(Chunk(
            source=doc.source, doc_title=doc.title, doc_no=doc.doc_no,
            status=doc.status, effective_date=doc.effective_date, seq=doc.seq,
            offset=-1, title="〔印发通知/前言〕", content=preamble_text,
            is_article=False, sha256=doc.sha256,
        ))

    for idx, (title, body_lines) in enumerate(sections):
        content = "\n".join(body_lines).strip()
        chunks.append(Chunk(
            source=doc.source, doc_title=doc.title, doc_no=doc.doc_no,
            status=doc.status, effective_date=doc.effective_date, seq=doc.seq,
            offset=idx, title=title, content=content,
            is_article=bool(ARTICLE_NO_RE.match(title)),
            sha256=doc.sha256,
        ))
    return chunks


def split_by_article(docs: list[Document]) -> list[Chunk]:
    """兼容旧调用名：切分多份文档。"""
    chunks: list[Chunk] = []
    for d in docs:
        chunks.extend(split_document(d))
    return chunks
