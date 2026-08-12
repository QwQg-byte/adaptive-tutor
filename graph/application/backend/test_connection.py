"""验证数据库连接和统计"""
import asyncio
import sys
sys.path.insert(0, '.')

from database.neo4j_service import neo4j_service


async def main():
    await neo4j_service.connect()
    print("连接成功！")
    stats = await neo4j_service.get_statistics()
    print("\n=== 节点统计 ===")
    for label, count in stats.get('nodes', {}).items():
        print(f"  {label}: {count}")
    print(f"\n  总节点数: {stats.get('total_nodes', 0)}")
    
    print("\n=== 关系统计 ===")
    for rel_type, count in stats.get('relationships', {}).items():
        print(f"  {rel_type}: {count}")
    print(f"\n  总关系数: {stats.get('total_relationships', 0)}")
    
    # 测试查询知识点
    kp_query = """
    MATCH (n:KnowledgeNode)
    RETURN n.id as id, n.name as name, n.node_type as node_type
    LIMIT 5
    """
    kps = await neo4j_service.execute_query(kp_query)
    print("\n=== 知识点示例 ===")
    for kp in kps:
        print(f"  {kp.get('id')}: {kp.get('name')} ({kp.get('node_type')})")
    
    # 测试查询题目
    q_query = """
    MATCH (q:Question)
    RETURN q.id as id, q.name as name, q.difficulty as difficulty
    LIMIT 5
    """
    questions = await neo4j_service.execute_query(q_query)
    print("\n=== 题目示例 ===")
    for q in questions:
        print(f"  {q.get('id')}: {q.get('name')} [{q.get('difficulty')}]")
    
    # 测试 REQUIRES 关系
    req_query = """
    MATCH (q:Question)-[r:REQUIRES]->(kp)
    RETURN q.id as q_id, kp.name as kp_name, r.weight as weight
    LIMIT 5
    """
    reqs = await neo4j_service.execute_query(req_query)
    print("\n=== REQUIRES关系示例 ===")
    if reqs:
        for r in reqs:
            print(f"  题目 {r.get('q_id')} -> 知识点 {r.get('kp_name')} (权重: {r.get('weight')})")
    else:
        print("  无REQUIRES关系，数据未导入")
    
    await neo4j_service.close()


if __name__ == "__main__":
    asyncio.run(main())
