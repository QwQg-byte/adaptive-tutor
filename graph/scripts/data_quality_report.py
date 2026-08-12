"""Generate an offline data-quality report for the current graph inputs.

The report is intentionally independent of Neo4j so it can run before an import
and can be used in CI. It accepts the two current source files by default, but
the file arguments are configurable for future course or question datasets.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_KNOWLEDGE_FILE = ROOT / "data" / "processed" / "knowledge_graph_v3" / "knowledge_graph.json"
DEFAULT_QUESTION_FILE = ROOT / "data" / "processed" / "matiji_knowledge_graph.json"


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"{path} 顶层必须是对象")
    return value


def _entity_id(entity: dict[str, Any]) -> str | None:
    value = entity.get("id")
    return str(value).strip() if value is not None and str(value).strip() else None


def _relationship_endpoints(relationship: dict[str, Any]) -> tuple[str | None, str | None]:
    source = relationship.get("source", relationship.get("from"))
    target = relationship.get("target", relationship.get("to"))
    source = str(source).strip() if source is not None and str(source).strip() else None
    target = str(target).strip() if target is not None and str(target).strip() else None
    return source, target


def _counter_values(counter: Counter[str]) -> dict[str, int]:
    return dict(sorted(counter.items(), key=lambda item: (-item[1], item[0])))


def _sample(values: Iterable[Any], limit: int = 20) -> list[Any]:
    return list(values)[:limit]


def build_report(
    knowledge_file: Path = DEFAULT_KNOWLEDGE_FILE,
    question_file: Path = DEFAULT_QUESTION_FILE,
) -> dict[str, Any]:
    datasets = [(knowledge_file, _read_json(knowledge_file)), (question_file, _read_json(question_file))]
    entities: list[dict[str, Any]] = []
    relationships: list[dict[str, Any]] = []
    metadata_checks: list[dict[str, Any]] = []

    for path, data in datasets:
        source = str(path)
        current_entities = data.get("entities", [])
        current_relationships = data.get("relationships", [])
        if not isinstance(current_entities, list) or not isinstance(current_relationships, list):
            raise ValueError(f"{path} 的 entities/relationships 必须是数组")
        entities.extend({"source_file": source, "entity": entity} for entity in current_entities if isinstance(entity, dict))
        relationships.extend(
            {"source_file": source, "relationship": relationship}
            for relationship in current_relationships
            if isinstance(relationship, dict)
        )
        metadata = data.get("metadata", {})
        metadata_checks.append(
            {
                "file": source,
                "declared_entities": metadata.get("total_entities"),
                "actual_entities": len(current_entities),
                "declared_relationships": metadata.get("total_relationships"),
                "actual_relationships": len(current_relationships),
            }
        )

    entity_occurrences: defaultdict[str, list[str]] = defaultdict(list)
    entity_types: Counter[str] = Counter()
    for item in entities:
        entity = item["entity"]
        entity_id = _entity_id(entity)
        if entity_id:
            entity_occurrences[entity_id].append(item["source_file"])
        entity_types[str(entity.get("type", "<missing>"))] += 1

    known_ids = set(entity_occurrences)
    duplicate_entities = {
        entity_id: files
        for entity_id, files in sorted(entity_occurrences.items())
        if len(files) > 1
    }

    relationship_types: Counter[str] = Counter()
    relationship_keys: defaultdict[tuple[str | None, str | None, str | None], list[str]] = defaultdict(list)
    invalid_relationships: list[dict[str, Any]] = []
    degree: Counter[str] = Counter()
    for item in relationships:
        relationship = item["relationship"]
        rel_type = str(relationship.get("type", "<missing>"))
        source, target = _relationship_endpoints(relationship)
        relationship_types[rel_type] += 1
        relationship_keys[(source, target, rel_type)].append(item["source_file"])
        if not source or not target or source not in known_ids or target not in known_ids:
            invalid_relationships.append(
                {
                    "source_file": item["source_file"],
                    "type": rel_type,
                    "source": source,
                    "target": target,
                }
            )
        else:
            degree[source] += 1
            degree[target] += 1

    duplicate_relationships = {
        "|".join("" if value is None else value for value in key): files
        for key, files in sorted(relationship_keys.items())
        if len(files) > 1
    }
    orphan_nodes = sorted(entity_id for entity_id in known_ids if degree[entity_id] == 0)

    unique_entities_by_type: defaultdict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for item in entities:
        entity = item["entity"]
        entity_id = _entity_id(entity)
        if entity_id:
            unique_entities_by_type[str(entity.get("type", "<missing>"))].setdefault(entity_id, entity)
    knowledge_nodes = list(unique_entities_by_type["KnowledgeNode"].values())
    questions = list(unique_entities_by_type["Question"].values())
    related_knowledge_ids = {
        target
        for item in relationships
        if item["relationship"].get("type") == "REQUIRES"
        for source, target in [_relationship_endpoints(item["relationship"])]
        if source and target
    }
    required_question_ids = {
        source
        for item in relationships
        if item["relationship"].get("type") == "REQUIRES"
        for source, target in [_relationship_endpoints(item["relationship"])]
        if source and target
    }
    chapter_linked_ids = {
        source
        for item in relationships
        if item["relationship"].get("type") == "BELONGS_TO"
        for source, target in [_relationship_endpoints(item["relationship"])]
        if source and target and source.startswith("NODE_")
    }

    coverage = {
        "knowledge_nodes": {
            "total": len(knowledge_nodes),
            "with_chapter": sum(1 for node in knowledge_nodes if _entity_id(node) in chapter_linked_ids),
            "with_overview": sum(1 for node in knowledge_nodes if str(node.get("overview", "")).strip()),
            "with_tags": sum(1 for node in knowledge_nodes if node.get("tags")),
        },
        "questions": {
            "total": len(questions),
            "with_requires_relation": sum(1 for question in questions if _entity_id(question) in required_question_ids),
            "with_url": sum(1 for question in questions if str(question.get("url", "")).strip()),
            "with_pass_rate": sum(1 for question in questions if question.get("pass_rate") is not None),
        },
        "requires": {
            "links": relationship_types.get("REQUIRES", 0),
            "knowledge_nodes_referenced": len(related_knowledge_ids & known_ids),
        },
    }

    metadata_mismatches = [
        check
        for check in metadata_checks
        if check["declared_entities"] != check["actual_entities"]
        or check["declared_relationships"] != check["actual_relationships"]
    ]
    issues = {
        "duplicate_entity_ids": duplicate_entities,
        "duplicate_relationships": duplicate_relationships,
        "invalid_relationships": _sample(invalid_relationships),
        "invalid_relationship_count": len(invalid_relationships),
        "orphan_node_ids": orphan_nodes,
        "metadata_mismatches": metadata_mismatches,
    }
    error_count = (
        len(duplicate_entities)
        + len(duplicate_relationships)
        + len(invalid_relationships)
        + len(metadata_mismatches)
    )

    return {
        "files": [str(path) for path, _ in datasets],
        "summary": {
            "entity_count": len(entities),
            "relationship_count": len(relationships),
            "unique_entity_count": len(known_ids),
            "entity_types": _counter_values(entity_types),
            "relationship_types": _counter_values(relationship_types),
            "orphan_node_count": len(orphan_nodes),
            "error_count": error_count,
        },
        "metadata": metadata_checks,
        "coverage": coverage,
        "issues": issues,
    }


def _render_text(report: dict[str, Any]) -> str:
    summary = report["summary"]
    coverage = report["coverage"]
    issues = report["issues"]
    lines = [
        "知识图谱数据质量报告",
        f"实体: {summary['entity_count']}（唯一 {summary['unique_entity_count']}）",
        f"关系: {summary['relationship_count']}",
        f"孤立节点: {summary['orphan_node_count']}",
        f"质量错误: {summary['error_count']}",
        "",
        "实体类型:",
    ]
    lines.extend(f"  {name}: {count}" for name, count in summary["entity_types"].items())
    lines.append("关系类型:")
    lines.extend(f"  {name}: {count}" for name, count in summary["relationship_types"].items())
    lines.extend(
        [
            "",
            "覆盖率:",
            f"  知识点章节归属: {coverage['knowledge_nodes']['with_chapter']}/{coverage['knowledge_nodes']['total']}",
            f"  知识点有概述: {coverage['knowledge_nodes']['with_overview']}/{coverage['knowledge_nodes']['total']}",
            f"  题目有关联知识点: {coverage['questions']['with_requires_relation']}/{coverage['questions']['total']}",
            f"  题目有通过率: {coverage['questions']['with_pass_rate']}/{coverage['questions']['total']}",
            "",
            f"重复实体: {len(issues['duplicate_entity_ids'])}",
            f"重复关系: {len(issues['duplicate_relationships'])}",
            f"无效关系: {issues['invalid_relationship_count']}",
            f"metadata 计数不一致: {len(issues['metadata_mismatches'])}",
        ]
    )
    if issues["orphan_node_ids"]:
        lines.append(f"孤立节点示例: {', '.join(issues['orphan_node_ids'][:20])}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="生成知识图谱离线数据质量报告")
    parser.add_argument("--knowledge-file", type=Path, default=DEFAULT_KNOWLEDGE_FILE)
    parser.add_argument("--question-file", type=Path, default=DEFAULT_QUESTION_FILE)
    parser.add_argument("--output", type=Path, help="将 JSON 报告写入文件")
    parser.add_argument("--json", action="store_true", dest="as_json", help="输出完整 JSON 报告")
    parser.add_argument("--strict", action="store_true", help="发现重复/无效数据时返回非零退出码")
    args = parser.parse_args()

    try:
        report = build_report(args.knowledge_file, args.question_file)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"数据质量报告失败: {exc}", file=sys.stderr)
        return 2

    payload = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
    print(payload if args.as_json else _render_text(report))
    return 1 if args.strict and report["summary"]["error_count"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
