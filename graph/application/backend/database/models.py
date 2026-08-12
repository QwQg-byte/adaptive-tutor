"""
数据模型定义
"""
from typing import Annotated, Any, Dict, Generic, List, Literal, Optional, TypeVar

from pydantic import BaseModel, Field, StringConstraints, field_validator

from database.cypher_security import validate_node_labels

T = TypeVar("T")


SafeText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=200),
]


class NodeModel(BaseModel):
    """节点模型"""
    id: str = Field(..., description="节点ID")
    label: str = Field(..., description="节点标签")
    type: str = Field(..., description="节点类型")
    properties: Dict[str, Any] = Field(default_factory=dict, description="节点属性")


class EdgeModel(BaseModel):
    """边模型"""
    from_id: str = Field(..., description="起始节点ID", alias="from")
    to_id: str = Field(..., description="目标节点ID", alias="to")
    label: str = Field(..., description="边标签")
    properties: Dict[str, Any] = Field(default_factory=dict, description="边属性")


class GraphDataModel(BaseModel):
    """图谱数据模型"""
    nodes: List[NodeModel]
    edges: List[EdgeModel]
    statistics: Dict[str, Any]


class GraphFragmentRequest(BaseModel):
    """按业务 ID 加载图谱片段的请求模型"""
    node_ids: List[SafeText] = Field(
        ...,
        min_length=1,
        max_length=200,
        description="需要加载的节点业务 ID 列表",
    )
    relationship_types: Optional[List[SafeText]] = Field(
        default_factory=list,
        max_length=20,
        description="可选的关系类型过滤列表",
    )


class SearchRequest(BaseModel):
    """搜索请求模型"""
    keyword: SafeText = Field(..., description="搜索关键词")
    node_types: Optional[List[str]] = Field(None, max_length=10, description="节点类型过滤")
    limit: Optional[int] = Field(100, ge=1, le=200, description="返回数量限制")

    @field_validator("node_types")
    @classmethod
    def validate_search_node_types(cls, value: Optional[List[str]]) -> Optional[List[str]]:
        return validate_node_labels(value) if value else value


class NodeDetailModel(BaseModel):
    """节点详情模型"""
    node: NodeModel
    relationships: List[Dict[str, Any]]


class PathRequest(BaseModel):
    """路径请求模型"""
    start: SafeText = Field(..., description="起始节点ID或名称")
    end: SafeText = Field(..., description="目标节点ID或名称")
    max_depth: Optional[int] = Field(5, ge=1, le=10, description="最大路径深度")


class PathModel(BaseModel):
    """路径模型"""
    nodes: List[Dict[str, Any]]
    relationships: List[Dict[str, Any]]
    length: int


class PlanRequest(BaseModel):
    """学习计划请求模型"""
    target: SafeText = Field(..., description="目标知识点名称或业务ID（如 NODE_358）")
    max_depth: Optional[int] = Field(6, ge=1, le=10, description="前置依赖追溯深度")
    mastered: Optional[List[SafeText]] = Field(
        default_factory=list,
        max_length=2000,
        description="已掌握知识点的业务ID列表，生成时裁剪",
    )
    completed: Optional[List[SafeText]] = Field(
        default_factory=list,
        max_length=2000,
        description="当前目标下已完成步骤的业务ID列表，生成时裁剪",
    )
    difficulty_preference: Literal["foundation", "balanced", "challenge"] = Field(
        "balanced",
        description="推荐题训练强度：基础、均衡或挑战",
    )
    questions_per_step: Optional[int] = Field(3, ge=0, le=5, description="每个知识点推荐题目数量")


class StatisticsModel(BaseModel):
    """统计信息模型"""
    total_nodes: int
    total_relationships: int
    nodes: Dict[str, int]
    relationships: Dict[str, int]
    labels: List[str]
    relationship_types: List[str]


# ---------------------------------------------------------------------------
# 题目组数据模型（Q2）
# ---------------------------------------------------------------------------

class QuestionSummary(BaseModel):
    """题目列表项（不含完整题面）"""
    id: str
    name: str
    difficulty: str = ""
    url: str = ""
    category1: str = ""
    category2: str = ""
    source: str = ""
    kp_count: int = 0


class PaginationInfo(BaseModel):
    page: int
    page_size: int
    total: int
    total_pages: int
    mode: str = "offset"
    next_cursor: Optional[str] = None


class QuestionListData(BaseModel):
    questions: List[QuestionSummary]
    pagination: PaginationInfo


class KnowledgePointRef(BaseModel):
    """题目关联的知识点引用"""
    node_id: Optional[str] = None
    id: Optional[str] = None
    name: str = ""
    node_type: str = ""
    chapter_id: Optional[int] = None
    weight: float = 0.5
    match_method: str = ""


class QuestionDetailData(BaseModel):
    """题目详情（含完整题面和关联知识点）"""
    question: Dict[str, Any]
    knowledge_points: List[KnowledgePointRef] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# 学习计划数据模型（Q2）
# ---------------------------------------------------------------------------

class PlanStepQuestion(BaseModel):
    id: str
    name: str = ""
    difficulty: str = ""
    pass_rate: Optional[Any] = None  # Neo4j 存储为 float 或 str，两者都接受
    url: str = ""
    category1: str = ""
    category2: str = ""


class PlanStepPrerequisite(BaseModel):
    id: str
    name: str


class PlanStep(BaseModel):
    order: int
    id: str
    name: str
    depth: int = 0
    is_target: bool = False
    prerequisites: List[PlanStepPrerequisite] = Field(default_factory=list)
    questions: List[PlanStepQuestion] = Field(default_factory=list)


class PlanData(BaseModel):
    target: Dict[str, str]
    total_steps: int
    steps: List[PlanStep]
    mastered_skipped: List[Dict[str, str]] = Field(default_factory=list)
    completed_skipped: List[Dict[str, str]] = Field(default_factory=list)
    difficulty_preference: str = "balanced"
    already_mastered: bool = False
    already_completed: bool = False


# ---------------------------------------------------------------------------
# 统一响应模型
# ---------------------------------------------------------------------------

class ResponseModel(BaseModel):
    """统一响应模型"""
    success: bool = True
    message: str = ""
    data: Optional[Any] = None


class TypedResponse(BaseModel, Generic[T]):
    """带具体数据类型的统一响应模型，用于 OpenAPI 文档可读性（Q2）。"""
    success: bool = True
    message: str = ""
    data: Optional[T] = None


class ErrorResponse(BaseModel):
    """错误响应模型"""
    success: bool = False
    message: str
    error: Optional[str] = None
