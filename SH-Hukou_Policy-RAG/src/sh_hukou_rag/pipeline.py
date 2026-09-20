"""端到端问答入口：加载 → 切分 → 建索引 → 检索 → 生成。"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .chunker import Chunk, split_by_article
from .config import TOP_K
from .embeddings import Embedder, build_index, get_encoder
from .generator import Generation, build_prompt, llm_ask, refuse
from .loader import Document, load_docs
from .retriever import Hit, is_low_confidence, search


@dataclass
class Answer:
    query: str
    answer: str
    hits: list[Hit] = field(default_factory=list)
    prompt_tokens: int = 0
    completion_tokens: int = 0
    refused: bool = False
    refusal_reason: str = ""
    empty_answer: bool = False
    truncated: bool = False

    @property
    def top1_source(self) -> str | None:
        return self.hits[0].source if self.hits else None

    @property
    def top1_score(self) -> float | None:
        return round(self.hits[0].score, 4) if self.hits else None


class RagPipeline:
    """一次构建，多次问答。"""

    def __init__(self, chunks: list[Chunk], embedder: Embedder,
                 matrix, *, top_k: int = TOP_K) -> None:
        self.chunks = chunks
        self.embedder = embedder
        self.matrix = matrix
        self.top_k = top_k

    # ---------- 构建 ----------
    @classmethod
    def from_disk(cls, data_dir: str | Path | None = None, *,
                  embedder: Embedder | None = None,
                  top_k: int = TOP_K,
                  use_cache: bool = True) -> "RagPipeline":
        docs: list[Document] = load_docs(data_dir)
        chunks = split_by_article(docs)
        embedder = embedder or get_encoder()
        if use_cache:
            matrix = build_index(embedder, chunks)
        else:
            from .embeddings import encode_texts
            matrix = encode_texts(embedder, [c.search_text for c in chunks])
        return cls(chunks, embedder, matrix, top_k=top_k)

    # ---------- 问答 ----------
    def retrieve(self, query: str, k: int | None = None) -> list[Hit]:
        return search(self.chunks, query, self.embedder, self.matrix,
                      k=k or self.top_k)

    def ask(self, query: str, *, k: int | None = None) -> Answer:
        hits = self.retrieve(query, k=k)
        if is_low_confidence(hits):
            gen = refuse("召回得分低于阈值")
            return Answer(query, gen.answer, hits, gen.prompt_tokens,
                          gen.completion_tokens, gen.refused,
                          "low_score")
        gen: Generation = llm_ask(build_prompt(query, hits))
        reason = ""
        if gen.empty:
            reason = "empty_response_truncated" if gen.truncated else "empty_response"
        elif gen.refused:
            reason = "llm_refused"
        return Answer(query, gen.answer, hits, gen.prompt_tokens,
                      gen.completion_tokens, gen.refused, reason,
                      gen.empty, gen.truncated)

    def stats(self) -> dict:
        articles = [c for c in self.chunks if c.is_article]
        return {
            "n_chunks": len(self.chunks),
            "n_articles": len(articles),
            "n_preamble": len(self.chunks) - len(articles),
            "n_docs": len({c.source for c in self.chunks}),
            "n_chars": sum(len(c.search_text) for c in self.chunks),
            "matrix_shape": tuple(self.matrix.shape),
        }
