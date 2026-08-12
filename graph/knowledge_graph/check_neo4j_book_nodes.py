"""检查Neo4j中书籍数据的情况"""
from neo4j_connector import Neo4jConnector

connector = Neo4jConnector()

# 查询所有Reference节点
print("=" * 60)
print("Reference节点")
print("=" * 60)
ref_nodes = connector.execute_query("MATCH (r:Reference) RETURN r")
for node in ref_nodes:
    print(f"  ID: {node['r'].get('id', 'N/A')}")
    print(f"  Title: {node['r'].get('title', 'N/A')}")

# 查询前10个KnowledgePoint节点
print("\n" + "=" * 60)
print("KnowledgePoint节点（前10个）")
print("=" * 60)
kp_nodes = connector.execute_query("MATCH (k:KnowledgePoint) RETURN k LIMIT 10")
for i, node in enumerate(kp_nodes, 1):
    print(f"  {i}. ID: {node['k'].get('id', 'N/A'):15s} Name: {node['k'].get('name', 'N/A')}")

# 查询COVERS关系
print("\n" + "=" * 60)
print("COVERS关系（前10个）")
print("=" * 60)
covers_rels = connector.execute_query("""
    MATCH (r:Reference)-[c:COVERS]->(n)
    RETURN r.id as ref_id, n.id as node_id, labels(n)[0] as label
    LIMIT 10
""")
for i, rel in enumerate(covers_rels, 1):
    print(f"  {i}. {rel['ref_id']:30s} -> {rel['node_id']:15s} ({rel['label']})")

# 统计各类型节点有多少
print("\n" + "=" * 60)
print("各类型节点统计")
print("=" * 60)
stats = connector.get_statistics()
for node_stat in sorted(stats['nodes_by_label'], key=lambda x: x['label']):
    print(f"  {node_stat['label']:20s}: {node_stat['count']:5d}")

# 统计COVERS关系数量
print("\n" + "=" * 60)
print("关系统计")
print("=" * 60)
covers_count = connector.execute_query("""
    MATCH ()-[r:COVERS]->()
    RETURN count(r) as count
""")[0]['count']
print(f"  COVERS: {covers_count}")

for rel_stat in sorted(stats['relationships_by_type'], key=lambda x: x['type']):
    print(f"  {rel_stat['type']:20s}: {rel_stat['count']:5d}")

connector.close()
