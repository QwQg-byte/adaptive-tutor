# 知识图谱可视化系统 - 后端

基于FastAPI的知识图谱后端服务。

---

## 📋 功能特性

- ✅ Neo4j数据库连接管理
- ✅ 图谱数据查询API
- ✅ 智能搜索功能
- ✅ 学习路径规划
- ✅ 统计分析API
- ✅ 自动API文档（Swagger/ReDoc）

---

## 🚀 快速开始

### 1. 安装依赖

```bash
cd application/backend
pip install -r requirements.txt
```

### 2. 配置环境变量

复制`.env.example`为`.env`，并修改配置：

```bash
cp .env.example .env
```

主要配置项：
```env
ENVIRONMENT=development
DEBUG=False
RELOAD=False
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=
NEO4J_DATABASE=neo4j
NEO4J_MAX_CONNECTION_POOL_SIZE=50
NEO4J_CONNECTION_TIMEOUT_SECONDS=10
NEO4J_CONNECTION_ACQUISITION_TIMEOUT_SECONDS=30
NEO4J_MAX_CONNECTION_LIFETIME_SECONDS=3600
NEO4J_MAX_TRANSACTION_RETRY_TIME_SECONDS=15
NEO4J_QUERY_TIMEOUT_SECONDS=30
NEO4J_FETCH_SIZE=1000
NEO4J_FULLTEXT_INDEX_NAME=content_search_fulltext
GRAPH_STATISTICS_CACHE_TTL_SECONDS=30
```

`.env` 仅用于本机且已被 Git 忽略。请填写强密码，禁止把真实凭据写入
`.env.example`、源码或文档。

Web 后端使用 `AsyncGraphDatabase` 和异步 managed transaction。连接池、连接获取、
事务重试及单查询超时均由上述配置控制；离线构建和导入脚本使用同步
`knowledge_graph/neo4j_connector.py`，不会在 FastAPI 事件循环中运行。
统计信息在应用启动时预热，并按上述 TTL 使用进程内缓存。

### 3. 启动服务

```bash
# 默认安全模式（仅监听本机、不开启热重载）
python main.py

# 或使用uvicorn
uvicorn main:app --host 127.0.0.1 --port 8000
```

如本地开发确实需要热重载，仅在未对外暴露的开发环境中设置
`RELOAD=True`；生产环境会拒绝同时启用 `DEBUG` 或 `RELOAD`。

### 4. 访问服务

- **主页**: http://localhost:8000
- **API文档（Swagger）**: http://localhost:8000/docs
- **API文档（ReDoc）**: http://localhost:8000/redoc
- **健康检查**: http://localhost:8000/health

---

## 📚 API文档

### 图谱管理 API

#### 获取图谱数据
```http
GET /api/v1/graph/data?limit=1000
```

#### 获取统计信息
```http
GET /api/v1/graph/statistics
```

#### 获取节点详情
```http
GET /api/v1/graph/node/{node_id}?direction=both
```

#### 按需展开节点邻居
```http
GET /api/v1/graph/node/{node_id}/neighbors?limit=30
```

#### 分页获取知识点摘要
```http
GET /api/v1/graph/knowledge-points/page?page=1&page_size=30&chapter_id=2&knowledge_type=核心抽象&keyword=线性
```

#### 获取节点标签
```http
GET /api/v1/graph/labels
```

#### 获取关系类型
```http
GET /api/v1/graph/relationship-types
```

---

### 智能搜索 API

#### 搜索节点
```http
POST /api/v1/search/
Content-Type: application/json

{
  "keyword": "动态规划",
  "node_types": ["KnowledgeNode", "Question"],
  "limit": 100
}
```

#### 关键词搜索
```http
GET /api/v1/search/keyword?keyword=动态规划&node_type=KnowledgeNode&limit=100
```

#### 搜索建议
```http
GET /api/v1/search/suggestions?keyword=动&limit=10
```

---

### 学习路径 API

#### 查找最短路径
```http
POST /api/v1/path/shortest
Content-Type: application/json

{
  "start": "两数之和",
  "end": "最长子序列",
  "max_depth": 5
}
```

#### 获取学习路径
```http
GET /api/v1/path/learning/{knowledge_name}?max_depth=3
```

#### 获取相关节点
```http
GET /api/v1/path/related/{node_id}?limit=20
```

#### 获取依赖关系
```http
GET /api/v1/path/dependencies/{knowledge_name}
```

---

## 📁 项目结构

```
backend/
├── main.py                  # 主应用入口
├── config.py                # 配置管理
├── requirements.txt         # Python依赖
├── .env.example            # 环境变量模板
├── api/
│   ├── __init__.py
│   ├── graph.py           # 图谱API
│   ├── search.py          # 搜索API
│   └── path.py            # 路径API
├── database/
│   ├── __init__.py
│   ├── neo4j_service.py   # FastAPI 异步 Neo4j 服务
│   ├── neo4j_exceptions.py # 数据库异常语义
│   └── models.py          # 数据模型
└── logs/                  # 日志目录
```

---

## 🔧 开发说明

### 添加新API

1. 在`api/`目录下创建新模块（如`analytics.py`）
2. 定义路由和处理器
3. 在`main.py`中注册路由

示例：
```python
# api/analytics.py
from fastapi import APIRouter
from loguru import logger

router = APIRouter(prefix="/analytics", tags=["数据分析"])

@router.get("/overview")
async def get_overview():
    # 实现逻辑
    return {"data": {}}
```

```python
# main.py
from api import analytics

app.include_router(analytics.router, prefix=settings.API_PREFIX)
```

---

### 数据模型

所有数据模型定义在`database/models.py`中：

- `NodeModel` - 节点模型
- `EdgeModel` - 边模型
- `GraphDataModel` - 图谱数据模型
- `SearchRequest` - 搜索请求模型
- `PathRequest` - 路径请求模型
- `ResponseModel` - 统一响应模型

---

## 📊 响应格式

所有API响应格式统一：

```json
{
  "success": true,
  "message": "操作成功",
  "data": {}
}
```

错误响应：

```json
{
  "success": false,
  "message": "错误描述",
  "data": null
}
```

服务端日志保留异常类型用于排查，响应不会返回 Cypher、连接信息或驱动异常原文。

---

## 🔍 故障排除

### Neo4j连接失败

1. 检查Neo4j服务是否启动
2. 确认连接配置（URI、用户名、密码）
3. 检查防火墙设置

### 查询超时

1. 检查Cypher查询语句
2. 考虑添加索引
3. 调整查询参数（limit）
4. 按部署环境调整 `NEO4J_QUERY_TIMEOUT_SECONDS`，不要用无限超时掩盖慢查询

数据库未连接返回 HTTP 503，查询超时返回 HTTP 504，其他查询执行失败返回
HTTP 500。合法查询没有匹配行时仍按接口语义返回空数组或 HTTP 404，不会被当作数据库错误。

可在仓库根目录使用真实 Neo4j 执行只读异步接口回归：

```bash
python scripts/verify_async_api.py
```

### Schema 与阶段 3 验收

```bash
# 唯一性预检、幂等创建和状态检查
python scripts/manage_schema.py validate
python scripts/manage_schema.py apply
python scripts/manage_schema.py status

# 只读检查 Schema、PROFILE、全文索引和关键接口基准
python scripts/verify_phase3.py --samples 5
```

题目列表支持 `after_id` 前向游标；ID 排序的深层偏移超过 10000 条时必须改用
响应中的 `pagination.next_cursor`。

### CORS错误

1. 检查`.env`中的`CORS_ORIGINS`配置
2. 确保前端地址在允许列表中

---

## 📝 日志

日志输出到：
- 控制台（stderr）
- 文件（`logs/app.log`）

日志级别：
- DEBUG: 详细调试信息
- INFO: 一般信息
- WARNING: 警告信息
- ERROR: 错误信息

---

## 🧪 测试

```bash
# 后端单元/API测试
python -m pytest -m "not integration" -q

# 独立 Neo4j 集成测试（需要 Docker Desktop）
powershell -ExecutionPolicy Bypass -File ..\..\scripts\run_neo4j_integration.ps1

# 静态检查
ruff check application/backend knowledge_graph scripts tests import_data.py
```

---

## 📦 部署

生产部署采用本机绑定的 FastAPI、Nginx 和 Neo4j 服务，见
`docs/部署与备份.md`。Docker 仅用于隔离集成测试，不作为生产部署前提。

---

## 📄 许可证

许可证和共同开发者署名尚待书面确认，当前版本不应声明为 MIT 开源发布。

---

## 👥 联系方式

如有问题，请联系项目维护者。
