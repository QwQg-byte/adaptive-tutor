"""Cypher 查询中可由应用选择的标识符白名单。"""

import re
from collections.abc import Iterable


ALLOWED_NODE_LABELS = frozenset(
    {
        "Algorithm",
        "Category",
        "Chapter",
        "Complexity",
        "Concept",
        "DataStructure",
        "Difficulty",
        "KnowledgeNode",
        "KnowledgePoint",
        "Method",
        "NodeType",
        "ProblemType",
        "Question",
        "Reference",
    }
)


def validate_node_labels(labels: Iterable[str] | None) -> list[str]:
    """返回去重后的安全标签；发现未知标签时立即拒绝。"""
    if not labels:
        return []

    normalized = list(dict.fromkeys(label.strip() for label in labels if label.strip()))
    invalid = sorted(set(normalized) - ALLOWED_NODE_LABELS)
    if invalid:
        raise ValueError(f"不支持的节点类型: {', '.join(invalid)}")
    if len(normalized) > 10:
        raise ValueError("一次最多筛选 10 种节点类型")
    return normalized


def validate_limit(value: int, *, minimum: int = 1, maximum: int = 2000) -> int:
    """为内部调用提供第二层数值边界校验。"""
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("limit 必须是整数")
    if not minimum <= value <= maximum:
        raise ValueError(f"limit 必须在 {minimum} 到 {maximum} 之间")
    return value


_LUCENE_SPECIAL_CHARS = re.compile(r'([+\-!(){}\[\]^"~*?:\\/&|])')
_ASCII_TOKEN = re.compile(r"[A-Za-z0-9_]+")


def build_fulltext_query(keyword: str) -> str:
    """Build a Lucene query string without exposing operators from user input.

    Shared by node search and question search so both go through the same
    escaping rules for the ``content_search_fulltext`` CJK index.
    """
    terms = keyword.split()
    escaped_terms = []
    for term in terms:
        escaped = _LUCENE_SPECIAL_CHARS.sub(r"\\\1", term)
        if _ASCII_TOKEN.fullmatch(term):
            escaped_terms.append(f"{escaped}*")
        else:
            # The Neo4j CJK analyzer emits bi-grams. An unquoted term is
            # analyzed the same way; quoting it prevents valid CJK hits.
            escaped_terms.append(escaped)
    return " AND ".join(escaped_terms)
