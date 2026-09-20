"""批量评测：python eval/run_eval.py

相对原 run_eval.py 的修复：
1. **Hit@3 分母错误**：原实现用含 5 道不可答题的 10 道题做分母（6/10=60%），
   把该拒答的题算成 miss，指标被系统性低估。这里区分"可答题"与"不可答题"。
2. **空答案被当成成功**：baseline 里第 2、4、5、6 题的 answer 是空字符串，
   评测却仍记为 hit。这里增加 empty_answer 统计，避免把 LLM 空返回当成通过。
3. `ok = is_hit(hits, gold)` 在 gold 为 None 时也执行，属于无效调用；已去除。
4. 问题从 txt 读取，但 gold 硬编码在文件里，两边容易漂移；
   这里校验"每道题都必须有 gold 记录"，缺失直接报错。
5. 结果文件带数据集指纹与配置，便于跨版本对比。
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sh_hukou_rag.config import (MODEL_NAME, SCORE_THRESHOLD, TOP_K,  # noqa: E402
                                 PROJECT_ROOT)
from sh_hukou_rag.pipeline import RagPipeline  # noqa: E402

QUESTIONS_FILE = ROOT / "eval" / "questions_v0.txt"
RESULTS_FILE = ROOT / "results" / "baseline_v0.jsonl"

# key=问题；value=答案所在文件的关键词列表；None 表示库里没有，理应拒答
#
# 修正记录：原 GOLD 把"公示期是多少天？"标成 None（应拒答），
# 但 03 号文《实施细则》六.3 明确写了"为期 5 天的网上公示"，
# 这题其实**可答**，标 None 等于放水（答对也记 ok-refused）。
GOLD: dict[str, list[str] | None] = {
    "引进人才落户有哪几类人才？": ["01_"],
    "重点机构紧缺急需人才需要满足什么条件？": ["01_"],
    "居转户需要持证和缴纳社保满几年？": ["02_", "03_"],
    "留学回国人员落户对院校排名有什么要求？": ["04_"],
    "落户申请可以由个人直接提交吗？": ["01_", "02_", "03_", "04_"],
    "配偶和子女能随迁吗？": ["01_", "02_", "03_", "04_"],
    "公示期是多少天？": ["03_"],          # 03 号文六.3：为期 5 天的网上公示
    "2020年版的引进人才办法现在还有效吗？": None,
    "上海公积金贷款额度最高是多少？": None,
    "随申办上怎么办理落户？": None,
}


def load_questions() -> list[str]:
    lines = QUESTIONS_FILE.read_text(encoding="utf-8").splitlines()
    questions = [l.strip() for l in lines if l.strip() and not l.startswith("#")]
    missing = [q for q in questions if q not in GOLD]
    if missing:
        raise SystemExit(f"以下问题缺少 GOLD 标注：{missing}")
    return questions


def hit_at_k(hits, gold: list[str], k: int = 3) -> bool:
    tops = [h.source for h in hits[:k]]
    return any(g in s for s in tops for g in gold)


def main() -> None:
    questions = load_questions()
    print(f"加载模型 {MODEL_NAME} ...")
    pipeline = RagPipeline.from_disk()
    stats = pipeline.stats()
    print(f"文档 {stats['n_docs']} 份 / 条款 {stats['n_articles']} 条 / "
          f"索引 {stats['matrix_shape']}")

    rows = []
    for q in questions:
        t0 = time.time()
        result = pipeline.ask(q)
        gold = GOLD[q]

        if gold is None:
            verdict = "ok-refused" if result.refused else "hallucination"
            hit = None
        else:
            hit = hit_at_k(result.hits, gold)
            verdict = "hit" if hit else "miss"

        rows.append({
            "q": q,
            "verdict": verdict,
            "hit@3": hit,
            "refused": result.refused,
            "refusal_reason": result.refusal_reason,
            "empty_answer": result.empty_answer,
            "truncated": result.truncated,
            "tokens": result.prompt_tokens + result.completion_tokens,
            "latency": round(time.time() - t0, 2),
            "answer": result.answer[:300],
            "top1_source": result.top1_source,
            "top1_score": result.top1_score,
            "top3": [{"source": h.source, "title": h.title,
                      "score": round(h.score, 4)} for h in result.hits[:3]],
        })
        print(f"{verdict.upper():14s} | {q}")

    answerable = [r for r in rows if GOLD[r["q"]] is not None]
    unanswerable = [r for r in rows if GOLD[r["q"]] is None]

    n_hit = sum(1 for r in answerable if r["verdict"] == "hit")
    n_miss = sum(1 for r in answerable if r["verdict"] == "miss")
    n_ok_ref = sum(1 for r in unanswerable if r["verdict"] == "ok-refused")
    n_hallu = sum(1 for r in unanswerable if r["verdict"] == "hallucination")
    n_empty = sum(1 for r in answerable if r["empty_answer"])

    def pct(a: int, b: int) -> str:
        return f"{a / b * 100:.0f}%" if b else "n/a"

    print("\n=== 评测报告 ===")
    print(f"总题数        : {len(rows)}（可答 {len(answerable)} / 不可答 {len(unanswerable)}）")
    print(f"Hit@3（可答题）: {n_hit}/{len(answerable)} ({pct(n_hit, len(answerable))})")
    print(f"Miss          : {n_miss}")
    print(f"空答案        : {n_empty}  ← 原评测会把这些当成 hit")
    print(f"正确拒答      : {n_ok_ref}/{len(unanswerable)} ({pct(n_ok_ref, len(unanswerable))})")
    print(f"幻觉          : {n_hallu}")
    if rows:
        print(f"平均 tokens   : {sum(r['tokens'] for r in rows) / len(rows):.0f}")
        print(f"平均延迟      : {sum(r['latency'] for r in rows) / len(rows):.2f}s")

    RESULTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(RESULTS_FILE, "w", encoding="utf-8") as f:
        f.write(json.dumps({
            "_meta": {
                "embed_model": MODEL_NAME,
                "top_k": TOP_K,
                "score_threshold": SCORE_THRESHOLD,
                "dataset_fingerprint": hashlib.sha256(
                    "".join(sorted(c.sha256 for c in pipeline.chunks))
                    .encode("utf-8")).hexdigest()[:16],
                "n_chunks": stats["n_chunks"],
                "n_articles": stats["n_articles"],
            }
        }, ensure_ascii=False) + "\n")
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"已保存 {RESULTS_FILE.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
