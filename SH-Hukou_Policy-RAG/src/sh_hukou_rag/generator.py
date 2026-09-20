"""调用 OpenAI 兼容的 chat/completions 接口生成答案。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import requests

from .config import (LLM_API_KEY, LLM_BASE_URL, LLM_MAX_TOKENS, LLM_MODEL,
                     LLM_TIMEOUT, PROMPT_TEMPLATE, REFUSAL_TEXT,
                     REFUSE_MARKERS, require_llm_config)
from .retriever import Hit


@dataclass
class Generation:
    answer: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    refused: bool = False
    empty: bool = False          # 接口返回了空 content
    truncated: bool = False      # finish_reason == "length"
    finish_reason: str = ""


def build_prompt(query: str, hits: Sequence[Hit]) -> str:
    if not hits:
        context = "（无可用材料）"
    else:
        context = "\n\n---\n\n".join(
            f"[{h.rank}] {h.chunk.citation}\n{h.context}" for h in hits
        )
    return PROMPT_TEMPLATE.format(context=context, query=query, refusal=REFUSAL_TEXT)


def llm_ask(prompt: str, *, session: requests.Session | None = None) -> Generation:
    require_llm_config()
    url = LLM_BASE_URL.rstrip("/") + "/chat/completions"
    payload = {
        "model": LLM_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
        "max_tokens": LLM_MAX_TOKENS,
    }
    http = session or requests
    resp = http.post(
        url,
        headers={"Authorization": f"Bearer {LLM_API_KEY}",
                 "Content-Type": "application/json"},
        json=payload,
        timeout=LLM_TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()
    choice = (data.get("choices") or [{}])[0]
    content = (choice.get("message") or {}).get("content") or ""
    finish_reason = str(choice.get("finish_reason") or "")
    usage = data.get("usage", {}) or {}

    # 空返回是真实存在的故障模式：max_tokens 偏小、或模型把预算全花在
    # 推理 token 上时，content 会是空字符串而 HTTP 仍是 200。
    # 原实现直接把它当成正常答案写进评测，导致"空答案记 hit"。
    return Generation(
        answer=content,
        prompt_tokens=int(usage.get("prompt_tokens", 0)),
        completion_tokens=int(usage.get("completion_tokens", 0)),
        refused=looks_like_refusal(content),
        empty=not content.strip(),
        truncated=finish_reason == "length",
        finish_reason=finish_reason,
    )


def looks_like_refusal(text: str) -> bool:
    return any(marker in text for marker in REFUSE_MARKERS)


def refuse(reason: str = "") -> Generation:
    """本地直接拒答，不消耗 token。"""
    suffix = f"（{reason}）" if reason else ""
    return Generation(answer=f"{REFUSAL_TEXT}。{suffix}", completion_tokens=0,
                      refused=True)
