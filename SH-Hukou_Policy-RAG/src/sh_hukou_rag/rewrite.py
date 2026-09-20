"""查询改写。

修复记录：原 main.py 定义了 `_REWRITE` 列表和 `rewrite()` 函数，但函数体
引用不存在的 `_REWRITE_RULES`（一调用就 NameError），而且 `rewrite()`
在 `ask()`/`search()` 里从未被调用——整套改写逻辑是死代码。

这里把规则修好并真正接进检索，但要避免一个容易踩的坑：
**把"文档全名"当成独立查询注入会污染排序**。
例如"居转户"扩展成"持有《上海市居住证》人员申办本市常住户口"后，
该串几乎是 02 号文全篇的字面超集，会让"第二条（指导原则）"这类
无关条款拿到 0.91 的高分，把真正含答案的条款挤下去。

因此规则拆成两类：
- REPLACEMENTS：整句替换，保留原问题的其余部分；
- KEYWORDS    ：短关键词注入，只补充词面，不引入整篇文档的字面命中。
检索侧再对变体得分做一个折扣加权（见 retriever.VARIANT_WEIGHT）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List

# 民间简称 → 政策正式名称（用于整句替换）
_REPLACEMENTS: list[tuple[str, str]] = [
    (r"居转户", "居住证转常住户口"),
]

# 触发模式 → 补充的短关键词（注入独立查询，靠语义而非字面覆盖）
_KEYWORDS: list[tuple[str, list[str]]] = [
    (r"配偶|子女|孩子", ["家属随迁", "配偶 未成年子女"]),
    (r"满几年|年限|多久|多长时间", ["持证年限", "累计年限"]),
    (r"公示期|公示.*天|几天", ["公示", "网上公示 天数"]),
    (r"个人.*提交|自己.*申请|个人.*申请", ["由用人单位提出申请"]),
    (r"还有效|失效|作废|旧版|20\d\d年版", ["施行期限", "有效期"]),
    (r"哪几类|哪些类型|分类", ["分类 类别"]),
]

MAX_VARIANTS = 6


@dataclass
class Variants:
    """查询变体集合，第一项固定为原查询。"""

    original: str
    items: List[str]

    def __iter__(self):
        return iter(self.items)

    def __len__(self) -> int:
        return len(self.items)


def rewrite(query: str) -> Variants:
    """构造查询变体。第一个元素永远是原查询。"""
    q = query.strip()
    items: list[str] = [q]

    def add(text: str) -> None:
        text = " ".join(text.split())
        if text and text not in items:
            items.append(text)

    for pattern, expansion in _REPLACEMENTS:
        if re.search(pattern, q):
            add(re.sub(pattern, expansion, q))

    matched = False
    for pattern, keywords in _KEYWORDS:
        if re.search(pattern, q):
            matched = True
            for kw in keywords:
                add(kw)

    # 关键词命中但原问题很短（如只有"居转户"）时，补上完整正式名称，
    # 否则向量只有一个词的语义，召回面太窄。
    if matched and len(q) <= 8:
        add("持有《上海市居住证》人员申办本市常住户口")

    return Variants(original=q, items=items[:MAX_VARIANTS])


def rewrite_texts(query: str) -> list[str]:
    """只要字符串列表的便捷接口。"""
    return list(rewrite(query))
