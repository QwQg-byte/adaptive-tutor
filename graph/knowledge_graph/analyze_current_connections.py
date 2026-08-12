"""分析当前题目和知识点的关联情况"""
from neo4j_connector import Neo4jConnector

connector = Neo4jConnector()

print("=" * 70)
print("题目与知识点关联分析")
print("=" * 70)

# 1. 查看题目使用的数据结构
print("\n[1] 题目使用的数据结构（USES_STRUCTURE关系）")
print("=" * 70)
structure_questions = connector.execute_query("""
    MATCH (q:Question)-[u:USES_STRUCTURE]->(ds:DataStructure)
    RETURN ds.name as structure, count(q) as question_count
    ORDER BY question_count DESC
    LIMIT 10
""")
for item in structure_questions:
    print(f"  {item['structure']:20s}: {item['question_count']:3d} 道题目")

# 2. 查看题目使用的算法
print("\n[2] 题目使用的算法（USES_ALGORITHM关系）")
print("=" * 70)
algorithm_questions = connector.execute_query("""
    MATCH (q:Question)-[u:USES_ALGORITHM]->(a:Algorithm)
    RETURN a.name as algorithm, count(q) as question_count
    ORDER BY question_count DESC
""")
for item in algorithm_questions:
    print(f"  {item['algorithm']:20s}: {item['question_count']:3d} 道题目")

# 3. 查看书籍中的知识点
print("\n[3] 书籍知识点（前20个）")
print("=" * 70)
knowledge_points = connector.execute_query("""
    MATCH (kp:KnowledgePoint)
    RETURN kp.id as id, kp.name as name, kp.description as description
    ORDER BY kp.id
    LIMIT 20
""")
for kp in knowledge_points:
    print(f"  [{kp['id']:10s}] {kp['name']:20s}")

# 4. 查看书籍中的算法
print("\n[4] 书籍中的算法（前15个）")
print("=" * 70)
algorithms = connector.execute_query("""
    MATCH (a:Algorithm)
    RETURN a.id as id, a.name as name, a.category as category
    ORDER BY a.id
    LIMIT 15
""")
for algo in algorithms:
    print(f"  [{algo['id']:10s}] {algo['name']:20s} ({algo['category']})")

# 5. 查看书籍中的数据结构
print("\n[5] 书籍中的数据结构（前15个）")
print("=" * 70)
data_structures = connector.execute_query("""
    MATCH (ds:DataStructure)
    RETURN ds.id as id, ds.name as name
    ORDER BY ds.id
    LIMIT 15
""")
for ds in data_structures:
    print(f"  [{ds['id']:10s}] {ds['name']:20s}")

# 6. 查看题目与知识点的潜在连接（通过数据结构）
print("\n[6] 题目与知识点的潜在连接路径")
print("=" * 70)
potential_paths = connector.execute_query("""
    MATCH (q:Question)-[u:USES_STRUCTURE]->(ds:DataStructure)<-[r:RELATED_TO]-(kp:KnowledgePoint)
    RETURN q.name as question, ds.name as structure, kp.name as knowledge_point
    LIMIT 10
""")
for path in potential_paths:
    print(f"  题目: {path['question']}")
    print(f"    -> 使用: {path['structure']}")
    print(f"    -> 关联: {path['knowledge_point']}")
    print()

connector.close()
