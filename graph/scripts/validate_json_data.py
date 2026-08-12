"""校验项目 JSON 文件的语法和知识图谱基础结构。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_DIR = PROJECT_ROOT / "data"


def discover_json_files(paths: list[str]) -> list[Path]:
    """展开文件/目录参数；未传参数时扫描 data 目录。"""
    candidates = [Path(path) for path in paths] if paths else [DEFAULT_DATA_DIR]
    files: set[Path] = set()

    for candidate in candidates:
        path = candidate if candidate.is_absolute() else PROJECT_ROOT / candidate
        if path.is_file():
            if path.suffix.lower() == ".json":
                files.add(path.resolve())
        elif path.is_dir():
            files.update(item.resolve() for item in path.rglob("*.json") if item.is_file())
        else:
            raise FileNotFoundError(f"路径不存在: {candidate}")

    return sorted(files)


def validate_graph_document(path: Path, data: dict[str, Any]) -> list[str]:
    """校验包含 entities/relationships 的知识图谱文档。"""
    errors: list[str] = []
    entities = data.get("entities")
    relationships = data.get("relationships")

    if not isinstance(entities, list) or not isinstance(relationships, list):
        return errors

    entity_ids: set[str] = set()
    for index, entity in enumerate(entities, start=1):
        location = f"{path}: entities[{index}]"
        if not isinstance(entity, dict):
            errors.append(f"{location} 必须是对象")
            continue

        entity_id = entity.get("id")
        entity_type = entity.get("type")
        if not isinstance(entity_id, str) or not entity_id.strip():
            errors.append(f"{location} 缺少非空字符串 id")
        elif entity_id in entity_ids:
            errors.append(f"{location} 出现重复 id: {entity_id}")
        else:
            entity_ids.add(entity_id)

        if not isinstance(entity_type, str) or not entity_type.strip():
            errors.append(f"{location} 缺少非空字符串 type")

    for index, relationship in enumerate(relationships, start=1):
        location = f"{path}: relationships[{index}]"
        if not isinstance(relationship, dict):
            errors.append(f"{location} 必须是对象")
            continue

        rel_type = relationship.get("type")
        source = relationship.get("from") or relationship.get("source")
        target = relationship.get("to") or relationship.get("target")
        if not isinstance(rel_type, str) or not rel_type.strip():
            errors.append(f"{location} 缺少非空字符串 type")
        if not isinstance(source, str) or not source.strip():
            errors.append(f"{location} 缺少 from/source")
        if not isinstance(target, str) or not target.strip():
            errors.append(f"{location} 缺少 to/target")

    relationship_keys: set[str] = set()
    for index, relationship in enumerate(relationships, start=1):
        if not isinstance(relationship, dict):
            continue
        key = json.dumps(relationship, ensure_ascii=False, sort_keys=True)
        if key in relationship_keys:
            errors.append(f"{path}: relationships[{index}] 是完全重复的关系")
        else:
            relationship_keys.add(key)

    metadata = data.get("metadata")
    if isinstance(metadata, dict):
        expected_entities = metadata.get("total_entities")
        expected_relationships = metadata.get("total_relationships")
        if isinstance(expected_entities, int) and expected_entities != len(entities):
            errors.append(
                f"{path}: metadata.total_entities={expected_entities}，"
                f"实际为 {len(entities)}"
            )
        if isinstance(expected_relationships, int) and expected_relationships != len(relationships):
            errors.append(
                f"{path}: metadata.total_relationships={expected_relationships}，"
                f"实际为 {len(relationships)}"
            )

    return errors


def validate_file(path: Path) -> list[str]:
    try:
        with path.open("r", encoding="utf-8-sig") as handle:
            data = json.load(handle)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return [f"{path}: {type(exc).__name__}: {exc}"]

    if isinstance(data, dict):
        return validate_graph_document(path, data)
    return []


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="校验 JSON 语法；知识图谱文件额外校验实体、关系和 metadata 计数。"
    )
    parser.add_argument(
        "paths",
        nargs="*",
        help="要校验的 JSON 文件或目录；默认扫描项目 data 目录",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        files = discover_json_files(args.paths)
    except FileNotFoundError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 2

    errors: list[str] = []
    for path in files:
        errors.extend(validate_file(path))

    if errors:
        print(f"[FAIL] 已检查 {len(files)} 个 JSON 文件，发现 {len(errors)} 个问题：")
        for error in errors:
            print(f"  - {error}")
        return 1

    print(f"[OK] 已检查 {len(files)} 个 JSON 文件，语法与基础结构均有效")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
