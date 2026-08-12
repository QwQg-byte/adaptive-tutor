"""检查图谱中知识点数据"""
import asyncio
import sys
sys.path.insert(0, '.')

from database.neo4j_service import neo4j_service


async def main():
    await neo4j_service.connect()
    # 检查各类型节点
    checks = [
        ("KnowledgeNode", "MATCH (n:KnowledgeNode) RETURN count(n) as count"),
        ("NODE_* 节点", "MATCH (n) WHERE n.id STARTS WITH 'NODE_' RETURN count(n) as count"),
        ("CHAP_* 节点", "MATCH (n) WHERE n.id STARTS WITH 'CHAP_' RETURN count(n) as count"),
        ("Question 节点", "MATCH (n:Question) RETURN count(n) as count"),
    ]
    
    for name, query in checks:
        result = await neo4j_service.execute_query(query)
        count = result[0]['count'] if result else 0
        print(f"{name}: {count}")
    
    # 检查REQUIRES关系详情
    print("\n=== REQUIRES关系示例 ===")
    req_query = """
    MATCH (q:Question)-[r:REQUIRES]->(kp)
    RETURN q.id as q_id, kp.id as kp_id, kp.name as kp_name, labels(kp)[0] as kp_type
    LIMIT 10
    """
    reqs = await neo4j_service.execute_query(req_query)
    for r in reqs:
        print(f"  {r.get('q_id')} -> {r.get('kp_id')} ({r.get('kp_type')}): {r.get('kp_name')}")
    
    await neo4j_service.close()


if __name__ == "__main__":
    asyncio.run(main())
