"""检索：多查询变体打分 + 邻条上下文扩展。

相对原实现的改动：
- 编码只做一次（见 embeddings.build_index），不再每问重算；
- 改写变体真正生效，按 chunk 取最高分（max-pool），并记录命中变体；
- 上下文窗口按"条款序"扩展，而不是靠 `articles[idx±1]` 拼字符串——
  原实现把相邻条款拼进 context 后，TOP-10 命中相邻条目时 prompt 里
  会出现大段重复文本，白烧 token（baseline 第 3 题 5407 tokens 即此因）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np

from .chunker import Chunk
from .config import (CONTEXT_WINDOW, SCORE_THRESHOLD, TOP_K, VARIANT_WEIGHT)
from .embeddings import Embedder, encode_texts
from .rewrite import rewrite


@dataclass
class Hit:
    rank: int
    score: float
    chunk: Chunk
    matched_query: str
    context: str

    # 便于评测脚本沿用旧字段名
    @property
    def source(self) -> str:
        return self.chunk.source

    @property
    def title(self) -> str:
        return self.chunk.title

    @property
    def key(self) -> tuple[str, int]:
        return self.chunk.key

    def to_dict(self) -> dict:
        return {"rank": self.rank, "score": round(self.score, 4),
                "matched_query": self.matched_query, **self.chunk.to_dict()}


def search(
    chunks: Sequence[Chunk],
    query: str,
    embedder: Embedder,
    matrix: np.ndarray | None = None,
    *,
    k: int = TOP_K,
    context_window: int = CONTEXT_WINDOW,
    include_preamble: bool = False,
) -> list[Hit]:
    """返回 TOP-k 命中。matrix 为预计算的 chunk 向量矩阵。"""
    pool = [c for c in chunks if include_preamble or c.is_article]
    if not pool:
        return []
    if matrix is None:
        matrix = encode_texts(embedder, [c.search_text for c in pool])
    elif len(matrix) == len(chunks) and len(pool) != len(chunks):
        # 索引是按全部 chunk 建的，这里要同步筛掉前言行，保持行序对齐
        keep = [i for i, c in enumerate(chunks) if include_preamble or c.is_article]
        matrix = matrix[keep]

    variants = rewrite(query)
    qmat = encode_texts(embedder, variants.items)    # (V, D)

    # 原查询权重 1.0，改写变体打折扣：变体只做补充，不能反客为主。
    weights = np.ones(len(qmat), dtype=np.float32)
    weights[1:] = VARIANT_WEIGHT
    sims = (matrix @ qmat.T) * weights[None, :]      # (N, V)
    best = sims.max(axis=1)                          # 每个 chunk 取最高分
    best_variant = sims.argmax(axis=1)

    order = np.argsort(best)[::-1]
    hits: list[Hit] = []
    for i in order:
        if best[i] < 0:      # 负相似度不可能是有用召回
            continue
        chunk = pool[int(i)]
        hits.append(Hit(
            rank=len(hits) + 1,
            score=float(best[i]),
            chunk=chunk,
            matched_query=variants.items[int(best_variant[i])],
            context=_build_context(pool, chunk, context_window),
        ))
        if len(hits) >= k:
            break

    if context_window > 0:
        _dedupe_across_hits(pool, hits, context_window)
    return hits


def _articles_of(pool: Sequence[Chunk], source: str) -> list[Chunk]:
    """取某一份文件内的条款，按 offset 升序（split_document 的顺序即如此）。"""
    return sorted((c for c in pool if c.source == source and c.offset >= 0),
                  key=lambda c: c.offset)


def _build_context(pool: Sequence[Chunk], chunk: Chunk, window: int) -> str:
    """把**同一份文件内**相邻条款拼成上下文，条款只出现一次。

    注意：窗口必须在本文件内部计算。早期实现用跨文件的全量下标算窗口，
    导致 01 号文的命中会带出 02 号文的条款（两份文件都有"第五条"），
    既误导模型，也让"出处"标注失效。
    """
    if window <= 0:
        return f"{chunk.title}\n{chunk.content}".strip()
    siblings = _articles_of(pool, chunk.source)
    pos = next((i for i, c in enumerate(siblings) if c is chunk), None)
    if pos is None:
        return f"{chunk.title}\n{chunk.content}".strip()
    lo = max(0, pos - window)
    hi = min(len(siblings), pos + window + 1)
    return "\n\n".join(f"{c.title}\n{c.content}".strip()
                       for c in siblings[lo:hi])


def _dedupe_across_hits(pool: Sequence[Chunk], hits: list[Hit], window: int) -> None:
    """合并命中之间重叠的上下文区间，避免同一段条款在 prompt 里反复出现。

    TOP-k 命中同一文档的相邻条款时，各自的窗口会大幅重叠
    （10 条命中 × 3 条窗口 ≈ 30 段，去重后通常只剩十几段）。
    做法是把重叠窗口合并成区间，每个区间只在**第一次出现**的命中里渲染，
    其余命中的 context 换成一行指针，指回已经渲染过的编号。

    所有区间都以 (source, offset) 为坐标，**每份文件独立处理**，
    绝不跨文档拼接。
    """
    for source in {h.chunk.source for h in hits}:
        siblings = _articles_of(pool, source)
        if not siblings:
            continue
        pos_of = {id(c): i for i, c in enumerate(siblings)}
        doc_hits = [h for h in hits if h.chunk.source == source]

        # 已渲染的区间：[lo, hi, owner_rank]
        claimed: list[list] = []

        for hit in doc_hits:
            pos = pos_of.get(id(hit.chunk))
            if pos is None:
                continue

            # 命中条款本身已被别的区间渲染过 → 直接给指针，不再重复展开
            covering = next((r for r in claimed if r[0] <= pos < r[1]), None)
            if covering is not None:
                _point_to(hit, covering[2])
                continue

            lo = max(0, pos - window)
            hi = min(len(siblings), pos + window + 1)
            owner = hit.rank

            # 归并所有相交区间：只"向外扩张"，取最左 owner
            changed = True
            while changed:
                changed = False
                for rng in list(claimed):
                    if rng[0] < hi and lo < rng[1]:
                        lo, hi = min(lo, rng[0]), max(hi, rng[1])
                        owner = min(owner, rng[2])
                        claimed.remove(rng)
                        changed = True

            # 扩张了别人的区间 → 仍由原 owner 渲染，本条件只给指针，
            # 否则同一段条款会被渲染两次
            if owner != hit.rank:
                _point_to(hit, owner)
                continue

            claimed.append([lo, hi, owner])
            hit.context = "\n\n".join(
                f"{siblings[i].title}\n{siblings[i].content}".strip()
                for i in range(lo, hi)
            )


def _point_to(hit: Hit, owner_rank: int) -> None:
    hit.context = (f"（本条上下文已并入第 {owner_rank} 条，"
                   f"避免重复：{hit.chunk.title}）")


def is_low_confidence(hits: Sequence[Hit], threshold: float = SCORE_THRESHOLD) -> bool:
    """最高分低于阈值 → 视为召回不可靠。

    注意：这是启发式兜底，不是可靠闸门；真正的拒答由 prompt + 复核完成。
    """
    return not hits or hits[0].score < threshold
