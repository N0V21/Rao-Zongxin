"""向量编码与缓存。

修复了原实现最影响可用性的问题：`search()` 每次提问都对全部 chunk
重新 `model.encode(...)`（53 条要重算一遍，交互式问答每轮多花数秒）。
这里只编码一次，并把矩阵缓存到磁盘。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Protocol, Sequence

import numpy as np

from .chunker import Chunk
from .config import CACHE_DIR, MODEL_NAME


class Embedder(Protocol):
    """最小编码器接口，测试里可以注入假实现，不必下载模型。"""

    def encode(self, texts: Sequence[str], **kwargs) -> np.ndarray: ...


_encoder = None  # 进程级单例，避免重复加载权重


def get_encoder(model_name: str = MODEL_NAME) -> Embedder:
    global _encoder
    if _encoder is None:
        from sentence_transformers import SentenceTransformer

        _encoder = SentenceTransformer(model_name)
    return _encoder


def encode_texts(embedder: Embedder, texts: Sequence[str]) -> np.ndarray:
    """编码为 L2 归一化矩阵，余弦相似度可直接用点积。"""
    vecs = embedder.encode(list(texts), normalize_embeddings=True,
                           show_progress_bar=False)
    return np.asarray(vecs, dtype=np.float32)


def _fingerprint(model_name: str, texts: Sequence[str]) -> str:
    h = hashlib.sha256(model_name.encode("utf-8"))
    for t in texts:
        h.update(hashlib.sha256(t.encode("utf-8")).digest())
    return h.hexdigest()[:20]


def build_index(embedder: Embedder, chunks: Sequence[Chunk], *,
                model_name: str = MODEL_NAME,
                cache_dir: Path | None = None) -> np.ndarray:
    """编码全部 chunk，命中缓存则直接读取。"""
    cache_dir = Path(cache_dir) if cache_dir else CACHE_DIR
    texts = [c.search_text for c in chunks]
    fp = _fingerprint(model_name, texts)

    cache_dir.mkdir(parents=True, exist_ok=True)
    vec_path = cache_dir / f"chunks-{fp}.npy"
    meta_path = cache_dir / f"chunks-{fp}.json"

    if vec_path.exists() and meta_path.exists():
        try:
            cached = np.load(vec_path)
            if cached.shape[0] == len(chunks):
                return cached
        except (OSError, ValueError):
            pass  # 缓存损坏则重新编码

    matrix = encode_texts(embedder, texts)
    np.save(vec_path, matrix)
    meta_path.write_text(
        json.dumps({"model": model_name, "n_chunks": len(chunks),
                    "dim": int(matrix.shape[1]), "fingerprint": fp},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return matrix
