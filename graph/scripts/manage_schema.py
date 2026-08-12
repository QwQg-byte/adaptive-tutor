"""Apply, validate, inspect or remove the project-owned Neo4j 5 Schema."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from knowledge_graph.neo4j_connector import Neo4jConnector  # noqa: E402
from knowledge_graph.schema_manager import SchemaManager  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("apply", "validate", "status", "drop"))
    parser.add_argument(
        "--timeout",
        type=int,
        default=300,
        help="等待索引上线的秒数（默认 300）",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="确认执行 drop；只删除本项目命名的 Schema 对象",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.action == "drop" and not args.yes:
        print("拒绝删除：drop 必须显式提供 --yes", file=sys.stderr)
        return 2

    with Neo4jConnector() as connector:
        manager = SchemaManager(connector)
        if args.action == "validate":
            output = {"validation": manager.validate_constraint_candidates()}
        elif args.action == "status":
            output = manager.get_schema_status()
        elif args.action == "apply":
            validation = manager.validate_constraint_candidates()
            manager.initialize_schema(args.timeout)
            output = {
                "action": "apply",
                "validation": validation,
                **manager.get_schema_status(),
            }
        else:
            manager.drop_all_indexes()
            manager.drop_all_constraints()
            output = {"action": "drop", **manager.get_schema_status()}

    print(json.dumps(output, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
