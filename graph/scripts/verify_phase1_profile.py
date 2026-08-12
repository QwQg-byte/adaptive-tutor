"""阶段 1 验收：用真实 Neo4j PROFILE 验证节点解析查询命中索引。

只读操作，不写库。输出各分支的执行计划算子摘要。
"""

import asyncio
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1] / "application" / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from database.neo4j_service import Neo4jService, neo4j_service  # noqa: E402


def collect_operators(plan, out):
    out.append(plan.get("operatorType", ""))
    for child in plan.get("children", []):
        collect_operators(child, out)


async def profile(service, description, query, params):
    async with service.driver.session(database=service.database) as session:
        result = await session.run("PROFILE " + query, params)
        await result.data()
        summary = await result.consume()
        operators = []
        collect_operators(summary.profile, operators)
        seeks = [op for op in operators if "IndexSeek" in op or "NodeUniqueIndexSeek" in op]
        scans = [op for op in operators if "AllNodesScan" in op]
        print(f"[{description}]")
        print(f"  算子: {', '.join(sorted(set(operators)))}")
        print(f"  索引Seek: {len(seeks)} 处 | AllNodesScan: {len(scans)} 处")
        return operators


async def main():
    await neo4j_service.connect()
    try:
        sub = Neo4jService._node_resolution_subquery("n")

        # 1. get_node_by_id 全查询（含兜底分支，允许兜底分支有扫描，
        #    但 KnowledgeNode/Question 分支必须是 IndexSeek）
        await profile(
            neo4j_service,
            "get_node_by_id 完整查询",
            sub + "RETURN coalesce(n.id, n.node_id, elementId(n)) as id",
            {"id": "NODE_001"},
        )

        # 2. 仅 KnowledgeNode 分支（核心热路径）
        await profile(
            neo4j_service,
            "KnowledgeNode 按 id 定位",
            "MATCH (n:KnowledgeNode) WHERE n.id = $id RETURN n.id",
            {"id": "NODE_001"},
        )

        # 3. 数字 node_id 双形态（B16）
        await profile(
            neo4j_service,
            "KnowledgeNode 按 node_id 双形态定位",
            "MATCH (n:KnowledgeNode) WHERE n.node_id = $id OR n.node_id = toInteger($id) RETURN n.id",
            {"id": "1"},
        )

        # 4. 关系导入的带标签端点定位（B7，模拟 import_data 查询形状）
        await profile(
            neo4j_service,
            "带标签关系端点 MATCH（导入形状）",
            "UNWIND $rows AS row MATCH (s:KnowledgeNode {id: row.f}) MATCH (t:KnowledgeNode {id: row.t}) RETURN count(*)",
            {"rows": [{"f": "NODE_001", "t": "NODE_002"}]},
        )

        # 5. 功能冒烟：get_node_by_id / get_node_relationships 真实调用
        node = await neo4j_service.get_node_by_id("NODE_001")
        print(f"[冒烟] get_node_by_id('NODE_001') -> {node['id'] if node else None}")
        rels = await neo4j_service.get_node_relationships("NODE_001")
        print(
            f"[冒烟] get_node_relationships -> {len(rels['relationships'])} 条, truncated={rels['truncated']}"
        )
    finally:
        await neo4j_service.close()


if __name__ == "__main__":
    asyncio.run(main())
