"""Incrementally sync MC0577-MC0588 from the Matiji question bank.

The command is a dry run by default. Pass ``--apply`` to atomically update
``data/processed/matiji_knowledge_graph.json``.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Iterable

import requests
from bs4 import BeautifulSoup, NavigableString


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_QUESTION_FILE = ROOT / "data" / "processed" / "matiji_knowledge_graph.json"
DEFAULT_KNOWLEDGE_FILE = (
    ROOT / "data" / "processed" / "knowledge_graph_v3" / "knowledge_graph.json"
)
API_URL = "https://www.matiji.net/exam-back/pc/queryQuestionByOrder.do"
QUESTION_BANK_ID = "C98C14523F069FECB0DEED64F00CEAB0"
TREE_ID = 4777
ORDERS = tuple(range(77, 89))
EXPECTED_IDS = tuple(f"MC{number:04d}" for number in range(577, 589))

DIFFICULTY_MAP = {
    "青铜": "简单",
    "白银": "简单",
    "黄金": "中等",
    "钻石": "中等",
    "王者": "困难",
    "星耀": "星耀",
}

# Only exact semantic matches are listed here. Tags without a matching course
# knowledge node remain available through categories and official_knowledge_tags.
OFFICIAL_KNOWLEDGE_LINKS = {
    ("算法基础", "递推 | 递归 | 分治"): ("NODE_361", "NODE_378"),
    ("数据结构", "并查集"): ("NODE_369",),
    ("语言基础", "数组"): ("NODE_103",),
    ("动态规划", "线性DP"): ("NODE_407",),
    ("动态规划", "树形DP"): ("NODE_407",),
    ("图论", "最小生成树"): ("NODE_209", "NODE_426", "NODE_427"),
    ("数学", "拟阵"): ("NODE_425",),
    ("图论", "树上问题"): ("NODE_130",),
}


@dataclass(frozen=True)
class ParsedQuestion:
    order: int
    entity: dict[str, Any]
    knowledge_tags: tuple[tuple[str, str], ...]


@dataclass
class MergeStats:
    added_entities: Counter[str] = field(default_factory=Counter)
    added_relationships: Counter[str] = field(default_factory=Counter)
    updated_questions: int = 0
    metadata_updated: bool = False

    @property
    def changed(self) -> bool:
        return bool(
            self.added_entities
            or self.added_relationships
            or self.updated_questions
            or self.metadata_updated
        )


def _normalize_text(value: str) -> str:
    value = value.replace("\r\n", "\n").replace("\r", "\n").replace("\xa0", " ")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in value.split("\n")]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def html_to_text(html: str | None) -> str:
    """Convert Matiji HTML to readable text without duplicating KaTeX output."""
    if not html:
        return ""

    soup = BeautifulSoup(html, "lxml")
    for element in soup.select("span.editormd-tex"):
        annotation = element.find("annotation", attrs={"encoding": "application/x-tex"})
        tex = annotation.get_text(strip=True) if annotation else element.get_text(strip=True)
        element.replace_with(NavigableString(f"$${tex}$$"))

    for element in soup.find_all(["script", "style"]):
        element.decompose()
    for element in soup.find_all("br"):
        element.replace_with(NavigableString("\n"))
    for element in soup.find_all("hr"):
        element.replace_with(NavigableString("\n"))
    for cell in soup.find_all(["th", "td"]):
        cell.append(NavigableString("\t"))
    for block in soup.find_all(
        ["p", "div", "li", "tr", "table", "section", "article", "h1", "h2", "h3", "h4"]
    ):
        block.append(NavigableString("\n"))

    return _normalize_text(soup.get_text())


def normalize_difficulty(value: str) -> str:
    try:
        return DIFFICULTY_MAP[value.strip()]
    except (AttributeError, KeyError) as exc:
        raise ValueError(f"未知的码题集难度: {value!r}") from exc


def normalize_category(value: str) -> str:
    value = value.replace("\n", " ").strip()
    return re.sub(r"\s*\(\d+\)\s*$", "", value).strip()


def _require_text(value: Any, field_name: str) -> str:
    if value is None or not str(value).strip():
        raise ValueError(f"题目字段 {field_name} 为空")
    return str(value).strip()


def _parse_samples(raw_samples: Any) -> tuple[str, str]:
    if isinstance(raw_samples, str):
        try:
            samples = json.loads(raw_samples)
        except json.JSONDecodeError as exc:
            raise ValueError("simpleArray 不是有效 JSON") from exc
    else:
        samples = raw_samples
    if samples is None:
        samples = []
    if not isinstance(samples, list):
        raise ValueError("simpleArray 必须是数组")

    inputs: list[str] = []
    outputs: list[str] = []
    for sample in samples:
        if not isinstance(sample, dict):
            raise ValueError("simpleArray 中的样例必须是对象")
        inputs.append(_normalize_text(str(sample.get("sampleInput", ""))))
        outputs.append(_normalize_text(str(sample.get("sampleOutput", ""))))
    return "\n\n".join(inputs), "\n\n".join(outputs)


def _parse_pass_rate(value: Any) -> float | None:
    if value is None or value == "":
        return None
    rate = float(value)
    if rate <= 1:
        rate *= 100
    return round(rate, 2)


def parse_question(payload: dict[str, Any], order: int) -> ParsedQuestion:
    data = payload.get("data")
    if not isinstance(data, dict):
        raise ValueError(f"第 {order} 题响应缺少 data")
    problem = data.get("ojProblemEntity")
    if not isinstance(problem, dict):
        raise ValueError(f"第 {order} 题响应缺少 ojProblemEntity")

    question_id = _require_text(problem.get("ojNumber"), "ojNumber")
    name = _require_text(problem.get("problemName"), "problemName")
    official_difficulty = _require_text(problem.get("difficultyLevel"), "difficultyLevel")

    raw_tags = data.get("ojProblemKnowledgeEntityList") or []
    tags: list[tuple[str, str]] = []
    for raw_tag in raw_tags:
        if not isinstance(raw_tag, dict):
            raise ValueError(f"{question_id} 的知识标签格式无效")
        parent = _require_text(raw_tag.get("parentName"), "parentName")
        name_value = _require_text(raw_tag.get("knowledgeName"), "knowledgeName")
        tag = (parent, name_value)
        if tag not in tags:
            tags.append(tag)
    if not tags:
        raise ValueError(f"{question_id} 没有官网知识标签")

    sample_input, sample_output = _parse_samples(problem.get("simpleArray"))
    pass_rate = data.get("passRateEntity") or {}
    pass_rate_value = pass_rate.get("passRate") if isinstance(pass_rate, dict) else None
    primary_category = tags[0]
    entity = {
        "type": "Question",
        "id": question_id,
        "name": name,
        "description": html_to_text(problem.get("descriptionHtml")),
        "input_format": _normalize_text(str(problem.get("inputFormat") or "")),
        "output_format": _normalize_text(str(problem.get("outputFormat") or "")),
        "sample_input": sample_input,
        "sample_output": sample_output,
        "difficulty": normalize_difficulty(official_difficulty),
        "official_difficulty": official_difficulty,
        "pass_rate": _parse_pass_rate(pass_rate_value),
        "source": "码蹄集",
        "url": (
            f"https://www.matiji.net/exam/brushquestion/{order}/{TREE_ID}/{QUESTION_BANK_ID}"
        ),
        "category1": primary_category[0],
        "category2": primary_category[1],
        "official_knowledge_tags": [f"{parent}/{child}" for parent, child in tags],
    }
    return ParsedQuestion(order=order, entity=entity, knowledge_tags=tuple(tags))


def validate_batch(questions: Iterable[ParsedQuestion]) -> list[ParsedQuestion]:
    result = list(questions)
    actual_orders = tuple(question.order for question in result)
    actual_ids = tuple(question.entity["id"] for question in result)
    if actual_orders != ORDERS:
        raise ValueError(f"题目顺序不匹配: 期望 {ORDERS}，实际 {actual_orders}")
    if actual_ids != EXPECTED_IDS:
        raise ValueError(f"题目编号不匹配: 期望 {EXPECTED_IDS}，实际 {actual_ids}")
    return result


def fetch_questions(timeout: float = 20) -> list[ParsedQuestion]:
    session = requests.Session()
    session.headers.update({"User-Agent": "knowledge-graph-matiji-sync/1.0"})
    questions: list[ParsedQuestion] = []
    for order in ORDERS:
        response = session.post(
            API_URL,
            data={
                "questionByOrder": order,
                "treeId": TREE_ID,
                "questionBankId": QUESTION_BANK_ID,
            },
            timeout=timeout,
        )
        response.raise_for_status()
        try:
            payload = response.json()
        except requests.exceptions.JSONDecodeError as exc:
            raise ValueError(f"第 {order} 题接口未返回 JSON") from exc
        questions.append(parse_question(payload, order))
    return validate_batch(questions)


def _endpoint(relationship: dict[str, Any], key: str) -> str | None:
    aliases = ("from", "source") if key == "from" else ("to", "target")
    for alias in aliases:
        value = relationship.get(alias)
        if value is not None:
            return str(value)
    return None


def _category_id(*parts: str) -> str:
    return "CATEGORY_" + "_".join(parts)


def _index_graph(data: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], set[tuple[str, str, str]]]:
    entities = data.get("entities")
    relationships = data.get("relationships")
    if not isinstance(entities, list) or not isinstance(relationships, list):
        raise ValueError("题库 JSON 的 entities/relationships 必须是数组")

    entity_by_id: dict[str, dict[str, Any]] = {}
    for entity in entities:
        if not isinstance(entity, dict) or not str(entity.get("id", "")).strip():
            raise ValueError("题库中存在无效实体")
        entity_id = str(entity["id"])
        if entity_id in entity_by_id:
            raise ValueError(f"题库中存在重复实体: {entity_id}")
        entity_by_id[entity_id] = entity

    relationship_keys: set[tuple[str, str, str]] = set()
    for relationship in relationships:
        if not isinstance(relationship, dict):
            raise ValueError("题库中存在无效关系")
        source = _endpoint(relationship, "from")
        target = _endpoint(relationship, "to")
        rel_type = str(relationship.get("type", ""))
        if not source or not target or not rel_type:
            raise ValueError("题库中存在端点或类型为空的关系")
        key = (source, target, rel_type)
        if key in relationship_keys:
            raise ValueError(f"题库中存在重复关系: {key}")
        relationship_keys.add(key)
    return entity_by_id, relationship_keys


def _requires_templates(data: dict[str, Any]) -> dict[tuple[str, str], list[dict[str, Any]]]:
    question_categories = {
        str(entity["id"]): (
            normalize_category(str(entity.get("category1", ""))),
            normalize_category(str(entity.get("category2", ""))),
        )
        for entity in data["entities"]
        if isinstance(entity, dict) and entity.get("type") == "Question"
    }
    requires_by_question: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for relationship in data["relationships"]:
        source = _endpoint(relationship, "from")
        if relationship.get("type") == "REQUIRES" and source in question_categories:
            requires_by_question[source].append(
                {
                    "to": _endpoint(relationship, "to"),
                    "attributes": copy.deepcopy(relationship.get("attributes") or {}),
                }
            )

    templates: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for question_id, category in question_categories.items():
        if category not in templates and requires_by_question.get(question_id):
            templates[category] = requires_by_question[question_id]
    return templates


def _append_entity(
    data: dict[str, Any],
    entity_by_id: dict[str, dict[str, Any]],
    entity: dict[str, Any],
    stats: MergeStats,
) -> None:
    entity_id = str(entity["id"])
    if entity_id in entity_by_id:
        return
    data["entities"].append(entity)
    entity_by_id[entity_id] = entity
    stats.added_entities[str(entity["type"])] += 1


def _append_relationship(
    data: dict[str, Any],
    relationship_keys: set[tuple[str, str, str]],
    relationship: dict[str, Any],
    stats: MergeStats,
) -> None:
    key = (relationship["from"], relationship["to"], relationship["type"])
    if key in relationship_keys:
        return
    data["relationships"].append(relationship)
    relationship_keys.add(key)
    stats.added_relationships[relationship["type"]] += 1


def merge_questions(
    data: dict[str, Any],
    questions: Iterable[ParsedQuestion],
    knowledge_entity_ids: set[str],
    updated_at: str | None = None,
) -> MergeStats:
    """Merge parsed questions into an in-memory graph without duplicates."""
    parsed_questions = list(questions)
    entity_by_id, relationship_keys = _index_graph(data)
    templates = _requires_templates(data)
    stats = MergeStats()

    configured_targets = {
        target for targets in OFFICIAL_KNOWLEDGE_LINKS.values() for target in targets
    }
    missing_targets = sorted(configured_targets - knowledge_entity_ids)
    if missing_targets:
        raise ValueError(f"官网标签映射指向不存在的知识点: {missing_targets}")

    for parsed in parsed_questions:
        question = parsed.entity
        question_id = str(question["id"])
        existing = entity_by_id.get(question_id)
        if existing is None:
            data["entities"].append(copy.deepcopy(question))
            entity_by_id[question_id] = data["entities"][-1]
            stats.added_entities["Question"] += 1
        elif existing.get("type") != "Question":
            raise ValueError(f"{question_id} 已被非题目实体占用")
        else:
            merged_entity = {**existing, **question}
            if merged_entity != existing:
                existing.clear()
                existing.update(copy.deepcopy(merged_entity))
                stats.updated_questions += 1

        for parent, child in parsed.knowledge_tags:
            parent_id = _category_id(parent)
            child_id = _category_id(parent, child)
            _append_entity(
                data,
                entity_by_id,
                {
                    "type": "Category",
                    "id": parent_id,
                    "name": parent,
                    "description": f"{parent}类题目",
                    "level": 1,
                },
                stats,
            )
            _append_entity(
                data,
                entity_by_id,
                {
                    "type": "Category",
                    "id": child_id,
                    "name": child,
                    "description": f"{child}类题目",
                    "parent": parent,
                    "level": 2,
                },
                stats,
            )
            for category_id in (parent_id, child_id):
                _append_relationship(
                    data,
                    relationship_keys,
                    {
                        "type": "BELONGS_TO",
                        "from": question_id,
                        "to": category_id,
                        "attributes": {},
                    },
                    stats,
                )

        difficulty_id = f"DIFF_{question['difficulty']}"
        _append_entity(
            data,
            entity_by_id,
            {
                "type": "Difficulty",
                "id": difficulty_id,
                "level": question["difficulty"],
                "description": f"{question['difficulty']}难度",
            },
            stats,
        )
        _append_relationship(
            data,
            relationship_keys,
            {
                "type": "HAS_DIFFICULTY",
                "from": question_id,
                "to": difficulty_id,
                "attributes": {},
            },
            stats,
        )

        primary = tuple(normalize_category(value) for value in parsed.knowledge_tags[0])
        for template in templates.get(primary, []):
            target = template["to"]
            if not target:
                continue
            _append_relationship(
                data,
                relationship_keys,
                {
                    "type": "REQUIRES",
                    "from": question_id,
                    "to": target,
                    "attributes": copy.deepcopy(template["attributes"]),
                },
                stats,
            )

        for tag in parsed.knowledge_tags:
            for target in OFFICIAL_KNOWLEDGE_LINKS.get(tag, ()):
                _append_relationship(
                    data,
                    relationship_keys,
                    {
                        "type": "REQUIRES",
                        "from": question_id,
                        "to": target,
                        "attributes": {
                            "weight": 0.9,
                            "match_method": "official_knowledge_tag",
                            "official_tag": f"{tag[0]}/{tag[1]}",
                        },
                    },
                    stats,
                )

        has_requires = any(
            source == question_id and rel_type == "REQUIRES"
            for source, _target, rel_type in relationship_keys
        )
        if not has_requires:
            raise ValueError(f"{question_id} 未能生成任何知识点关联")

    metadata = data.setdefault("metadata", {})
    desired_metadata = {
        "total_entities": len(data["entities"]),
        "total_relationships": len(data["relationships"]),
        "unique_questions": sum(
            1 for entity in data["entities"] if entity.get("type") == "Question"
        ),
    }
    metadata_changed = any(metadata.get(key) != value for key, value in desired_metadata.items())
    core_changed = bool(stats.added_entities or stats.added_relationships or stats.updated_questions)
    if core_changed or metadata_changed:
        metadata.update(desired_metadata)
        metadata["updated_at"] = updated_at or date.today().isoformat()
        stats.metadata_updated = True
    return stats


def _load_graph(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"{path} 顶层必须是对象")
    return value


def _atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _print_summary(questions: list[ParsedQuestion], stats: MergeStats, apply: bool) -> None:
    for parsed in questions:
        entity = parsed.entity
        tags = "；".join(entity["official_knowledge_tags"])
        print(
            f"{entity['id']} {entity['name']} | {entity['official_difficulty']}"
            f"->{entity['difficulty']} | {entity['pass_rate']:.2f}% | {tags}"
        )
    print("\n增量统计:")
    print(f"  新增实体: {sum(stats.added_entities.values())} {dict(stats.added_entities)}")
    print(
        f"  新增关系: {sum(stats.added_relationships.values())}"
        f" {dict(stats.added_relationships)}"
    )
    print(f"  更新题目: {stats.updated_questions}")
    if apply:
        print("  已原子写入题库文件" if stats.changed else "  数据已是最新，无需写入")
    else:
        print("  [dry-run] 未写入；使用 --apply 生效")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="同步码题集 MC0577-MC0588 及知识点关联")
    parser.add_argument("--apply", action="store_true", help="实际写入；默认仅预览")
    parser.add_argument("--question-file", type=Path, default=DEFAULT_QUESTION_FILE)
    parser.add_argument("--knowledge-file", type=Path, default=DEFAULT_KNOWLEDGE_FILE)
    parser.add_argument("--timeout", type=float, default=20, help="单个接口请求超时秒数")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        questions = fetch_questions(args.timeout)
        question_graph = _load_graph(args.question_file)
        knowledge_graph = _load_graph(args.knowledge_file)
        knowledge_ids = {
            str(entity["id"])
            for entity in knowledge_graph.get("entities", [])
            if isinstance(entity, dict) and entity.get("id")
        }
        stats = merge_questions(question_graph, questions, knowledge_ids)
        if args.apply and stats.changed:
            _atomic_write_json(args.question_file, question_graph)
        _print_summary(questions, stats, args.apply)
    except (OSError, ValueError, requests.RequestException, json.JSONDecodeError) as exc:
        print(f"同步失败: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
