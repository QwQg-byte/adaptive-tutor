"""Batch import knowledge graph data into Neo4j."""

import argparse
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Sequence

from loguru import logger

from knowledge_graph.cypher_security import (
    validate_node_label,
    validate_property_names,
    validate_relationship_type,
)
from knowledge_graph.neo4j_connector import Neo4jConnector
from knowledge_graph.neo4j_exceptions import Neo4jConnectionError, Neo4jConnectorError


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_KG_FILE = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "knowledge_graph_v3"
    / "knowledge_graph.json"
)
DEFAULT_QUESTIONS_FILE = (
    PROJECT_ROOT / "data" / "processed" / "matiji_knowledge_graph.json"
)
DEFAULT_FAILURE_REPORT = PROJECT_ROOT / "logs" / "import_failures.json"


def load_knowledge_graph(json_file: Path) -> Dict[str, Any]:
    """Load one graph JSON document."""
    with json_file.open("r", encoding="utf-8") as file:
        return json.load(file)


def validate_import_data(data: Dict[str, Any], source: str) -> None:
    """Validate every identifier before connecting to or clearing Neo4j."""
    for index, entity in enumerate(data.get("entities", [])):
        try:
            validate_node_label(entity.get("type", ""))
            validate_property_names(
                key for key in entity.keys() if key not in {"type", "id"}
            )
        except ValueError as exc:
            raise ValueError(
                f"{source} 的第 {index + 1} 个实体不安全: {exc}"
            ) from exc

    for index, relationship in enumerate(data.get("relationships", [])):
        try:
            validate_relationship_type(relationship.get("type", ""))
            validate_property_names((relationship.get("attributes") or {}).keys())
        except ValueError as exc:
            raise ValueError(
                f"{source} 的第 {index + 1} 个关系不安全: {exc}"
            ) from exc


def normalize_property_value(value: Any) -> Any:
    """Keep flat string lists native and serialize nested values safely."""
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return value
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False)
    return value


def chunks(rows: Sequence[Dict[str, Any]], size: int) -> Iterable[List[Dict[str, Any]]]:
    for start in range(0, len(rows), size):
        yield list(rows[start : start + size])


def make_failure(
    *,
    source: str,
    kind: str,
    index: int,
    item_type: str,
    reason: str,
    item_id: str = "",
    from_id: str = "",
    to_id: str = "",
    error_type: str = "",
) -> Dict[str, Any]:
    failure = {
        "source": source,
        "kind": kind,
        "index": index,
        "type": item_type,
        "reason": reason,
    }
    if item_id:
        failure["id"] = item_id
    if from_id:
        failure["from_id"] = from_id
    if to_id:
        failure["to_id"] = to_id
    if error_type:
        failure["error_type"] = error_type
    return failure


def execute_batch_with_isolation(
    rows: List[Dict[str, Any]],
    execute: Callable[[List[Dict[str, Any]]], List[Dict[str, Any]]],
    failure_by_row_id: Dict[str, Dict[str, Any]],
    failures: List[Dict[str, Any]],
) -> set[str]:
    """Execute an atomic batch, bisecting failed batches down to one row."""
    if not rows:
        return set()
    try:
        records = execute(rows)
        return {record["row_id"] for record in records}
    except Neo4jConnectionError:
        raise
    except Neo4jConnectorError as exc:
        if len(rows) == 1:
            row_id = rows[0]["row_id"]
            failure = dict(failure_by_row_id[row_id])
            failure["reason"] = "query_error"
            failure["error_type"] = type(exc).__name__
            failures.append(failure)
            logger.error("导入记录 {} 失败: {}", row_id, type(exc).__name__)
            return set()

        middle = len(rows) // 2
        return execute_batch_with_isolation(
            rows[:middle], execute, failure_by_row_id, failures
        ) | execute_batch_with_isolation(
            rows[middle:], execute, failure_by_row_id, failures
        )


def import_knowledge_nodes(
    connector: Neo4jConnector,
    data: Dict[str, Any],
    source: str,
    batch_size: int,
    failures: List[Dict[str, Any]],
) -> Dict[str, int]:
    """Import entities with one UNWIND transaction per label and batch."""
    entities = data.get("entities", [])
    logger.info("开始分批导入 {} 个实体，批次大小 {}", len(entities), batch_size)
    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    failure_by_row_id: Dict[str, Dict[str, Any]] = {}

    for index, entity in enumerate(entities, start=1):
        entity_type = validate_node_label(entity.get("type", ""))
        entity_id = entity.get("id")
        if entity_id in (None, ""):
            failures.append(
                make_failure(
                    source=source,
                    kind="entity",
                    index=index,
                    item_type=entity_type,
                    reason="missing_id",
                )
            )
            continue

        properties = {
            key: normalize_property_value(value)
            for key, value in entity.items()
            if key not in {"type", "id"}
        }
        validate_property_names(properties.keys())
        row_id = f"{source}:entity:{index}"
        grouped[entity_type].append(
            {"row_id": row_id, "id": entity_id, "properties": properties}
        )
        failure_by_row_id[row_id] = make_failure(
            source=source,
            kind="entity",
            index=index,
            item_type=entity_type,
            item_id=str(entity_id),
            reason="",
        )

    stats: Dict[str, int] = defaultdict(int)
    for entity_type, rows in sorted(grouped.items()):
        query = f"""
        UNWIND $rows AS row
        MERGE (n:{entity_type} {{id: row.id}})
        SET n += row.properties
        RETURN row.row_id AS row_id
        """

        def execute(batch: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
            return connector.execute_write_records(query, {"rows": batch})

        for batch in chunks(rows, batch_size):
            successful = execute_batch_with_isolation(
                batch,
                execute,
                failure_by_row_id,
                failures,
            )
            stats[entity_type] += len(successful)

    logger.info("实体导入完成: {} 条成功", sum(stats.values()))
    for entity_type, count in sorted(stats.items()):
        logger.info("  {}: {}", entity_type, count)
    return dict(stats)


def import_relationships(
    connector: Neo4jConnector,
    data: Dict[str, Any],
    source: str,
    batch_size: int,
    failures: List[Dict[str, Any]],
    id_to_label: Dict[Any, str] | None = None,
) -> Dict[str, int]:
    """Import relationships in UNWIND batches and report missing endpoints.

    传入 id_to_label（实体 ID -> 节点标签）时，端点 MATCH 会带标签，
    使其命中按标签建立的唯一约束索引，避免逐行全库扫描（B7）。
    """
    relationships = data.get("relationships", [])
    logger.info("开始分批导入 {} 个关系，批次大小 {}", len(relationships), batch_size)
    id_to_label = id_to_label or {}
    # 分组键从 rel_type 扩展为 (rel_type, from_label, to_label)，
    # 端点标签未知时留空串走无标签兜底分支。
    grouped: Dict[tuple[str, str, str], List[Dict[str, Any]]] = defaultdict(list)
    failure_by_row_id: Dict[str, Dict[str, Any]] = {}

    for index, relationship in enumerate(relationships, start=1):
        rel_type = validate_relationship_type(relationship.get("type", ""))
        from_id = relationship.get("from") or relationship.get("source")
        to_id = relationship.get("to") or relationship.get("target")
        if from_id in (None, "") or to_id in (None, ""):
            failures.append(
                make_failure(
                    source=source,
                    kind="relationship",
                    index=index,
                    item_type=rel_type,
                    from_id=str(from_id or ""),
                    to_id=str(to_id or ""),
                    reason="missing_endpoint_id",
                )
            )
            continue

        attributes = {
            key: normalize_property_value(value)
            for key, value in (relationship.get("attributes") or {}).items()
        }
        validate_property_names(attributes.keys())
        row_id = f"{source}:relationship:{index}"
        from_label = id_to_label.get(from_id, "")
        to_label = id_to_label.get(to_id, "")
        grouped[(rel_type, from_label, to_label)].append(
            {
                "row_id": row_id,
                "from_id": from_id,
                "to_id": to_id,
                "attributes": attributes,
            }
        )
        failure_by_row_id[row_id] = make_failure(
            source=source,
            kind="relationship",
            index=index,
            item_type=rel_type,
            from_id=str(from_id),
            to_id=str(to_id),
            reason="",
        )

    stats: Dict[str, int] = defaultdict(int)
    for (rel_type, from_label, to_label), rows in sorted(grouped.items()):
        source_pattern = f"(source:{from_label} {{id: row.from_id}})" if from_label else "(source {id: row.from_id})"
        target_pattern = f"(target:{to_label} {{id: row.to_id}})" if to_label else "(target {id: row.to_id})"
        query = f"""
        UNWIND $rows AS row
        MATCH {source_pattern}
        MATCH {target_pattern}
        MERGE (source)-[r:{rel_type}]->(target)
        SET r += row.attributes
        RETURN DISTINCT row.row_id AS row_id
        """

        def execute(batch: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
            return connector.execute_write_records(query, {"rows": batch})

        for batch in chunks(rows, batch_size):
            failure_count_before = len(failures)
            successful = execute_batch_with_isolation(
                batch,
                execute,
                failure_by_row_id,
                failures,
            )
            expected = {row["row_id"] for row in batch}
            missing = expected - successful
            batch_query_failures = {
                (failure["source"], failure["kind"], failure["index"])
                for failure in failures[failure_count_before:]
            }
            for row_id in sorted(missing):
                failure_key = (
                    failure_by_row_id[row_id]["source"],
                    "relationship",
                    failure_by_row_id[row_id]["index"],
                )
                if failure_key in batch_query_failures:
                    continue
                failure = dict(failure_by_row_id[row_id])
                failure["reason"] = "endpoint_not_found"
                failures.append(failure)
            stats[rel_type] += len(successful)

    logger.info("关系导入完成: {} 条成功", sum(stats.values()))
    for rel_type, count in sorted(stats.items()):
        logger.info("  {}: {}", rel_type, count)
    return dict(stats)


def verify_import(connector: Neo4jConnector) -> Dict[str, Any]:
    nodes = connector.execute_read(
        """
        MATCH (n)
        RETURN labels(n)[0] as label, count(*) as count
        ORDER BY count DESC
        """
    )
    relationships = connector.execute_read(
        """
        MATCH ()-[r]->()
        RETURN type(r) as type, count(*) as count
        ORDER BY count DESC
        """
    )
    summary = {
        "total_nodes": sum(row["count"] for row in nodes),
        "total_relationships": sum(row["count"] for row in relationships),
        "nodes": nodes,
        "relationships": relationships,
    }
    logger.info(
        "导入验证: {} 个节点，{} 条关系",
        summary["total_nodes"],
        summary["total_relationships"],
    )
    return summary


def write_failure_report(
    report_path: Path,
    failures: List[Dict[str, Any]],
    verification: Dict[str, Any],
) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "failure_count": len(failures),
        "verification": verification,
        "failures": failures,
    }
    temporary_path = report_path.with_suffix(report_path.suffix + ".tmp")
    with temporary_path.open("w", encoding="utf-8", newline="\n") as file:
        json.dump(report, file, ensure_ascii=False, indent=2)
        file.write("\n")
    temporary_path.replace(report_path)
    logger.info("导入报告已写入 {}", report_path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="批量导入知识图谱数据到 Neo4j")
    parser.add_argument("--kg-file", type=Path, default=DEFAULT_KG_FILE)
    parser.add_argument("--questions-file", type=Path, default=DEFAULT_QUESTIONS_FILE)
    source_group = parser.add_mutually_exclusive_group()
    source_group.add_argument("--kg-only", action="store_true")
    source_group.add_argument("--questions-only", action="store_true")
    clear_group = parser.add_mutually_exclusive_group()
    clear_group.add_argument("--clear", dest="clear", action="store_true")
    clear_group.add_argument("--no-clear", dest="clear", action="store_false")
    parser.set_defaults(clear=None)
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument("--relationship-batch-size", type=int, default=1000)
    parser.add_argument("--failure-report", type=Path, default=DEFAULT_FAILURE_REPORT)
    args = parser.parse_args()
    if not 1 <= args.batch_size <= 5000:
        parser.error("--batch-size 必须在 1 到 5000 之间")
    if not 1 <= args.relationship_batch_size <= 10000:
        parser.error("--relationship-batch-size 必须在 1 到 10000 之间")
    return args


def main() -> int:
    args = parse_args()
    selected: List[tuple[str, Path]] = []
    if not args.questions_only:
        selected.append(("knowledge", args.kg_file.resolve()))
    if not args.kg_only:
        selected.append(("questions", args.questions_file.resolve()))

    data_sources: List[tuple[str, Dict[str, Any]]] = []
    try:
        for name, path in selected:
            if not path.is_file():
                raise FileNotFoundError(f"数据文件不存在: {path}")
            data = load_knowledge_graph(path)
            validate_import_data(data, str(path))
            data_sources.append((name, data))
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        logger.error("导入前校验失败，未连接数据库且未清除数据: {}", exc)
        write_failure_report(
            args.failure_report.resolve(),
            [
                {
                    "source": "input",
                    "kind": "validation",
                    "index": 0,
                    "type": "input_data",
                    "reason": "validation_error",
                    "error_type": type(exc).__name__,
                }
            ],
            {},
        )
        return 2

    should_clear = args.clear
    if should_clear is None:
        should_clear = not (args.kg_only or args.questions_only)

    failures: List[Dict[str, Any]] = []
    verification: Dict[str, Any] = {}
    try:
        with Neo4jConnector() as connector:
            if should_clear:
                logger.warning("正在清除现有 Neo4j 数据")
                connector.clear_database()

            # Import all selected nodes before relationships so cross-file links resolve.
            for source, data in data_sources:
                import_knowledge_nodes(
                    connector,
                    data,
                    source,
                    args.batch_size,
                    failures,
                )
            # 端点标签映射：让关系 MATCH 带标签命中唯一约束索引（B7）。
            # 标签同样过白名单校验，因为它会被拼入 Cypher。
            id_to_label: Dict[Any, str] = {}
            for _, data in data_sources:
                for entity in data.get("entities", []):
                    entity_id = entity.get("id")
                    entity_type = entity.get("type", "")
                    if entity_id not in (None, "") and entity_type:
                        id_to_label[entity_id] = validate_node_label(entity_type)
            for source, data in data_sources:
                import_relationships(
                    connector,
                    data,
                    source,
                    args.relationship_batch_size,
                    failures,
                    id_to_label=id_to_label,
                )
            verification = verify_import(connector)
    except (Neo4jConnectorError, RuntimeError, ValueError) as exc:
        logger.error("导入中止: {}", type(exc).__name__)
        failures.append(
            {
                "source": "database",
                "kind": "operation",
                "index": 0,
                "type": "Neo4j",
                "reason": "database_or_configuration_error",
                "error_type": type(exc).__name__,
            }
        )

    write_failure_report(args.failure_report.resolve(), failures, verification)
    if failures:
        logger.error("导入结束，共 {} 条失败记录", len(failures))
        return 1
    logger.success("批量导入完成，未发现失败记录")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
