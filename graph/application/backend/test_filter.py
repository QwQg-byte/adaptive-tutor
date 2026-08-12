import asyncio

from database.neo4j_service import neo4j_service


async def main():
    await neo4j_service.connect()

    # 查看难度分布
    print('=== 难度分布 ===')
    diff_stats = await neo4j_service.execute_query('''
    MATCH (q:Question)
    WHERE q.difficulty IS NOT NULL
    RETURN q.difficulty as difficulty, count(q) as count
    ORDER BY count DESC
    ''')
    for d in diff_stats:
        print(f"  {d['difficulty']}: {d['count']}")

# 查看分类分布
    print('\n=== 分类分布 ===')
    cat_stats = await neo4j_service.execute_query('''
    MATCH (q:Question)
    WHERE q.category1 IS NOT NULL
    RETURN q.category1 as category, count(q) as count
    ORDER BY count DESC
    LIMIT 10
    ''')
    for c in cat_stats:
        print(f"  {c['category']}: {c['count']}")

# 测试筛选
    print('\n=== 测试筛选 category1=语言基础 ===')
    filtered = await neo4j_service.execute_query('''
    MATCH (q:Question)
    WHERE q.category1 = $category
    RETURN q.id as id, q.name as name, q.difficulty as difficulty, q.category1 as category1
    LIMIT 5
    ''', {'category': '语言基础'})
    for q in filtered:
        print(f"  {q['id']}: {q['name'][:30]}... [{q['difficulty']}]")

    await neo4j_service.close()


if __name__ == "__main__":
    asyncio.run(main())
