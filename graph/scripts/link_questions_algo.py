# -*- coding: utf-8 -*-
"""
link_questions_algo.py —— 把码蹄集题目按分类关联到算法设计课程的知识点

原有题目→知识点 REQUIRES 边是按数据结构课的分类映射生成的，
本脚本按 category1/category2 追加到新导入的算法课知识点（REQUIRES，weight 0.85）。

用法:
    python scripts/link_questions_algo.py           # 干跑预览
    python scripts/link_questions_algo.py --apply   # 写入 matiji_knowledge_graph.json（自动备份）

写入后需重建数据库: python import_data.py
"""
import json
import re
import sys
import shutil
import argparse
from pathlib import Path
from collections import Counter

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding='utf-8')
    except Exception:
        pass

ROOT = Path(__file__).parent.parent
MATIJI = ROOT / 'data' / 'processed' / 'matiji_knowledge_graph.json'
KG = ROOT / 'data' / 'processed' / 'knowledge_graph_v3' / 'knowledge_graph.json'

# category2（归一化后）→ 算法课知识点名称
CAT2_MAP = {
    '线性DP': ['动态规划'],
    '背包DP': ['0/1背包问题（动态规划）', '完全背包和多重背包问题'],
    '区间DP': ['矩阵连乘问题'],
    '状压DP': ['旅行商问题（动态规划）'],
    '数位DP': ['动态规划'],
    '树形DP': ['动态规划'],
    '概率DP': ['动态规划'],
    '计数DP': ['动态规划'],
    '动态DP': ['动态规划'],
    'DP优化': ['动态规划'],
    'DAG上的DP': ['动态规划'],
    '记忆化搜索': ['动态规划'],
    '贪心': ['贪心法'],
    '递推 | 递归 | 分治': ['递归算法设计', '分治法'],
    '前缀和 | 差分': ['前缀和数组'],
    '二分 | 三分': ['二分查找'],
    '枚举': ['穷举法'],
    '最短路': ['Dijkstra算法'],
    '最小生成树': ['Prim算法', 'Kruskal算法'],
    '网络流': ['网络流'],
    '凸包': ['凸包问题'],
    '平面最近点对': ['最近点对问题'],
    '计算几何基础': ['向量运算'],
    '启发式搜索': ['A*算法'],
    '连通性相关': ['并查集'],
}
# category1 兜底：该大类的所有题目都补一条到方法级知识点
CAT1_MAP = {
    '动态规划': ['动态规划'],
    '计算几何': ['向量运算'],
}

WEIGHT = 0.85
METHOD = 'algo_category_mapping'


def norm(cat: str) -> str:
    """归一化分类名：去掉换行和 (2)/(3) 后缀"""
    if not cat:
        return ''
    return re.sub(r'\s*\(\d+\)\s*$', '', cat.replace('\n', ' ').strip()).strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true', help='实际写入（默认干跑）')
    args = ap.parse_args()

    kg = json.load(open(KG, encoding='utf-8'))
    name_to_id = {e['name']: e['id'] for e in kg['entities'] if e.get('type') == 'KnowledgeNode'}

    # 校验映射目标都存在
    missing = [n for names in list(CAT2_MAP.values()) + list(CAT1_MAP.values())
               for n in names if n not in name_to_id]
    if missing:
        sys.exit(f"[错误] 映射目标不存在于知识图谱: {set(missing)}")

    data = json.load(open(MATIJI, encoding='utf-8'))
    questions = [e for e in data['entities'] if e.get('type') == 'Question']
    existing = {(r.get('from') or r.get('source'), r.get('to') or r.get('target'))
                for r in data['relationships'] if r.get('type') == 'REQUIRES'}

    new_rels = []
    stats = Counter()
    for q in questions:
        c1, c2 = norm(q.get('category1')), norm(q.get('category2'))
        targets = list(CAT2_MAP.get(c2, []))
        for extra in CAT1_MAP.get(c1, []):
            if extra not in targets:
                targets.append(extra)
        for name in targets:
            key = (q['id'], name_to_id[name])
            if key in existing:
                continue
            existing.add(key)
            new_rels.append({
                'type': 'REQUIRES', 'from': q['id'], 'to': name_to_id[name],
                'attributes': {'weight': WEIGHT, 'match_method': METHOD},
            })
            stats[name] += 1

    print(f"新增题目→算法知识点关联: {len(new_rels)} 条，覆盖 {len(stats)} 个知识点")
    for name, n in stats.most_common():
        print(f"  {name}: {n} 题")

    if not args.apply:
        print("\n[dry-run] 未写入。执行 --apply 生效，然后 python import_data.py")
        return

    shutil.copy2(MATIJI, MATIJI.with_suffix('.json.bak'))
    data['relationships'].extend(new_rels)
    meta = data.setdefault('metadata', {})
    meta['total_relationships'] = len(data['relationships'])
    json.dump(data, open(MATIJI, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    print(f"\n[完成] 已写入 {MATIJI}（备份 .bak）")
    print("下一步：python import_data.py")


if __name__ == '__main__':
    main()
