"""知识图谱构建工具使用的 Cypher 标识符白名单。"""

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

ALLOWED_RELATIONSHIP_TYPES = frozenset(
    {
        "APPLIED_IN",
        "BASED_ON",
        "BELONGS_TO",
        "COVERS",
        "HAS_COMPLEXITY",
        "HAS_CONCEPT",
        "HAS_CORE_CONCEPT",
        "HAS_CORE_RELATION",
        "HAS_DIFFICULTY",
        "HAS_INSTANCE",
        "HAS_METHOD",
        "HAS_TYPE",
        "IS_ABSTRACT_CONCEPT",
        "IS_CONCRETE_ENTITY",
        "IS_KEY_EVENT",
        "IS_SUBCATEGORY",
        "LEADS_TO",
        "PART_OF",
        "PRACTICES_FOR",
        "PREREQUISITE",
        "RECOMMENDS",
        "RELATED_TO",
        "RELATED_TO_KNOWLEDGE",
        "REQUIRES",
        "SIMILAR_TO",
        "USED_BY",
        "USES_ALGORITHM",
        "USES_STRUCTURE",
    }
)

ALLOWED_PROPERTY_NAMES = frozenset(
    {
        "acceptance_rate",
        "applications",
        "category",
        "category1",
        "category2",
        "chapter_id",
        "confidence",
        "content_file",
        "description",
        "difficulty",
        "elaboration",
        "exercises",
        "frequency",
        "id",
        "importance",
        "input_format",
        "keywords",
        "learning_time",
        "learning_tips",
        "level",
        "match_method",
        "memory_limit",
        "method",
        "name",
        "node_id",
        "node_type",
        "notation",
        "order",
        "output_format",
        "overview",
        "official_difficulty",
        "official_knowledge_tags",
        "official_tag",
        "parent",
        "parent_category",
        "pass_rate",
        "questions",
        "quote",
        "reason",
        "related_section",
        "remark",
        "sample_input",
        "sample_output",
        "score",
        "section",
        "similarity",
        "source",
        "source_text",
        "space_complexity",
        "sub_sections",
        "tags",
        "text_id",
        "time_complexity",
        "time_limit",
        "title",
        "type",
        "url",
        "weight",
    }
)


def _require_allowed(value: str, allowed: frozenset[str], kind: str) -> str:
    if value not in allowed:
        raise ValueError(f"不允许的{kind}: {value!r}")
    return value


def validate_node_label(value: str) -> str:
    return _require_allowed(value, ALLOWED_NODE_LABELS, "节点标签")


def validate_relationship_type(value: str) -> str:
    return _require_allowed(value, ALLOWED_RELATIONSHIP_TYPES, "关系类型")


def validate_property_name(value: str) -> str:
    return _require_allowed(value, ALLOWED_PROPERTY_NAMES, "属性名")


def validate_property_names(values: Iterable[str]) -> list[str]:
    return [validate_property_name(value) for value in values]
