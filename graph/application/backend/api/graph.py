"""
图谱相关API
包括图谱数据、节点查询、题目与知识点匹配等
测试端点是否正确加载
"""
from datetime import date
from time import monotonic
from typing import Any, Dict, Literal
import asyncio

from fastapi import APIRouter, HTTPException, Query
from loguru import logger
from database.neo4j_service import neo4j_service
from database.neo4j_exceptions import Neo4jServiceError
from database.models import (
    GraphDataModel,
    GraphFragmentRequest,
    NodeDetailModel,
    StatisticsModel,
    ResponseModel,
    TypedResponse,
    QuestionListData,
    QuestionDetailData,
)
from database.cypher_security import ALLOWED_NODE_LABELS, validate_node_labels
from config import settings

router = APIRouter(prefix="/graph", tags=["图谱管理"])

MAX_OFFSET_PAGINATION_SKIP = 10_000
RECOMMENDATION_CATEGORIES = [
    "语言基础",
    "算法基础",
    "数据结构",
    "图论",
    "动态规划",
]

# 首页聚合数据进程内缓存（Q5）—— 同统计缓存，默认 60 秒 TTL
_home_data_cache: Dict[str, Any] = {}
_home_data_cache_expires_at: float = 0.0
_home_data_lock = asyncio.Lock()


def _knowledge_lookup_predicate(value: str, variable: str) -> str:
    """Choose an index-friendly locator for the current KnowledgeNode IDs."""
    if ":" in value:
        return f"elementId({variable}) = $id"
    if value.startswith("NODE_"):
        return f"{variable}.id = $id"
    if value.isdigit():
        # node_id 在库中可能是字符串或整数，两种形态都兼容（B16）
        return f"({variable}.node_id = $id OR {variable}.node_id = toInteger($id))"
    return f"{variable}.name = $id"


@router.get("/data", response_model=TypedResponse[GraphDataModel])
async def get_graph_data(
    limit: int = Query(2000, ge=1, le=2000),
    node_types: str = Query(None, max_length=200),
):
    """
    获取图谱数据
    
    Args:
        limit: 节点数量限制，默认1000
        node_types: 节点类型过滤，逗号分隔（如 "KnowledgeNode,Chapter"）
        
    Returns:
        图谱数据（节点、边、统计信息）
    """
    try:
        # 解析节点类型
        types_list = None
        if node_types:
            types_list = validate_node_labels(node_types.split(','))
        
        data = await neo4j_service.get_graph_data(limit=limit, node_types=types_list)
        
        # 转换为模型
        graph_data = GraphDataModel(
            nodes=data['nodes'],
            edges=data['edges'],
            statistics=data['statistics']
        )
        
        return ResponseModel(
            success=True,
            message=f"获取图谱数据成功，共 {len(data['nodes'])} 个节点，{len(data['edges'])} 条边",
            data=graph_data
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Neo4jServiceError:
        raise
    except Exception as e:
        logger.error(f"获取图谱数据失败: {e}")
        raise HTTPException(status_code=500, detail="获取图谱数据失败")


@router.get("/statistics", response_model=TypedResponse[StatisticsModel])
async def get_statistics():
    """
    获取图谱统计信息
    
    Returns:
        节点数量、关系数量、类型分布等统计信息
    """
    try:
        stats = await neo4j_service.get_statistics()
        
        # 转换为模型
        statistics = StatisticsModel(
            total_nodes=stats.get('total_nodes', 0),
            total_relationships=stats.get('total_relationships', 0),
            nodes=stats.get('nodes', {}),
            relationships=stats.get('relationships', {}),
            labels=stats.get('labels', []),
            relationship_types=stats.get('relationship_types', [])
        )
        
        return ResponseModel(
            success=True,
            message="获取统计信息成功",
            data=statistics
        )
    except Neo4jServiceError:
        raise
    except Exception as e:
        logger.error(f"获取统计信息失败: {e}")
        raise HTTPException(status_code=500, detail="获取统计信息失败")


@router.post("/nodes/fragment", response_model=ResponseModel)
async def get_graph_fragment(request: GraphFragmentRequest):
    """按业务 ID 批量加载节点及这些节点之间的直接关系。"""
    try:
        data = await neo4j_service.get_graph_fragment(
            request.node_ids,
            relationship_types=request.relationship_types,
        )
        return ResponseModel(
            success=True,
            message=f"加载了 {len(data['nodes'])} 个节点、{len(data['edges'])} 条关系",
            data=data,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Neo4jServiceError:
        raise
    except Exception as e:
        logger.error(f"获取图谱片段失败: {e}")
        raise HTTPException(status_code=500, detail="获取图谱片段失败")


@router.get("/node/{node_id}", response_model=TypedResponse[NodeDetailModel])
async def get_node_detail(
    node_id: str,
    direction: Literal["in", "out", "both"] = "both",
):
    """
    获取节点详情
    
    Args:
        node_id: 节点ID
        direction: 关系方向（in/out/both），默认both
        
    Returns:
        节点及其关系
    """
    try:
        # 获取节点
        node = await neo4j_service.get_node_by_id(node_id)
        if not node:
            raise HTTPException(status_code=404, detail=f"节点不存在: {node_id}")
        
        # 获取关系（带上限保护高度数节点，超限时提示截断）
        relationship_data = await neo4j_service.get_node_relationships(node_id, direction)
        relationships = relationship_data["relationships"]

        # 构建详情
        node_detail = NodeDetailModel(
            node=node,
            relationships=relationships
        )

        message = "获取节点详情成功"
        if relationship_data["truncated"]:
            message = f"获取节点详情成功（关系较多，仅返回前 {len(relationships)} 条）"

        return ResponseModel(
            success=True,
            message=message,
            data=node_detail
        )
    except HTTPException:
        raise
    except Neo4jServiceError:
        raise
    except Exception as e:
        logger.error(f"获取节点详情失败: {e}")
        raise HTTPException(status_code=500, detail="获取节点详情失败")


@router.get("/node/{node_id}/neighbors", response_model=ResponseModel)
async def get_node_neighbors(
    node_id: str,
    limit: int = Query(30, ge=1, le=100),
    relationship_types: str = Query(None, max_length=500),
):
    """按需获取一个节点周围的有限图谱片段。"""
    try:
        relationship_type_list = []
        if relationship_types:
            relationship_type_list = list(
                dict.fromkeys(
                    value.strip()
                    for value in relationship_types.split(",")
                    if value.strip()
                )
            )
            if len(relationship_type_list) > 20:
                raise HTTPException(status_code=400, detail="一次最多筛选 20 种关系类型")

        node = await neo4j_service.get_node_by_id(node_id)
        if not node:
            raise HTTPException(status_code=404, detail=f"节点不存在: {node_id}")

        data = await neo4j_service.get_node_neighbors(
            node_id,
            limit=limit,
            relationship_types=relationship_type_list,
        )
        return ResponseModel(
            success=True,
            message=f"加载了 {len(data['nodes'])} 个邻居节点",
            data=data,
        )
    except HTTPException:
        raise
    except Neo4jServiceError:
        raise
    except Exception as e:
        logger.error(f"获取节点邻居失败: {e}")
        raise HTTPException(status_code=500, detail="获取节点邻居失败")


@router.get("/labels", response_model=ResponseModel)
async def get_labels():
    """
    获取所有节点标签（类型）
    
    Returns:
        节点类型列表
    """
    try:
        stats = await neo4j_service.get_statistics()
        
        return ResponseModel(
            success=True,
            message="获取节点标签成功",
            data=[label for label in stats.get('labels', []) if label in ALLOWED_NODE_LABELS]
        )
    except Neo4jServiceError:
        raise
    except Exception as e:
        logger.error(f"获取节点标签失败: {e}")
        raise HTTPException(status_code=500, detail="获取节点标签失败")


@router.get("/relationship-types", response_model=ResponseModel)
async def get_relationship_types():
    """
    获取所有关系类型
    
    Returns:
        关系类型列表
    """
    try:
        stats = await neo4j_service.get_statistics()
        
        return ResponseModel(
            success=True,
            message="获取关系类型成功",
            data=stats.get('relationship_types', [])
        )
    except Neo4jServiceError:
        raise
    except Exception as e:
        logger.error(f"获取关系类型失败: {e}")
        raise HTTPException(status_code=500, detail="获取关系类型失败")


@router.get("/knowledge/{knowledge_id}/questions", response_model=ResponseModel)
async def get_questions_by_knowledge(
    knowledge_id: str,
    limit: int = Query(100, ge=1, le=200),
):
    """
    获取知识点关联的所有题目
    
    Args:
        knowledge_id: 知识点业务ID或名称（兼容旧 elementId）
        limit: 返回数量限制
        
    Returns:
        题目列表及其关联原因
    """
    try:
        predicate = _knowledge_lookup_predicate(knowledge_id, "kp")
        query = f"""
        MATCH (kp:KnowledgeNode)<-[r:REQUIRES]-(q:Question)
        WHERE {predicate}
        RETURN properties(q) as question,
               coalesce(r.match_method, 'REQUIRES') as reason
        ORDER BY coalesce(r.weight, 0) DESC, q.id
        LIMIT $limit
        """
        results = await neo4j_service.execute_query(
            query,
            {"id": knowledge_id, "limit": limit},
        )
        
        questions = []
        for result in results:
            question = result['question']
            question['reason'] = result['reason']
            questions.append(question)
        
        return ResponseModel(
            success=True,
            message=f"找到 {len(questions)} 道题目",
            data=questions
        )
    except Neo4jServiceError:
        raise
    except Exception as e:
        logger.error(f"获取知识点题目失败: {e}")
        raise HTTPException(status_code=500, detail="获取知识点题目失败")


@router.get("/question/{question_id}/knowledge", response_model=ResponseModel)
async def get_knowledge_by_question(question_id: str):
    """
    获取题目关联的所有知识点
    
    Args:
        question_id: 题目业务ID（兼容旧 elementId）
        
    Returns:
        知识点列表及其关联原因
    """
    try:
        query = """
        MATCH (q:Question)-[r:REQUIRES]->(kp:KnowledgeNode)
        WHERE q.id = $id OR q.name = $id OR elementId(q) = $id
        RETURN properties(kp) as knowledge_point,
               coalesce(r.match_method, 'REQUIRES') as reason
        ORDER BY coalesce(r.weight, 0) DESC, kp.id
        """
        results = await neo4j_service.execute_query(query, {"id": question_id})
        
        knowledge_points = []
        for result in results:
            kp = result['knowledge_point']
            kp['reason'] = result['reason']
            knowledge_points.append(kp)
        
        return ResponseModel(
            success=True,
            message=f"找到 {len(knowledge_points)} 个知识点",
            data=knowledge_points
        )
    except Neo4jServiceError:
        raise
    except Exception as e:
        logger.error(f"获取题目知识点失败: {e}")
        raise HTTPException(status_code=500, detail="获取题目知识点失败")


@router.get("/question-knowledge/statistics", response_model=ResponseModel)
async def get_question_knowledge_statistics():
    """
    获取题目与知识点匹配的统计信息
    
    Returns:
        统计信息（覆盖率、匹配数量等）
    """
    try:
        # 当前数据模型为 Question-[:REQUIRES]->KnowledgeNode。所有统计合并
        # 为一个 Cypher 请求，避免旧 PRACTICES_FOR/KnowledgePoint 的空结果。
        query = """
        CALL {
            MATCH (q:Question)
            RETURN count(q) AS total_questions
        }
        CALL {
            MATCH (kp:KnowledgeNode)
            RETURN count(kp) AS total_kp
        }
        CALL {
            MATCH (q:Question)-[:REQUIRES]->(kp:KnowledgeNode)
            RETURN count(DISTINCT q) AS matched_questions,
                   count(DISTINCT kp) AS matched_kp
        }
        CALL {
            MATCH (q:Question)-[:REQUIRES]->(kp:KnowledgeNode)
            WITH kp, count(q) AS question_count
            ORDER BY question_count DESC, kp.id
            LIMIT 20
            RETURN collect({
                kp_id: kp.id,
                kp_name: kp.name,
                question_count: question_count
            }) AS kp_question_stats
        }
        CALL {
            MATCH (q:Question)-[:REQUIRES]->(:KnowledgeNode)-[:BELONGS_TO]->(ch:Chapter)
            WITH ch, count(DISTINCT q) AS question_count
            ORDER BY question_count DESC, ch.order
            RETURN collect({
                chapter_id: coalesce(ch.id, toString(ch.order)),
                chapter_name: ch.title,
                question_count: question_count
            }) AS chapter_stats
        }
        CALL {
            MATCH (:Question)-[r:REQUIRES]->(:KnowledgeNode)
            WITH coalesce(r.match_method, 'REQUIRES') AS reason,
                 count(r) AS rel_count
            ORDER BY rel_count DESC, reason
            RETURN collect({reason: reason, count: rel_count}) AS reason_stats
        }
        RETURN total_questions, total_kp, matched_questions, matched_kp,
               kp_question_stats, chapter_stats, reason_stats
        """
        rows = await neo4j_service.execute_query(query)
        row = rows[0] if rows else {
            "total_questions": 0,
            "total_kp": 0,
            "matched_questions": 0,
            "matched_kp": 0,
            "kp_question_stats": [],
            "chapter_stats": [],
            "reason_stats": [],
        }
        total_questions = row["total_questions"]
        matched_questions = row["matched_questions"]
        total_kp = row["total_kp"]
        matched_kp = row["matched_kp"]
        
        return ResponseModel(
            success=True,
            message="获取统计信息成功",
            data={
                "questions": {
                    "total": total_questions,
                    "matched": matched_questions,
                    "coverage": f"{matched_questions/total_questions*100:.1f}%" if total_questions > 0 else "0%"
                },
                "knowledge_points": {
                    "total": total_kp,
                    "matched": matched_kp,
                    "coverage": f"{matched_kp/total_kp*100:.1f}%" if total_kp > 0 else "0%"
                },
                "kp_question_stats": row["kp_question_stats"],
                "chapter_stats": row["chapter_stats"],
                "reason_stats": row["reason_stats"]
            }
        )
    except Neo4jServiceError:
        raise
    except Exception as e:
        logger.error(f"获取统计信息失败: {e}")
        raise HTTPException(status_code=500, detail="获取统计信息失败")


@router.get("/knowledge-points", response_model=ResponseModel)
async def get_knowledge_points(
    limit: int = Query(1000, ge=1, le=2000),
    node_type: str = Query(None, max_length=50),
    chapter_id: int = Query(None, ge=1, le=10000),
):
    """
    获取所有知识点列表
    
    Args:
        limit: 返回数量限制
        node_type: 节点类型过滤（KnowledgeNode, Chapter等）
        chapter_id: 章节ID过滤
        
    Returns:
        知识点列表
    """
    try:
        if node_type:
            safe_node_type = validate_node_labels([node_type])[0]
            query = """
            MATCH (n)
            WHERE $node_type IN labels(n)
            RETURN coalesce(n.id, n.node_id, elementId(n)) as id,
                   labels(n)[0] as type, properties(n) as properties
            ORDER BY coalesce(n.order, n.node_id, n.name, '')
            LIMIT $limit
            """
            results = await neo4j_service.execute_query(
                query,
                {"limit": limit, "node_type": safe_node_type},
            )
        elif chapter_id:
            query = """
            MATCH (n:KnowledgeNode)
            WHERE n.chapter_id = $chapter_id
            RETURN coalesce(n.id, n.node_id, elementId(n)) as id,
                   labels(n)[0] as type, properties(n) as properties
            ORDER BY n.node_id
            LIMIT $limit
            """
            results = await neo4j_service.execute_query(query, {"chapter_id": chapter_id, "limit": limit})
        else:
            # 获取所有 KnowledgeNode 节点（V3 教材知识图谱）
            query = """
            MATCH (n:KnowledgeNode)
            RETURN coalesce(n.id, n.node_id, elementId(n)) as id,
                   labels(n)[0] as type, properties(n) as properties
            ORDER BY coalesce(n.node_id, n.order, n.name, '')
            LIMIT $limit
            """
            results = await neo4j_service.execute_query(query, {"limit": limit})
        
        knowledge_points = []
        for result in results:
            kp = {
                **result['properties'],
                'id': result['id'],
                'type': result['type'],
            }
            knowledge_points.append(kp)
        
        return ResponseModel(
            success=True,
            message=f"获取到 {len(knowledge_points)} 个知识点",
            data=knowledge_points
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Neo4jServiceError:
        raise
    except Exception as e:
        logger.error(f"获取知识点列表失败: {e}")
        raise HTTPException(status_code=500, detail="获取知识点列表失败")


@router.get("/knowledge-points/page", response_model=ResponseModel)
async def get_knowledge_points_page(
    page: int = Query(1, ge=1, le=10000),
    page_size: int = Query(30, ge=10, le=100),
    chapter_id: int = Query(None, ge=1, le=10000),
    knowledge_type: str = Query(None, max_length=50),
    keyword: str = Query(None, max_length=100),
):
    """分页获取知识点摘要，不返回详情正文。"""
    try:
        normalized_keyword = (keyword or "").strip()
        normalized_type = (knowledge_type or "").strip()
        params = {
            "offset": (page - 1) * page_size,
            "page_size": page_size,
            "chapter_id": chapter_id,
            "knowledge_type": normalized_type,
            "keyword": normalized_keyword.lower(),
        }
        where_clause = """
        ($chapter_id IS NULL OR n.chapter_id = $chapter_id)
        AND ($knowledge_type = '' OR n.node_type = $knowledge_type)
        AND (
            $keyword = ''
            OR toLower(coalesce(n.name, '')) CONTAINS $keyword
            OR toLower(coalesce(n.overview, '')) CONTAINS $keyword
            OR toLower(coalesce(n.node_id, '')) CONTAINS $keyword
        )
        """
        count_rows = await neo4j_service.execute_query(
            f"MATCH (n:KnowledgeNode) WHERE {where_clause} RETURN count(n) AS total",
            params,
        )
        rows = await neo4j_service.execute_query(
            f"""
            MATCH (n:KnowledgeNode)
            WHERE {where_clause}
            RETURN coalesce(n.id, n.node_id, elementId(n)) AS id,
                   n.node_id AS node_id,
                   n.name AS name,
                   n.node_type AS node_type,
                   n.chapter_id AS chapter_id,
                   n.section AS section,
                   n.overview AS overview,
                   labels(n)[0] AS type
            ORDER BY coalesce(n.node_id, n.name, '')
            SKIP $offset LIMIT $page_size
            """,
            params,
        )
        total = count_rows[0]["total"] if count_rows else 0
        total_pages = (total + page_size - 1) // page_size
        return ResponseModel(
            success=True,
            message=f"获取到 {len(rows)} 个知识点摘要",
            data={
                "items": rows,
                "pagination": {
                    "page": page,
                    "page_size": page_size,
                    "total": total,
                    "total_pages": total_pages,
                },
            },
        )
    except Neo4jServiceError:
        raise
    except Exception as e:
        logger.error(f"分页获取知识点失败: {e}")
        raise HTTPException(status_code=500, detail="分页获取知识点失败")


@router.get("/knowledge-point/{knowledge_id}", response_model=ResponseModel)
async def get_knowledge_point_detail(knowledge_id: str):
    """
    获取知识点详情
    
    Args:
        knowledge_id: 知识点业务ID、node_id 或名称（兼容旧 elementId）
        
    Returns:
        知识点详情及相关内容
    """
    try:
        predicate = _knowledge_lookup_predicate(knowledge_id, "n")
        query = """
        MATCH (n:KnowledgeNode)
        WHERE __PREDICATE__
        WITH n,
             CASE WHEN n.id = $id OR n.node_id = $id THEN 0
                  WHEN n.name = $id THEN 1 ELSE 2 END AS priority
        ORDER BY priority, n.id
        LIMIT 1
        OPTIONAL MATCH (n)-[r:PREREQUISITE|HAS_CORE_RELATION|APPLIED_IN|HAS_INSTANCE|HAS_CORE_CONCEPT]->(target)
        OPTIONAL MATCH (target)-[:BELONGS_TO]->(target_chapter:Chapter)
        WITH n, collect(
            CASE WHEN target IS NULL THEN null ELSE {
                id: coalesce(target.id, target.node_id, elementId(target)),
                node_id: target.node_id,
                name: target.name,
                node_type: target.node_type,
                description: r.description,
                relation_type: type(r),
                chapter_order: target_chapter.order,
                chapter_title: target_chapter.title
            } END
        ) AS related_nodes
        OPTIONAL MATCH (n)-[:BELONGS_TO]->(ch:Chapter)
        RETURN coalesce(n.id, n.node_id, elementId(n)) AS id,
               labels(n)[0] AS type,
               properties(n) AS properties,
               related_nodes,
               head(collect(
                   CASE WHEN ch IS NULL THEN null ELSE {
                       chapter_title: ch.title,
                       chapter_order: ch.order
                   } END
               )) AS chapter_info
        """.replace("__PREDICATE__", predicate)
        results = await neo4j_service.execute_query(query, {"id": knowledge_id})
        
        if not results:
            raise HTTPException(status_code=404, detail=f"知识点不存在: {knowledge_id}")
        
        result = results[0]
        knowledge_point = {
            **result['properties'],
            'id': result['id'],
            'type': result['type'],
        }
        
        return ResponseModel(
            success=True,
            message="获取知识点详情成功",
            data={
                'knowledge_point': knowledge_point,
                'related_nodes': result['related_nodes'],
                'chapter_info': result['chapter_info']
            }
        )
    except HTTPException:
        raise
    except Neo4jServiceError:
        raise
    except Exception as e:
        logger.error(f"获取知识点详情失败: {e}")
        raise HTTPException(status_code=500, detail="获取知识点详情失败")


@router.get("/knowledge-point/{knowledge_id:path}/questions", response_model=ResponseModel)
async def get_knowledge_point_questions(
    knowledge_id: str,
    limit: int = Query(10, ge=1, le=100),
):
    """
    获取知识点关联的题目

    Args:
        knowledge_id: 知识点ID（可以是elementId、node_id或者name属性；
                      :path 转换器允许名称中含斜杠，如 0/1背包问题）
        limit: 返回数量限制
        
    Returns:
        关联题目列表
    """
    try:
        # 通过 REQUIRES 关系查找关联题目（新版）
        query = """
        MATCH (q:Question)-[r:REQUIRES]->(kp)
        WHERE kp.node_id = $id OR kp.id = $id OR kp.name = $id OR kp.name CONTAINS $id
        RETURN q.id as question_id, q.name as question_name, q.difficulty as difficulty,
               q.url as url, q.category1 as category1, q.category2 as category2,
               r.weight as weight, r.match_method as match_method
        ORDER BY r.weight DESC
        LIMIT $limit
        """
        
        results = await neo4j_service.execute_query(query, {"id": knowledge_id, "limit": limit})
        
        questions = []
        for r in results:
            questions.append({
                'id': r.get('question_id', ''),
                'name': r.get('question_name', ''),
                'difficulty': r.get('difficulty', ''),
                'url': r.get('url', ''),
                'category': f"{r.get('category1', '')} - {r.get('category2', '')}",
                'weight': r.get('weight', 0.5),
                'match_method': r.get('match_method', 'category_mapping')
            })
        
        return ResponseModel(
            success=True,
            message=f"找到 {len(questions)} 道关联题目",
            data=questions
        )
    except Neo4jServiceError:
        raise
    except Exception as e:
        logger.error(f"获取知识点关联题目失败: {e}")
        raise HTTPException(status_code=500, detail="获取知识点关联题目失败")


@router.get("/questions", response_model=TypedResponse[QuestionListData])
async def get_questions(
    page: int = Query(1, ge=1, le=100000),
    page_size: int = Query(20, ge=1, le=100),
    difficulty: str = Query(None, max_length=20),
    category1: str = Query(None, max_length=100),
    keyword: str = Query(None, max_length=200),
    sort_by: Literal["id", "difficulty", "kp_count"] = "id",
    after_id: str = Query(None, max_length=100),
):
    """
    获取题目列表（分页）
    
    Args:
        page: 页码，从1开始
        page_size: 每页数量
        difficulty: 难度筛选
        category1: 一级分类筛选
        keyword: 关键词搜索
        sort_by: 排序方式（id, difficulty, kp_count）
        
    Returns:
        题目列表及分页信息
    """
    try:
        skip = (page - 1) * page_size
        if after_id and sort_by != "id":
            raise HTTPException(status_code=400, detail="after_id 仅支持按 id 排序")
        if after_id and page != 1:
            raise HTTPException(status_code=400, detail="使用 after_id 时 page 必须为 1")
        if not after_id and skip > MAX_OFFSET_PAGINATION_SKIP:
            raise HTTPException(
                status_code=400,
                detail="页码过深，请改用响应中的 next_cursor 作为 after_id",
            )
        
        # 构建查询条件
        conditions = []
        params = {"skip": 0 if after_id else skip, "limit": page_size}

        if difficulty:
            conditions.append("q.difficulty = $difficulty")
            params["difficulty"] = difficulty

        if category1:
            conditions.append("q.category1 = $category1")
            params["category1"] = category1

        if keyword:
            # 走已有的 CJK 全文索引而非全表 CONTAINS 扫描（B8）；无命中时
            # 直接返回空列表，避免对空 ID 列表生成误命中所有题目的查询。
            keyword_ids = await neo4j_service.search_question_ids_by_keyword(keyword)
            if not keyword_ids:
                return ResponseModel(
                    success=True,
                    message="获取到 0 道题目",
                    data={
                        'questions': [],
                        'pagination': {
                            'page': page,
                            'page_size': page_size,
                            'total': 0,
                            'total_pages': 0,
                            'mode': 'cursor' if after_id else 'offset',
                            'next_cursor': None,
                        },
                    },
                )
            conditions.append("q.id IN $keyword_ids")
            params["keyword_ids"] = keyword_ids

        where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""
        list_conditions = list(conditions)
        if after_id:
            list_conditions.append("q.id > $after_id")
            params["after_id"] = after_id
        list_where_clause = (
            "WHERE " + " AND ".join(list_conditions) if list_conditions else ""
        )
        
        # 排序逻辑
        order_clause = "ORDER BY q.id"
        if sort_by == "difficulty":
            # 难度排序：简单->中等->困难
            order_clause = """
            ORDER BY CASE q.difficulty 
                WHEN '简单' THEN 1 
                WHEN '中等' THEN 2 
                WHEN '困难' THEN 3 
                ELSE 4 END
            """
        elif sort_by == "kp_count":
            order_clause = "ORDER BY kp_count DESC"
        
        # 查询总数
        count_query = f"""
        MATCH (q:Question)
        {where_clause}
        RETURN count(q) as total
        """
        total_result = await neo4j_service.execute_query(count_query, params)
        total = total_result[0]['total'] if total_result else 0
        
        # 普通排序先分页，再只对当页题目展开 REQUIRES。只有 kp_count
        # 排序必须先计算全量关联数，以保持原有排序语义。
        if sort_by == "kp_count":
            list_query = f"""
            MATCH (q:Question)
            {list_where_clause}
            OPTIONAL MATCH (q)-[:REQUIRES]->(kp:KnowledgeNode)
            WITH q, count(DISTINCT kp) AS kp_count
            ORDER BY kp_count DESC, q.id
            SKIP $skip LIMIT $limit
            RETURN q.id AS id, q.name AS name, q.difficulty AS difficulty,
                   q.url AS url, q.category1 AS category1, q.category2 AS category2,
                   q.source AS source, kp_count
            ORDER BY kp_count DESC, id
            """
        else:
            list_query = f"""
            MATCH (q:Question)
            {list_where_clause}
            WITH q
            {order_clause}
            SKIP $skip LIMIT $limit
            OPTIONAL MATCH (q)-[:REQUIRES]->(kp:KnowledgeNode)
            WITH q, count(DISTINCT kp) AS kp_count
            RETURN q.id AS id, q.name AS name, q.difficulty AS difficulty,
                   q.url AS url, q.category1 AS category1, q.category2 AS category2,
                   q.source AS source, kp_count
            {order_clause}
            """
        results = await neo4j_service.execute_query(list_query, params)
        
        questions = []
        for r in results:
            questions.append({
                'id': r.get('id', ''),
                'name': r.get('name', ''),
                'difficulty': r.get('difficulty', ''),
                'url': r.get('url', ''),
                'category1': r.get('category1', ''),
                'category2': r.get('category2', ''),
                'source': r.get('source', '码蹄集'),
                'kp_count': r.get('kp_count', 0)
            })
        
        next_cursor = None
        if sort_by == "id" and len(questions) == page_size:
            next_cursor = questions[-1]["id"]

        return ResponseModel(
            success=True,
            message=f"获取到 {len(questions)} 道题目",
            data={
                'questions': questions,
                'pagination': {
                    'page': page,
                    'page_size': page_size,
                    'total': total,
                    'total_pages': (total + page_size - 1) // page_size,
                    'mode': 'cursor' if after_id else 'offset',
                    'next_cursor': next_cursor
                }
            }
        )
    except HTTPException:
        raise
    except Neo4jServiceError:
        raise
    except Exception as e:
        logger.error(f"获取题目列表失败: {e}")
        raise HTTPException(status_code=500, detail="获取题目列表失败")


@router.get("/questions/categories", response_model=ResponseModel)
async def get_question_categories():
    """
    获取题目分类信息
    
    Returns:
        一级分类列表及难度列表
    """
    try:
        query = """
        CALL {
            MATCH (q:Question)
            WHERE q.category1 IS NOT NULL AND q.category1 <> ''
            WITH q.category1 AS category, count(q) AS count
            ORDER BY count DESC, category
            RETURN collect({category: category, count: count}) AS categories
        }
        CALL {
            MATCH (q:Question)
            WHERE q.difficulty IS NOT NULL AND q.difficulty <> ''
            WITH q.difficulty AS difficulty, count(q) AS count
            ORDER BY count DESC, difficulty
            RETURN collect({difficulty: difficulty, count: count}) AS difficulties
        }
        RETURN categories, difficulties
        """
        rows = await neo4j_service.execute_query(query)
        row = rows[0] if rows else {"categories": [], "difficulties": []}
        
        return ResponseModel(
            success=True,
            message="获取分类信息成功",
            data={
                'categories': row['categories'],
                'difficulties': row['difficulties']
            }
        )
    except Neo4jServiceError:
        raise
    except Exception as e:
        logger.error(f"获取分类信息失败: {e}")
        raise HTTPException(status_code=500, detail="获取分类信息失败")


@router.get("/question/{question_id}", response_model=TypedResponse[QuestionDetailData])
async def get_question_detail(question_id: str):
    """
    获取题目详情
    
    Args:
        question_id: 题目ID
        
    Returns:
        题目详情及关联知识点
    """
    try:
        # 获取题目详情
        query = """
        MATCH (q:Question {id: $id})
        OPTIONAL MATCH (q)-[r:REQUIRES]->(kp:KnowledgeNode)
        WITH q, kp, r
        ORDER BY coalesce(r.weight, 0) DESC, kp.id
        WITH q, collect(
            CASE WHEN kp IS NULL THEN null ELSE {
                node_id: kp.node_id,
                id: kp.id,
                name: kp.name,
                node_type: kp.node_type,
                chapter_id: kp.chapter_id,
                weight: coalesce(r.weight, 0.5),
                match_method: coalesce(r.match_method, 'category_mapping')
            } END
        )[0..20] AS knowledge_points
        RETURN q.id as id, q.name as name, q.description as description,
               q.input_format as input_format, q.output_format as output_format,
               q.sample_input as sample_input, q.sample_output as sample_output,
               q.difficulty as difficulty, q.pass_rate as pass_rate,
               q.url as url, q.category1 as category1, q.category2 as category2,
               q.source as source, knowledge_points
        """
        results = await neo4j_service.execute_query(query, {"id": question_id})
        
        if not results:
            raise HTTPException(status_code=404, detail=f"题目不存在: {question_id}")
        
        r = results[0]
        question = {
            'id': r.get('id', ''),
            'name': r.get('name', ''),
            'description': r.get('description', ''),
            'input_format': r.get('input_format', ''),
            'output_format': r.get('output_format', ''),
            'sample_input': r.get('sample_input', ''),
            'sample_output': r.get('sample_output', ''),
            'difficulty': r.get('difficulty', ''),
            'pass_rate': r.get('pass_rate', ''),
            'url': r.get('url', ''),
            'category1': r.get('category1', ''),
            'category2': r.get('category2', ''),
            'source': r.get('source', '码蹄集'),
            'remark': r.get('remark', '')
        }
        
        return ResponseModel(
            success=True,
            message="获取题目详情成功",
            data={
                'question': question,
                'knowledge_points': r.get('knowledge_points', [])
            }
        )
    except HTTPException:
        raise
    except Neo4jServiceError:
        raise
    except Exception as e:
        logger.error(f"获取题目详情失败: {e}")
        raise HTTPException(status_code=500, detail="获取题目详情失败")

@router.get("/home/data", response_model=ResponseModel)
async def get_home_data():
    """
    获取首页展示数据

    Returns:
        题目统计、热门知识点、推荐题目等
    """
    global _home_data_cache, _home_data_cache_expires_at

    # 缓存热路径：无锁快速返回（Q5）
    now = monotonic()
    if _home_data_cache and now < _home_data_cache_expires_at:
        return ResponseModel(success=True, message="获取首页数据成功", data=_home_data_cache)

    async with _home_data_lock:
        now = monotonic()
        if _home_data_cache and now < _home_data_cache_expires_at:
            return ResponseModel(success=True, message="获取首页数据成功", data=_home_data_cache)

        try:
            query = """
        CALL {
            MATCH (q:Question)
            RETURN count(q) AS total_questions
        }
        CALL {
            MATCH (q:Question)
            WHERE q.difficulty IS NOT NULL
            WITH q.difficulty AS difficulty, count(q) AS count
            ORDER BY count DESC, difficulty
            RETURN collect({difficulty: difficulty, count: count}) AS difficulty_stats
        }
        CALL {
            MATCH (q:Question)
            WHERE q.category1 IS NOT NULL AND q.category1 <> ''
            WITH q.category1 AS category, count(q) AS count
            ORDER BY count DESC, category
            LIMIT 10
            RETURN collect({category: category, count: count}) AS category_stats
        }
        CALL {
            MATCH (q:Question)-[:REQUIRES]->(kp:KnowledgeNode)
            WHERE kp.name IS NOT NULL
            WITH kp, count(q) AS question_count
            ORDER BY question_count DESC, kp.id
            LIMIT 10
            RETURN collect({
                id: kp.id,
                name: kp.name,
                question_count: question_count
            }) AS hot_knowledge_points
        }
        CALL {
            UNWIND $recommendation_categories AS category
            CALL {
                WITH category
                MATCH (q:Question)
                WHERE q.category1 = category
                WITH q
                ORDER BY q.id
                RETURN collect(q) AS category_all_questions
            }
            // Cypher 的 SKIP 不允许引用变量，改用列表切片对分类自身数量
            // 取模，避免题目数少于固定偏移量的小分类整块为空（B17）
            WITH category, category_all_questions,
                 size(category_all_questions) AS category_total
            WITH CASE WHEN category_total = 0 THEN 0
                      ELSE $recommendation_offset % category_total END AS skip_amount,
                 category_all_questions
            WITH [q IN category_all_questions[skip_amount..skip_amount + 2] | {
                id: q.id,
                name: q.name,
                difficulty: q.difficulty,
                category1: q.category1,
                url: q.url
            }] AS category_questions
            WITH collect(category_questions) AS question_groups
            UNWIND question_groups AS question_group
            UNWIND question_group AS question
            WITH question
            LIMIT 6
            RETURN collect(question) AS recommended_questions
        }
        CALL {
            MATCH (kp:KnowledgeNode)
            RETURN count(kp) AS total_knowledge_points
        }
        CALL {
            MATCH (ch:Chapter)
            RETURN count(ch) AS total_chapters
        }
        CALL {
            MATCH ()-[r]->()
            RETURN count(r) AS total_relationships
        }
        RETURN total_questions, total_knowledge_points, total_chapters,
               total_relationships, difficulty_stats, category_stats,
               hot_knowledge_points, recommended_questions
        """
            rows = await neo4j_service.execute_query(
                query,
                {
                    "recommendation_categories": RECOMMENDATION_CATEGORIES,
                    # Rotate a small indexed slice daily without sorting all
                    # questions by rand().
                    "recommendation_offset": date.today().toordinal() % 5,
                },
            )
            row = rows[0] if rows else {
                "total_questions": 0,
                "total_knowledge_points": 0,
                "total_chapters": 0,
                "total_relationships": 0,
                "difficulty_stats": [],
                "category_stats": [],
                "hot_knowledge_points": [],
                "recommended_questions": [],
            }
            result_data = {
                'overview': {
                    'total_questions': row['total_questions'],
                    'total_knowledge_points': row['total_knowledge_points'],
                    'total_chapters': row['total_chapters'],
                    'total_relationships': row['total_relationships']
                },
                'difficulty_stats': row['difficulty_stats'],
                'category_stats': row['category_stats'],
                'hot_knowledge_points': row['hot_knowledge_points'],
                'recommended_questions': row['recommended_questions']
            }
            # 写入缓存（Q5）
            _home_data_cache = result_data
            _home_data_cache_expires_at = monotonic() + settings.HOME_DATA_CACHE_TTL_SECONDS
            return ResponseModel(
                success=True,
                message="获取首页数据成功",
                data=result_data,
            )
        except Neo4jServiceError:
            raise
        except Exception as e:
            logger.error(f"获取首页数据失败: {e}")
            raise HTTPException(status_code=500, detail="获取首页数据失败")
