# -*- coding: utf-8 -*-
"""测试首页API"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from database.neo4j_service import neo4j_service


async def run_home_check():
    """测试首页API数据获取"""
    print("=" * 60)
    print("测试首页API")
    print("=" * 60)
    
    await neo4j_service.connect()
    try:
        # 1. 题目总数
        total_questions = (await neo4j_service.execute_query(
            "MATCH (q:Question) RETURN count(q) as count"
        ))[0]['count']
        print(f"\n[OK] 题目总数: {total_questions}")
        
        # 2. 难度分布
        difficulty_stats = await neo4j_service.execute_query("""
            MATCH (q:Question)
            WHERE q.difficulty IS NOT NULL
            RETURN q.difficulty as difficulty, count(q) as count
            ORDER BY count DESC
        """)
        print("\n[OK] 难度分布:")
        for d in difficulty_stats:
            print(f"  {d['difficulty']}: {d['count']}题")
        
        # 3. 一级分类分布
        category_stats = await neo4j_service.execute_query("""
            MATCH (q:Question)
            WHERE q.category1 IS NOT NULL AND q.category1 <> ''
            RETURN q.category1 as category, count(q) as count
            ORDER BY count DESC
            LIMIT 10
        """)
        print("\n[OK] 分类分布:")
        for c in category_stats:
            print(f"  {c['category']}: {c['count']}题")
        
        # 4. 热门知识点
        hot_kps = await neo4j_service.execute_query("""
            MATCH (q:Question)-[r:REQUIRES]->(kp:KnowledgeNode)
            WHERE kp.name IS NOT NULL
            RETURN kp.id as id, kp.name as name, count(q) as question_count
            ORDER BY question_count DESC
            LIMIT 10
        """)
        print("\n[OK] 热门知识点:")
        for kp in hot_kps:
            print(f"  {kp['name']}: {kp['question_count']}题")
        
        # 5. 推荐题目
        rec_questions = await neo4j_service.execute_query("""
            MATCH (q:Question)
            WHERE q.category1 IN ['语言基础', '算法基础', '数据结构', '图论', '动态规划']
            WITH q, rand() as r
            ORDER BY r
            RETURN q.id as id, q.name as name, q.difficulty as difficulty, 
                   q.category1 as category1, q.url as url
            LIMIT 6
        """)
        print("\n[OK] 推荐题目:")
        for q in rec_questions:
            print(f"  {q['id']}: {q['name']}")
        
        print("\n" + "=" * 60)
        print("[SUCCESS] API测试通过!")
        print("=" * 60)
        
    finally:
        await neo4j_service.close()


if __name__ == "__main__":
    asyncio.run(run_home_check())
