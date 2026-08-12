"""
路径规划相关API
"""
from fastapi import APIRouter, HTTPException, Query
from loguru import logger
from database.neo4j_service import neo4j_service
from database.neo4j_exceptions import Neo4jServiceError
from database.models import PathRequest, PathModel, PlanRequest, PlanData, ResponseModel, TypedResponse

router = APIRouter(prefix="/path", tags=["学习路径"])


async def _resolve_knowledge_node(target: str):
    """按业务ID（NODE_xxx）或名称解析知识点，返回 {id, name} 或 None"""
    query = """
    MATCH (n:KnowledgeNode)
    WHERE n.id = $target OR n.node_id = $target OR n.name = $target
    RETURN coalesce(n.id, n.node_id, elementId(n)) as id, n.name as name
    ORDER BY CASE WHEN n.id = $target OR n.node_id = $target THEN 0 ELSE 1 END,
             n.id
    LIMIT 1
    """
    result = await neo4j_service.execute_query(query, {"target": target})
    return result[0] if result else None


async def _fetch_prerequisite_subgraph(target_id: str, max_depth: int):
    """
    获取目标知识点的前置依赖子图

    Returns:
        nodes: {业务ID: {id, name, depth}}，depth 为距目标的最短层级（目标为0）
        edges: [(依赖者ID, 前置ID)]
    """
    query = f"""
    MATCH path = (t:KnowledgeNode)-[:PREREQUISITE*1..{max_depth}]->(p:KnowledgeNode)
    WHERE coalesce(t.id, t.node_id, elementId(t)) = $target_id
    UNWIND range(0, size(relationships(path)) - 1) as i
    WITH nodes(path)[i] as a, nodes(path)[i+1] as b, i + 1 as prereq_depth
    RETURN DISTINCT coalesce(a.id, a.node_id, elementId(a)) as from_id,
           coalesce(b.id, b.node_id, elementId(b)) as to_id,
           b.name as to_name, min(prereq_depth) as depth
    """
    results = await neo4j_service.execute_query(query, {"target_id": target_id})

    nodes = {}
    edges = set()
    for row in results:
        edges.add((row['from_id'], row['to_id']))
        # 记录前置节点的最小深度
        nid = row['to_id']
        if nid not in nodes or row['depth'] < nodes[nid]['depth']:
            nodes[nid] = {'id': nid, 'name': row['to_name'], 'depth': row['depth']}
    return nodes, list(edges)


def _prune_and_sort(target, sub_nodes, edges, mastered: set):
    """
    从子图生成学习顺序：
    1. 从目标出发遍历，跳过已掌握节点（不展开其前置 → 纯前置被自动裁剪）
    2. 容环拓扑排序（数据中存在双向 PREREQUISITE），前置在前、目标在后

    Returns:
        ordered: 排好序的业务ID列表（含目标，在最后）
        skipped: 被裁剪的已掌握节点ID集合
        dep_map: {节点ID: 计划内直接前置ID列表}
    """
    # 邻接表：依赖者 → 前置
    adj = {}
    for f, t in edges:
        adj.setdefault(f, set()).add(t)

    # 第一步：从目标 BFS，跳过已掌握节点
    included = {target['id']}
    skipped = set()
    queue = [target['id']]
    while queue:
        cur = queue.pop(0)
        for pre in adj.get(cur, ()):
            if pre in mastered:
                skipped.add(pre)
                continue  # 不展开已掌握节点的前置
            if pre not in included:
                included.add(pre)
                queue.append(pre)

    # 第二步：容环 Kahn 拓扑排序（学习顺序 = 前置在前）
    # indegree[x] = x 在计划内的未学前置数量
    indeg = {n: 0 for n in included}
    dependents = {n: [] for n in included}  # 前置 → 依赖者
    dep_map = {n: [] for n in included}
    for f, t in edges:
        if f in included and t in included:
            indeg[f] += 1
            dependents[t].append(f)
            dep_map[f].append(t)

    def depth_of(nid):
        if nid == target['id']:
            return 0
        return sub_nodes.get(nid, {}).get('depth', 0)

    # 深度大（更基础）优先出队，顺序更符合直觉
    ordered = []
    remaining = set(included)
    ready = sorted([n for n in remaining if indeg[n] == 0],
                   key=lambda n: (-depth_of(n), n))
    while remaining:
        if not ready:
            # 有环：选未学前置最少的节点强制出队（打破环）
            pick = min(remaining, key=lambda n: (indeg[n], -depth_of(n), n))
            ready = [pick]
        cur = ready.pop(0)
        if cur not in remaining:
            continue
        remaining.discard(cur)
        ordered.append(cur)
        for dep in dependents.get(cur, ()):
            if dep in remaining:
                indeg[dep] -= 1
                if indeg[dep] <= 0:
                    ready.append(dep)
        ready.sort(key=lambda n: (-depth_of(n), n))

    # 环中节点可能被强制排到目标之后，目标固定移到最后一步
    if target['id'] in ordered:
        ordered.remove(target['id'])
        ordered.append(target['id'])

    return ordered, skipped, dep_map


async def _fetch_questions_for_nodes(
    node_ids: list,
    per_node: int,
    difficulty_preference: str = "balanced",
):
    """批量获取知识点推荐题，综合训练强度、关系权重和通过率排序。"""
    if not node_ids or per_node <= 0:
        return {}
    query = """
    MATCH (q:Question)-[r:REQUIRES]->(kp)
    WHERE coalesce(kp.id, kp.node_id, elementId(kp)) IN $ids
    WITH coalesce(kp.id, kp.node_id, elementId(kp)) as kid,
         q, coalesce(r.weight, 0) as weight,
         CASE $difficulty_preference
             WHEN 'foundation' THEN CASE q.difficulty
                 WHEN '简单' THEN 0 WHEN '中等' THEN 1
                 WHEN '困难' THEN 2 WHEN '星耀' THEN 3 ELSE 4 END
             WHEN 'challenge' THEN CASE q.difficulty
                 WHEN '困难' THEN 0 WHEN '星耀' THEN 1
                 WHEN '中等' THEN 2 WHEN '简单' THEN 3 ELSE 4 END
             ELSE CASE q.difficulty
                 WHEN '中等' THEN 0 WHEN '简单' THEN 1
                 WHEN '困难' THEN 2 WHEN '星耀' THEN 3 ELSE 4 END
         END as dorder
    ORDER BY dorder ASC, weight DESC,
             CASE WHEN $difficulty_preference = 'challenge'
                  THEN coalesce(toFloat(q.pass_rate), 100.0) END ASC,
             CASE WHEN $difficulty_preference <> 'challenge'
                  THEN coalesce(toFloat(q.pass_rate), 0.0) END DESC,
             q.id ASC
    WITH kid, collect({
        id: q.id, name: q.name, difficulty: q.difficulty,
        pass_rate: q.pass_rate, url: q.url,
        category1: q.category1, category2: q.category2
    })[0..$per_node] as questions
    RETURN kid, questions
    """
    results = await neo4j_service.execute_query(
        query,
        {
            "ids": node_ids,
            "per_node": per_node,
            "difficulty_preference": difficulty_preference,
        },
    )
    return {row['kid']: row['questions'] for row in results}


@router.post("/plan", response_model=TypedResponse[PlanData])
async def generate_learning_plan(request: PlanRequest):
    """
    生成学习计划：目标知识点的前置依赖子图 → 拓扑排序 → 线性学习清单

    - 支持传入已掌握知识点列表（mastered），自动跳过它们及其纯前置
    - 每个学习步骤附带推荐练习题（按难度由易到难）
    """
    try:
        target = await _resolve_knowledge_node(request.target)
        if not target:
            raise HTTPException(status_code=404, detail=f"未找到知识点: {request.target}")

        mastered = set(request.mastered or [])
        completed = set(request.completed or []) - mastered
        if target['id'] in mastered:
            return ResponseModel(
                success=True,
                message="目标知识点已掌握，无需规划",
                data={"target": target, "steps": [], "total_steps": 0,
                      "mastered_skipped": [], "already_mastered": True}
            )
        if target['id'] in completed:
            return ResponseModel(
                success=True,
                message="目标知识点已在当前计划中完成",
                data={"target": target, "steps": [], "total_steps": 0,
                      "mastered_skipped": [], "completed_skipped": [],
                      "already_mastered": False, "already_completed": True}
            )

        sub_nodes, edges = await _fetch_prerequisite_subgraph(target['id'], request.max_depth)
        ordered, skipped, dep_map = _prune_and_sort(
            target,
            sub_nodes,
            edges,
            mastered | completed,
        )

        # 批量取题
        questions_map = await _fetch_questions_for_nodes(
            ordered,
            request.questions_per_step,
            request.difficulty_preference,
        )

        # 组装步骤
        name_map = {nid: info['name'] for nid, info in sub_nodes.items()}
        name_map[target['id']] = target['name']
        position = {nid: i for i, nid in enumerate(ordered)}
        steps = []
        for order, nid in enumerate(ordered, start=1):
            # 数据中存在双向 PREREQUISITE（环），只展示排在当前步骤之前的前置，
            # 保证清单读起来自洽：前置一定在前面的步骤里
            prereqs = [p for p in dep_map.get(nid, [])
                       if p in position and position[p] < position[nid]]
            steps.append({
                "order": order,
                "id": nid,
                "name": name_map.get(nid, nid),
                "depth": 0 if nid == target['id'] else sub_nodes.get(nid, {}).get('depth', 0),
                "is_target": nid == target['id'],
                "prerequisites": [
                    {"id": p, "name": name_map.get(p, p)} for p in prereqs
                ],
                "questions": questions_map.get(nid, [])
            })

        mastered_skipped = skipped & mastered
        completed_skipped = skipped & completed
        skipped_info = [{"id": s, "name": name_map.get(s, s)} for s in sorted(mastered_skipped)]
        completed_info = [{"id": s, "name": name_map.get(s, s)} for s in sorted(completed_skipped)]
        logger.info(f"📋 学习计划: target={target['name']}, steps={len(steps)}, "
                    f"mastered={len(skipped_info)}, completed={len(completed_info)}, "
                    f"depth={request.max_depth}, preference={request.difficulty_preference}")

        return ResponseModel(
            success=True,
            message=f"学习计划生成成功，共 {len(steps)} 步"
                    + (f"（已跳过 {len(skipped_info)} 个已掌握、{len(completed_info)} 个已完成知识点）"
                       if skipped_info or completed_info else ""),
            data={
                "target": target,
                "total_steps": len(steps),
                "steps": steps,
                "mastered_skipped": skipped_info,
                "completed_skipped": completed_info,
                "difficulty_preference": request.difficulty_preference,
                "already_mastered": False,
                "already_completed": False,
            }
        )
    except HTTPException:
        raise
    except Neo4jServiceError:
        raise
    except Exception as e:
        logger.error(f"生成学习计划失败: {e}")
        raise HTTPException(status_code=500, detail="生成学习计划失败")


@router.post("/shortest", response_model=TypedResponse[PathModel])
async def find_shortest_path(request: PathRequest):
    """
    查找两个节点之间的最短路径
    
    Args:
        request: 路径请求（起始节点、目标节点、最大深度）
        
    Returns:
        最短路径（节点和关系）
    """
    try:
        # 旧链接中的 elementId 含冒号；业务 ID 和名称走统一解析。
        uses_legacy_id = ':' in request.start or ':' in request.end
        logger.info(
            "最短路径请求: start={}, end={}, max_depth={}, legacy_id={}",
            request.start,
            request.end,
            request.max_depth,
            uses_legacy_id,
        )
        if uses_legacy_id:
            path_data = await neo4j_service.find_shortest_path(
                start_id=request.start,
                end_id=request.end,
                max_depth=request.max_depth
            )
        else:
            path_data = await neo4j_service.get_knowledge_path(
                start_knowledge=request.start,
                target_knowledge=request.end,
                max_depth=request.max_depth,
            )
        
        if not path_data:
            raise HTTPException(
                status_code=404, 
                detail="未找到路径，请检查节点是否存在或尝试增加最大深度"
            )
        
        # 转换为模型
        path = PathModel(
            nodes=path_data['nodes'],
            relationships=path_data['relationships'],
            length=len(path_data['nodes']) - 1
        )
        
        return ResponseModel(
            success=True,
            message=f"找到最短路径，长度: {path.length}",
            data=path
        )
    except HTTPException:
        raise
    except Neo4jServiceError:
        raise
    except Exception as e:
        logger.error(f"查找最短路径失败: {e}")
        raise HTTPException(status_code=500, detail="查找最短路径失败")


@router.get("/learning/{knowledge_name:path}", response_model=ResponseModel)
async def get_learning_path(
    knowledge_name: str,
    max_depth: int = Query(3, ge=1, le=10),
):
    """
    获取知识点的学习路径（前置知识）
    
    Args:
        knowledge_name: 知识点名称
        max_depth: 查找深度，默认3
        
    Returns:
        学习路径（从基础到目标）
    """
    try:
        # 查找当前 Schema 中的 KnowledgeNode。
        query = """
        MATCH (target:KnowledgeNode)
        WHERE target.id = $name OR target.node_id = $name OR target.name = $name
        RETURN coalesce(target.id, target.node_id, elementId(target)) as id
        ORDER BY CASE WHEN target.id = $name OR target.node_id = $name THEN 0 ELSE 1 END,
                 target.id
        LIMIT 1
        """
        result = await neo4j_service.execute_query(query, {"name": knowledge_name})
        
        if not result:
            raise HTTPException(
                status_code=404,
                detail=f"未找到知识点: {knowledge_name}"
            )
        
        target_id = result[0]['id']
        
        # 查找前置路径：PREREQUISITE 方向为 依赖者→被依赖者
        # 要从 target 出发沿 PREREQUISITE 查找它依赖的前置知识
        # 反向节点顺序，使显示为: 前置知识 → ... → 目标
        # 
        # 策略：分两步查询
        # 第一步：先获取所有深度下最优路径（每个深度取1条最短路径）
        # 第二步：如果还不够，再取更长的路径作为补充
        query = f"""
        MATCH path = (target:KnowledgeNode)-[:PREREQUISITE*1..{max_depth}]->(prereq:KnowledgeNode)
        WHERE coalesce(target.id, target.node_id, elementId(target)) = $target_id
        WITH path, length(path) as depth
        RETURN reverse([node in nodes(path) | {{
            id: coalesce(node.id, node.node_id, elementId(node)),
            name: node.name,
            type: labels(node)[0],
            properties: properties(node)
        }}]) as nodes,
        reverse([rel in relationships(path) | {{
            type: type(rel),
            properties: properties(rel)
        }}]) as relationships,
        depth
        ORDER BY length(path) ASC
        LIMIT 30
        """
        
        results = await neo4j_service.execute_query(query, {"target_id": target_id})
        
        if not results:
            return ResponseModel(
                success=True,
                message=f"未找到 {knowledge_name} 的前置知识",
                data=[]
            )
        
        # 转换为路径模型
        paths = []
        for result in results:
            path = PathModel(
                nodes=result['nodes'],
                relationships=result['relationships'],
                length=len(result['nodes']) - 1
            )
            paths.append(path)
        
        return ResponseModel(
            success=True,
            message=f"找到 {len(paths)} 条学习路径（来自 {len(set(p.get('depth', 0) for p in results if 'depth' in p))} 个不同深度）",
            data=paths
        )
    except HTTPException:
        raise
    except Neo4jServiceError:
        raise
    except Exception as e:
        logger.error(f"获取学习路径失败: {e}")
        raise HTTPException(status_code=500, detail="获取学习路径失败")


@router.get("/related/{node_id}", response_model=ResponseModel)
async def get_related_nodes(
    node_id: str,
    limit: int = Query(20, ge=1, le=100),
):
    """
    获取相关节点（基于关系）
    
    Args:
        node_id: 节点ID
        limit: 返回数量限制
        
    Returns:
        相关节点列表
    """
    try:
        # 获取直接相关的节点；只保留业务节点类型（B18），排除
        # Category/Difficulty/NodeType 等分类型节点带来的噪声，
        # 并按关系类型和名称排序，使结果确定、可复现。
        query = """
        MATCH (a)-[r]-(b)
        WHERE (a.id = $id OR a.node_id = $id OR elementId(a) = $id)
          AND (b:KnowledgeNode OR b:Chapter OR b:Question)
        WITH DISTINCT coalesce(b.id, b.node_id, elementId(b)) as id,
             properties(b) as properties,
             type(r) as relationship,
             coalesce(b.name, b.title, '') as sort_name
        RETURN id, properties, relationship
        ORDER BY relationship, sort_name
        LIMIT $limit
        """

        results = await neo4j_service.execute_query(query, {
            "id": node_id,
            "limit": limit
        })
        
        related_nodes = []
        for result in results:
            node = dict(result['properties'])
            node['id'] = result['id']
            node['relationship'] = result['relationship']
            related_nodes.append(node)
        
        return ResponseModel(
            success=True,
            message=f"找到 {len(related_nodes)} 个相关节点",
            data=related_nodes
        )
    except Neo4jServiceError:
        raise
    except Exception as e:
        logger.error(f"获取相关节点失败: {e}")
        raise HTTPException(status_code=500, detail="获取相关节点失败")


@router.get("/dependencies/{knowledge_name:path}", response_model=ResponseModel)
async def get_knowledge_dependencies(
    knowledge_name: str,
    depth: int = Query(4, ge=1, le=10),
):
    """
    获取知识点的依赖关系（前置和后续）
    
    Args:
        knowledge_name: 知识点名称
        depth: 追溯深度，默认4（查找4层以内的前置/后续关系）
        
    Returns:
        依赖关系（前置知识和后续知识）
    """
    try:
        # 前置与后续依赖在一次查询中返回，且只遍历 PREREQUISITE。
        query = f"""
        MATCH (target:KnowledgeNode)
        WHERE target.id = $name OR target.node_id = $name OR target.name = $name
        WITH target,
             CASE WHEN target.id = $name OR target.node_id = $name
                  THEN 0 ELSE 1 END AS priority
        ORDER BY priority, target.id
        LIMIT 1
        CALL {{
            WITH target
            OPTIONAL MATCH (target)-[:PREREQUISITE*1..{depth}]->(prereq:KnowledgeNode)
            RETURN collect(DISTINCT CASE WHEN prereq IS NULL THEN null ELSE {{
                id: coalesce(prereq.id, prereq.node_id, elementId(prereq)),
                name: prereq.name,
                type: labels(prereq)[0]
            }} END) AS prerequisites
        }}
        CALL {{
            WITH target
            OPTIONAL MATCH (next:KnowledgeNode)-[:PREREQUISITE*1..{depth}]->(target)
            RETURN collect(DISTINCT CASE WHEN next IS NULL THEN null ELSE {{
                id: coalesce(next.id, next.node_id, elementId(next)),
                name: next.name,
                type: labels(next)[0]
            }} END) AS next_knowledge
        }}
        RETURN coalesce(target.id, target.node_id, elementId(target)) AS target_id,
               prerequisites, next_knowledge
        """
        rows = await neo4j_service.execute_query(query, {"name": knowledge_name})
        if not rows:
            raise HTTPException(status_code=404, detail=f"未找到知识点: {knowledge_name}")
        prerequisites = rows[0]["prerequisites"]
        next_knowledge = rows[0]["next_knowledge"]
        
        return ResponseModel(
            success=True,
            message=f"获取 {knowledge_name} 的依赖关系成功",
            data={
                "target": {"id": rows[0]["target_id"], "name": knowledge_name},
                "prerequisites": prerequisites,  # 前置知识
                "next": next_knowledge           # 后续知识
            }
        )
    except Neo4jServiceError:
        raise
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取依赖关系失败: {e}")
        raise HTTPException(status_code=500, detail="获取依赖关系失败")
