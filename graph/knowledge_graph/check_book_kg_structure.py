"""检查书籍知识图谱的结构和连接"""
from neo4j_connector import Neo4jConnector

connector = Neo4jConnector()

print("=" * 70)
print("书籍知识图谱结构分析")
print("=" * 70)

# 1. 查询书籍节点及其直接连接的章节/算法/数据结构
print("\n[1] 书籍与其覆盖的节点")
print("=" * 70)
book_rels = connector.execute_query("""
    MATCH (r:Reference)-[c:COVERS]->(n)
    RETURN r.title as book, labels(n)[0] as node_type, n.name as name, n.id as id
    ORDER BY node_type, id
""")
book_count = 0
for rel in book_rels:
    if book_count == 0:
        print(f"  书籍: {rel['book']}")
        print("  覆盖节点:")
    book_count += 1
    print(f"    - [{rel['node_type']}] {rel['name']} (ID: {rel['id']})")

print(f"\n  总计: {book_count} 个COVERS关系")

# 2. 查询章节之间的PART_OF关系
print("\n[2] 知识点的层级关系 (PART_OF)")
print("=" * 70)
part_of_rels = connector.execute_query("""
    MATCH (a)-[r:PART_OF]->(b)
    RETURN labels(a)[0] as from_type, a.name as from_name,
           labels(b)[0] as to_type, b.name as to_name
    ORDER BY from_type, from_name
""")
for i, rel in enumerate(part_of_rels, 1):
    print(f"  {i}. [{rel['from_type']}] {rel['from_name']} -> PART_OF -> [{rel['to_type']}] {rel['to_name']}")

# 3. 查询算法之间的RELATED_TO关系
print("\n[3] 算法之间的关联 (RELATED_TO)")
print("=" * 70)
related_rels = connector.execute_query("""
    MATCH (a)-[r:RELATED_TO]->(b)
    RETURN labels(a)[0] as from_type, a.name as from_name,
           labels(b)[0] as to_type, b.name as to_name
    ORDER BY from_name
""")
for i, rel in enumerate(related_rels, 1):
    print(f"  {i}. [{rel['from_type']}] {rel['from_name']} -> RELATED_TO -> [{rel['to_type']}] {rel['to_name']}")

# 4. 查询算法/数据结构之间的BASED_ON关系
print("\n[4] 算法/数据结构之间的依赖关系 (BASED_ON)")
print("=" * 70)
based_on_rels = connector.execute_query("""
    MATCH (a)-[r:BASED_ON]->(b)
    RETURN labels(a)[0] as from_type, a.name as from_name,
           labels(b)[0] as to_type, b.name as to_name
    ORDER BY from_name
""")
for i, rel in enumerate(based_on_rels, 1):
    print(f"  {i}. [{rel['from_type']}] {rel['from_name']} -> BASED_ON -> [{rel['to_type']}] {rel['to_name']}")

# 5. 查询HAS_CONCEPT关系
print("\n[5] 概念关系 (HAS_CONCEPT)")
print("=" * 70)
has_concept_rels = connector.execute_query("""
    MATCH (a)-[r:HAS_CONCEPT]->(b)
    RETURN labels(a)[0] as from_type, a.name as from_name,
           labels(b)[0] as to_type, b.name as to_name
    ORDER BY from_name
""")
for i, rel in enumerate(has_concept_rels, 1):
    print(f"  {i}. [{rel['from_type']}] {rel['from_name']} -> HAS_CONCEPT -> [{rel['to_type']}] {rel['to_name']}")

# 6. 统计各节点的度数（连接数）
print("\n[6] 节点连接度数排行 (Top 20)")
print("=" * 70)
degree_query = """
MATCH (n)
OPTIONAL MATCH (n)-[r]->()
WITH n, count(r) as out_degree
OPTIONAL MATCH (n)<-[r]-( )
WITH n, out_degree, count(r) as in_degree
WITH n, out_degree, in_degree, out_degree + in_degree as total_degree
RETURN labels(n)[0] as type, n.name as name, out_degree, in_degree, total_degree
ORDER BY total_degree DESC
LIMIT 20
"""
degrees = connector.execute_query(degree_query)
print(f"  {'类型':<15} {'名称':<20} {'出度':>6} {'入度':>6} {'总度数':>8}")
print("  " + "-" * 65)
for deg in degrees:
    print(f"  [{deg['type']:<13}] {deg['name'][:18]:<20} {deg['out_degree']:>6} {deg['in_degree']:>6} {deg['total_degree']:>8}")

print("\n" + "=" * 70)
print("分析完成")
print("=" * 70)

connector.close()
