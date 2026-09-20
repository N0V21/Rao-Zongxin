"""命令行交互问答：python -m sh_hukou_rag.cli"""

from __future__ import annotations

import time

from .config import TOP_K
from .pipeline import RagPipeline


def main() -> None:
    print("加载模型与文档 ...")
    t0 = time.time()
    pipeline = RagPipeline.from_disk()
    stats = pipeline.stats()
    print(f"文档 {stats['n_docs']} 份 / 条款 {stats['n_articles']} 条 / "
          f"前言 {stats['n_preamble']} 条 / 索引 {stats['matrix_shape']} "
          f"（{time.time() - t0:.1f}s）")
    print("输入问题回车提问，直接回车退出。\n")

    while True:
        try:
            query = input("问：").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not query:
            break

        t0 = time.time()
        result = pipeline.ask(query)
        print(f"\n=== 召回 TOP-{min(TOP_K, len(result.hits))} ===")
        for h in result.hits:
            mark = "" if h.chunk.is_article else "（前言）"
            print(f"  {h.rank:>2}. {h.score:.3f}  {h.chunk.source}  "
                  f"→ {h.title}{mark}")
        print(f"\n=== 答案 ===\n{result.answer or '（模型返回空内容）'}")
        if result.empty_answer:
            print(f"⚠️  模型返回空内容"
                  f"{'（finish_reason=length，建议调大 LLM_MAX_TOKENS）' if result.truncated else ''}")
        print(f"\n[拒答={result.refused}"
              f"{'/' + result.refusal_reason if result.refusal_reason else ''}] "
              f"耗时 {time.time() - t0:.1f}s | "
              f"tokens {result.prompt_tokens}/{result.completion_tokens}")


if __name__ == "__main__":
    main()
