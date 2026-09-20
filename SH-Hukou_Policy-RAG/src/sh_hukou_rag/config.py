"""集中配置。所有可调参数都可以通过环境变量覆盖，方便复现评测。"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# 项目根目录：src/sh_hukou_rag/config.py -> src/sh_hukou_rag -> src -> 项目根
PROJECT_ROOT = Path(__file__).resolve().parents[2]

# 显式按项目根定位 .env，避免依赖调用方的 cwd
load_dotenv(PROJECT_ROOT / ".env")

DATA_DIR = Path(os.getenv("HK_DATA_DIR", PROJECT_ROOT / "data"))
CACHE_DIR = Path(os.getenv("HK_CACHE_DIR", PROJECT_ROOT / ".cache"))
RESULTS_DIR = Path(os.getenv("HK_RESULTS_DIR", PROJECT_ROOT / "results"))

# ---------- 检索 ----------
MODEL_NAME = os.getenv("HK_EMBED_MODEL", "BAAI/bge-small-zh-v1.5")
TOP_K = int(os.getenv("HK_TOP_K", "10"))

# 拒答阈值：**启发式兜底**，不是可靠的安全边界。
# bge-small-zh 的余弦相似度普遍落在 0.5~0.8，无关问题也常 >0.5，
# 因此真正的拒答主要依赖 prompt 约束 + REFUSE_MARKERS 复核。
SCORE_THRESHOLD = float(os.getenv("HK_SCORE_THRESHOLD", "0.5"))

# 改写变体的得分折扣：变体只是补充信号，不应压过原查询。
# 取 1.0 等于完全信任变体（已被证实会污染排序，见 rewrite.py 注释）。
VARIANT_WEIGHT = float(os.getenv("HK_VARIANT_WEIGHT", "0.9"))

# 邻条上下文窗口：1 = 命中条款左右各带一条。
# 重叠窗口会在 retriever._dedupe_across_hits 里合并，不会重复占 token。
CONTEXT_WINDOW = int(os.getenv("HK_CONTEXT_WINDOW", "1"))

# ---------- 生成 ----------
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.deepseek.com")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "deepseek-chat")
LLM_TIMEOUT = int(os.getenv("HK_LLM_TIMEOUT", "60"))
LLM_MAX_TOKENS = int(os.getenv("HK_LLM_MAX_TOKENS", "1024"))

REFUSAL_TEXT = "根据现有材料无法回答"
REFUSE_MARKERS = ("无法回答", "没有相关信息", "未提及", "材料中未提供", "无法确定")

PROMPT_TEMPLATE = """你是上海落户政策问答助手，只依据下方【参考材料】作答。

硬性规则：
1. 材料中未提及或信息不完整时，必须原样回答"{refusal}"，
   不得用常识、政策惯例或推测补全。
2. 不得把甲情形的规定套用到乙情形（如居转户的条款不能用来回答引进人才）。
3. 凡涉及"能不能/是否/由谁提交/几天/多少钱"的结论，材料中必须有明确依据，
   否则按第 1 条处理。
4. 末尾标注出处文件名与条款号（例：出处：02_持有〈上海市居住证〉人员申办本市常住户口办法 第五条）。

【参考材料】
{context}

【用户问题】
{query}"""


def require_llm_config() -> None:
    """在真正调用 LLM 前检查凭证，给出可读报错而不是 KeyError。"""
    if not LLM_API_KEY:
        raise RuntimeError(
            "缺少 LLM_API_KEY。请复制 .env.example 为 .env 并填入你的 API Key。"
        )
