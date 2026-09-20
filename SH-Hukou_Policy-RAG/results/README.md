# 评测输出

本目录存放 `eval/run_eval.py` 的产物。

| 文件 | 说明 |
|---|---|
| `baseline_v0.legacy-v0.3.jsonl` | **修复前**（v0.3 原代码）在 2026-09-20 跑出的评测结果，保留作对照。注意：当时 10 题里 4 题的 `answer` 为空字符串，却被记为 `hit`。 |
| `baseline_v0.jsonl` | 修复后重新跑出的结果。运行 `python eval/run_eval.py` 生成（需要配置 `LLM_API_KEY`）。 |

重新生成：

```bash
python eval/run_eval.py
```

每条记录包含 `verdict`、`hit@3`、`refused`、`empty_answer`、`truncated`、
`tokens`、`latency`、`answer`、`top1_source`、`top1_score`、`top3`。
文件首行是 `_meta`，含模型名、`TOP_K`、阈值与数据集指纹，便于跨版本对比。
