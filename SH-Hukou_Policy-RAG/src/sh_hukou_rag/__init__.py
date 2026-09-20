"""上海落户政策 RAG 最小可用实现（baseline v0.4）。

包结构：
    config      配置与常量
    loader      读取 data/*.md，解析 YAML front-matter
    chunker     条款级切分（## 标题为界）
    embeddings  向量编码 + 磁盘缓存
    retriever   查询改写 + 向量检索
    generator   调用 OpenAI 兼容 LLM 生成答案
    pipeline    端到端问答入口
"""

__version__ = "0.4.0"
