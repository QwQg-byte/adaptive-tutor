"""删除知识图谱 JSON 中完全相同的重复实体和关系。"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def deduplicate_entities(entities: list[Any]) -> tuple[list[Any], int]:
    result: list[Any] = []
    seen_by_id: dict[str, str] = {}
    removed = 0

    for entity in entities:
        if not isinstance(entity, dict) or not isinstance(entity.get("id"), str):
            result.append(entity)
            continue

        entity_id = entity["id"]
        fingerprint = canonical(entity)
        previous = seen_by_id.get(entity_id)
        if previous is None:
            seen_by_id[entity_id] = fingerprint
            result.append(entity)
        elif previous == fingerprint:
            removed += 1
        else:
            raise ValueError(f"实体 ID {entity_id!r} 重复但内容不同，拒绝自动合并")

    return result, removed


def deduplicate_relationships(relationships: list[Any]) -> tuple[list[Any], int]:
    result: list[Any] = []
    seen: set[str] = set()
    removed = 0

    for relationship in relationships:
        fingerprint = canonical(relationship)
        if fingerprint in seen:
            removed += 1
        else:
            seen.add(fingerprint)
            result.append(relationship)

    return result, removed


def write_atomically(path: Path, data: Any) -> None:
    descriptor, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
        text=True,
    )
    temp_path = Path(temp_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temp_path, path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="仅删除内容完全相同的重复项；冲突记录会中止，不自动覆盖。"
    )
    parser.add_argument("path", type=Path, help="知识图谱 JSON 文件")
    parser.add_argument("--apply", action="store_true", help="实际写回；默认只预览")
    args = parser.parse_args()

    path = args.path.resolve()
    try:
        with path.open("r", encoding="utf-8-sig") as handle:
            data = json.load(handle)
        if not isinstance(data, dict):
            raise ValueError("顶层必须是对象")

        entities, removed_entities = deduplicate_entities(data.get("entities", []))
        relationships, removed_relationships = deduplicate_relationships(
            data.get("relationships", [])
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1

    print(
        f"实体重复 {removed_entities} 条，关系重复 {removed_relationships} 条"
    )
    if not args.apply:
        print("仅预览；确认后添加 --apply")
        return 0

    data["entities"] = entities
    data["relationships"] = relationships
    metadata = data.get("metadata")
    if isinstance(metadata, dict):
        if isinstance(metadata.get("total_entities"), int):
            metadata["total_entities"] = len(entities)
        if isinstance(metadata.get("total_relationships"), int):
            metadata["total_relationships"] = len(relationships)

    write_atomically(path, data)
    print(f"[OK] 已更新 {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
