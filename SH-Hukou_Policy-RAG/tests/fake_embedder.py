"""一个不依赖网络的确定性编码器，仅用于测试。

原理：对字符做哈希分桶，得到稀疏但稳定的"词袋"向量，
字符重叠越多余弦相似度越高——足以验证排序、去重、拒答阈值等逻辑，
但绝不可用于评测真实召回质量。
"""

from __future__ import annotations

import hashlib
from typing import Sequence

import numpy as np


class HashingEmbedder:
    def __init__(self, dim: int = 512) -> None:
        self.dim = dim

    def encode(self, texts: Sequence[str], **_: object) -> np.ndarray:
        out = np.zeros((len(texts), self.dim), dtype=np.float32)
        for row, text in enumerate(texts):
            for ch in text:
                if ch.isspace():
                    continue
                idx = int(hashlib.md5(ch.encode("utf-8")).hexdigest()[:8], 16)
                out[row, idx % self.dim] += 1.0
            norm = np.linalg.norm(out[row])
            if norm > 0:
                out[row] /= norm
        return out
