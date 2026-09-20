"""回归测试：覆盖原代码里被修复的缺陷，防止再次退化。

运行：pytest -q
"""

from __future__ import annotations

import numpy as np
import pytest

from sh_hukou_rag.chunker import split_by_article, split_document
from sh_hukou_rag.config import REFUSAL_TEXT
from sh_hukou_rag.loader import load_docs
from sh_hukou_rag.pipeline import RagPipeline
from sh_hukou_rag.retriever import is_low_confidence, search
from sh_hukou_rag.rewrite import rewrite

from fake_embedder import HashingEmbedder


@pytest.fixture(scope="module")
def docs():
    return load_docs()


@pytest.fixture(scope="module")
def chunks(docs):
    return split_by_article(docs)


@pytest.fixture(scope="module")
def embedder():
    return HashingEmbedder()


@pytest.fixture(scope="module")
def pipeline(chunks, embedder):
    from sh_hukou_rag.embeddings import encode_texts

    matrix = encode_texts(embedder, [c.search_text for c in chunks])
    return RagPipeline(chunks, embedder, matrix)


# ---------------- loader ----------------

def test_loads_four_documents(docs):
    assert len(docs) == 4
    assert [d.seq for d in docs] == ["01", "02", "03", "04"]


def test_front_matter_parsed(docs):
    """元数据必须可用（data_card 要求靠 effective_date 做版本消歧）。"""
    assert all(d.doc_no for d in docs)
    assert all(d.effective_date for d in docs)
    assert all(d.status == "effective" for d in docs)
    assert all(d.sha256 for d in docs)


def test_front_matter_removed_from_body(docs):
    for d in docs:
        assert not d.body.startswith("---")
        assert "superseded_by" not in d.body


def test_document_title_taken_from_body(docs):
    """文档名应取正文 H1，而不是文件名。"""
    by_seq = {d.seq: d for d in docs}
    assert "引进人才" in by_seq["01"].title
    assert by_seq["04"].title.startswith("留学回国人员")


# ---------------- chunker ----------------

def test_h1_title_reaches_every_article_chunk(chunks):
    """核心回归：原实现把首个 H1 丢掉，导致 40/53 个 chunk 检索文本不含文档名。"""
    for c in chunks:
        if c.is_article:
            assert c.doc_title in c.search_text, c
            assert "##" not in c.search_text.split("\n")[0]


def test_preamble_flagged_not_article(chunks):
    """印发通知/前言必须被标记，不能当成条款参与检索。"""
    preamble = [c for c in chunks if not c.is_article]
    assert preamble, "应至少识别出 01 号文的印发通知"
    assert all(c.offset == -1 for c in preamble)


def test_preamble_excluded_by_default(chunks, embedder):
    hits = search(chunks, "现将文件印发给你们", embedder, k=5)
    assert all(h.chunk.is_article for h in hits)


def test_article_count_matches_headings(docs, chunks):
    expected = sum(len([l for l in d.body.splitlines() if l.startswith("## ")])
                   for d in docs)
    assert len([c for c in chunks if c.is_article]) == expected


def test_offsets_unique_per_document(chunks):
    keys = [c.key for c in chunks if c.is_article]
    assert len(keys) == len(set(keys))


def test_split_document_is_pure(docs):
    """切分不应修改输入文档。"""
    before = docs[0].body
    split_document(docs[0])
    assert docs[0].body == before


# ---------------- rewrite ----------------

def test_rewrite_returns_original_first():
    variants = rewrite("居转户需要满几年？")
    assert variants.items[0] == "居转户需要满几年？"
    assert len(variants) > 1


def test_rewrite_no_crash_on_plain_query():
    """原实现这里的 _REWRITE_RULES 会直接 NameError。"""
    variants = rewrite("留学回国人员落户")
    assert variants.items == ["留学回国人员落户"]


def test_rewrite_does_not_inject_whole_document_name():
    """回归：把文档全名当独立查询注入会污染排序（曾让无关条款拿到 0.91）。"""
    variants = rewrite("居转户需要持证和缴纳社保满几年？")
    assert "持有《上海市居住证》人员申办本市常住户口" not in variants.items
    assert all(len(v) < 40 for v in variants.items)


def test_rewrite_injects_keywords():
    joined = " ".join(rewrite("配偶和子女能随迁吗？").items)
    assert "家属随迁" in joined


def test_rewrite_variants_are_deduped():
    variants = rewrite("居转户满几年")
    assert len(variants.items) == len(set(variants.items))


def test_rewrite_is_bounded():
    variants = rewrite("居转户 配偶 子女 满几年 公示期 个人提交 还有效吗")
    assert len(variants.items) <= 6


# ---------------- retriever ----------------

def test_search_respects_k(chunks, embedder):
    assert len(search(chunks, "落户条件", embedder, k=3)) == 3


def test_search_scores_are_descending(chunks, embedder):
    scores = [h.score for h in search(chunks, "社保 年限", embedder, k=8)]
    assert scores == sorted(scores, reverse=True)


def test_context_has_no_duplicated_article(chunks, embedder):
    """相邻条款拼上下文时，条款本身不能重复出现。"""
    for hit in search(chunks, "随迁", embedder, k=5):
        assert hit.context.count(hit.chunk.title) == 1


def test_context_never_spans_documents(chunks, embedder):
    """上下文窗口绝不能跨文件拼接。

    注意：01 号文和 02 号文都有"第五条（申办条件）"这类同名标题，
    所以不能靠标题字符串判断，必须拿"本文件条款的完整行集合"来比对。
    """
    from sh_hukou_rag.chunker import split_document
    from sh_hukou_rag.loader import load_docs

    docs = {d.source: d for d in load_docs()}
    hits = search(chunks, "落户条件 社保 年限", embedder, k=10)

    for hit in hits:
        own = split_document(docs[hit.chunk.source])
        own_lines = {l.strip() for c in own for l in c.content.split("\n") if l.strip()}
        own_titles = {c.title for c in own}
        for line in hit.context.split("\n"):
            line = line.strip()
            if line and line not in own_lines and line not in own_titles \
                    and not line.startswith("（本条上下文"):
                raise AssertionError(
                    f"{hit.chunk.source} 上下文混入外来内容：{line[:40]!r}")


def test_context_is_exactly_a_within_document_window(chunks, embedder):
    """上下文内容必须等于"本文件内"某个连续条款区间，且不含别家条款。"""
    hits = search(chunks, "居转户 条件 材料", embedder, k=10)
    for hit in hits:
        if hit.context.startswith("（本条上下文"):
            continue
        own = [c for c in chunks
               if c.source == hit.chunk.source and c.is_article]
        own.sort(key=lambda c: c.offset)
        lines = hit.context.split("\n")
        # 每个窗口都是 own 里某段连续子序列的渲染结果
        matched = False
        for start in range(len(own)):
            for end in range(start + 1, len(own) + 1):
                piece = "\n\n".join(f"{c.title}\n{c.content}".strip()
                                    for c in own[start:end])
                if piece == hit.context:
                    matched = True
                    break
            if matched:
                break
        assert matched, f"上下文不是本文件的连续窗口：{lines[:2]}"


def test_overlapping_windows_are_merged(chunks, embedder):
    """重叠窗口应合并：命中条目之间不重复渲染同一段条款。"""
    hits = search(chunks, "居转户 持证 社保 年限 条件", embedder, k=10)
    titles = [c.title for c in chunks if c.is_article]
    max_renders = 0
    for t in titles:
        n = sum(1 for h in hits if t in h.context.split("\n"))
        max_renders = max(max_renders, n)
    # 不去重时一个条款可被 10 个窗口各带一次；合并后不应超过 2 次
    # （2 = 恰好被两个不相邻的命中区间各覆盖一次）
    assert max_renders <= 2, f"条款被重复渲染 {max_renders} 次"
    # 被并入的条目要有指针，说明确实发生了合并
    assert any(h.context.startswith("（本条上下文已并入") for h in hits)


def test_context_window_zero_gives_single_article(chunks, embedder):
    hits = search(chunks, "随迁", embedder, k=3, context_window=0)
    for h in hits:
        assert h.context.startswith(h.chunk.title)


def test_variant_weight_keeps_original_authoritative():
    """回归：改写变体不得反客为主。

    原实现把"居转户"扩展成 02 号文全名后独立检索，使无关条款拿到 0.91；
    变体必须打折，否则会污染排序。
    """
    from sh_hukou_rag.config import VARIANT_WEIGHT

    assert 0 < VARIANT_WEIGHT < 1, "变体权重必须小于 1"


def test_only_one_preamble_chunk_expected(chunks):
    """01 号文的印发通知应被识别为前言，不参与检索。"""
    preamble = [c for c in chunks if not c.is_article]
    assert all(c.title == "〔印发通知/前言〕" for c in preamble)


def test_low_confidence_gate(chunks, embedder):
    hits = search(chunks, "完全无关的外星人问题", embedder, k=3)
    assert isinstance(is_low_confidence(hits, threshold=0.99), bool)
    assert is_low_confidence([], threshold=0.0) is True


# ---------------- pipeline ----------------

def test_stats_consistent(pipeline):
    stats = pipeline.stats()
    assert stats["n_docs"] == 4
    assert stats["n_chunks"] == stats["n_articles"] + stats["n_preamble"]
    assert stats["matrix_shape"][0] == stats["n_chunks"]


def test_ask_refuses_without_llm_when_score_low(pipeline, monkeypatch):
    """低分时应本地拒答，不调用 LLM（也就不会因为缺 API Key 报错）。"""
    monkeypatch.setattr("sh_hukou_rag.pipeline.is_low_confidence",
                        lambda hits, threshold=None: True)
    result = pipeline.ask("上海公积金贷款额度最高是多少？")
    assert result.refused
    assert REFUSAL_TEXT in result.answer
    assert result.prompt_tokens == 0


def test_prompt_contains_citation_labels(chunks, embedder):
    from sh_hukou_rag.generator import build_prompt

    hits = search(chunks, "随迁条件", embedder, k=3)
    prompt = build_prompt("配偶和子女能随迁吗？", hits)
    assert hits[0].chunk.citation in prompt
    assert "配偶和子女能随迁吗？" in prompt
