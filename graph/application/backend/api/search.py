"""
搜索相关API
"""
from fastapi import APIRouter, HTTPException, Query
from loguru import logger
from database.neo4j_service import neo4j_service
from database.neo4j_exceptions import Neo4jServiceError
from database.models import SearchRequest, ResponseModel
from database.cypher_security import validate_node_labels

router = APIRouter(prefix="/search", tags=["智能搜索"])

# 实际业务使用的节点类型（排除系统标签）
BUSINESS_NODE_TYPES = {
    "KnowledgeNode": "知识点",
    "Chapter": "章节",
    "Question": "题目"
}

# 节点类型对应的中文标签
NODE_TYPE_LABELS = {
    "KnowledgeNode": "知识点",
    "Chapter": "章节", 
    "Question": "题目",
    "核心抽象": "核心抽象",
    "核心实体": "核心实体",
    "关键事件": "关键事件"
}


@router.get("/labels", response_model=ResponseModel)
async def get_business_labels():
    """
    获取业务节点类型标签（排除系统标签）
    
    Returns:
        业务节点类型列表
    """
    return ResponseModel(
        success=True,
        message="获取节点类型成功",
        data=list(BUSINESS_NODE_TYPES.keys())
    )


@router.post("/", response_model=ResponseModel)
async def search_nodes(request: SearchRequest):
    """
    搜索节点
    
    Args:
        request: 搜索请求（关键词、节点类型、限制数量）
        
    Returns:
        匹配的节点列表
    """
    try:
        nodes = await neo4j_service.search_nodes(
            keyword=request.keyword,
            node_types=request.node_types,
            limit=request.limit
        )
        
        # 为每个节点添加中文类型标签
        for node in nodes:
            if 'label' in node:
                node['label_cn'] = NODE_TYPE_LABELS.get(node['label'], node['label'])
        
        return ResponseModel(
            success=True,
            message=f"搜索到 {len(nodes)} 个节点",
            data=nodes
        )
    except Neo4jServiceError:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"搜索节点失败: {e}")
        raise HTTPException(status_code=500, detail="搜索节点失败")


@router.get("/keyword", response_model=ResponseModel)
async def search_by_keyword(
    keyword: str = Query(..., min_length=1, max_length=200, description="搜索关键词"),
    node_type: str = Query(None, max_length=50, description="节点类型"),
    limit: int = Query(100, ge=1, le=200, description="返回数量限制")
):
    """
    根据关键词搜索节点（GET方式）
    
    Args:
        keyword: 搜索关键词
        node_type: 节点类型（可选）
        limit: 返回数量限制
        
    Returns:
        匹配的节点列表
    """
    try:
        node_types = validate_node_labels([node_type]) if node_type else None
        nodes = await neo4j_service.search_nodes(
            keyword=keyword,
            node_types=node_types,
            limit=limit
        )
        
        # 为每个节点添加中文类型标签
        for node in nodes:
            if 'label' in node:
                node['label_cn'] = NODE_TYPE_LABELS.get(node['label'], node['label'])
        
        return ResponseModel(
            success=True,
            message=f"搜索到 {len(nodes)} 个节点",
            data=nodes
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Neo4jServiceError:
        raise
    except Exception as e:
        logger.error(f"关键词搜索失败: {e}")
        raise HTTPException(status_code=500, detail="关键词搜索失败")


@router.get("/suggestions", response_model=ResponseModel)
async def get_search_suggestions(
    keyword: str = Query(..., min_length=1, max_length=200, description="搜索关键词"),
    limit: int = Query(10, ge=1, le=50, description="返回数量限制")
):
    """
    获取搜索建议（自动补全）
    
    Args:
        keyword: 搜索关键词
        limit: 返回数量限制
        
    Returns:
        搜索建议列表
    """
    try:
        # 与主搜索共用 CJK 全文索引，单字无命中时由服务层回退到 CONTAINS。
        results = await neo4j_service.search_suggestions(keyword, limit)
        
        suggestions = []
        for r in results:
            suggestion = {
                "label": r['name'],
                "type": NODE_TYPE_LABELS.get(r['type'], r['type']),
                "search_score": r.get('score', 0.0),
            }
            # 添加额外信息
            if r.get('sub_type'):
                suggestion['sub_type'] = r['sub_type']
            if r.get('section'):
                suggestion['section'] = r['section']
            suggestions.append(suggestion)
        
        return ResponseModel(
            success=True,
            message=f"获取到 {len(suggestions)} 个建议",
            data=suggestions
        )
    except Neo4jServiceError:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"获取搜索建议失败: {e}")
        raise HTTPException(status_code=500, detail="获取搜索建议失败")
