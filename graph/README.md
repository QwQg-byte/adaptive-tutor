# 基于知识图谱的算法学习平台 --原始文档

> 面向程序设计竞赛的智能学习系统，基于Neo4j图数据库和Vue 3构建。

## 项目概述

本项目构建了一个面向程序设计竞赛的知识图谱智能学习平台，主要功能包括：

- **知识图谱可视化** - 交互式浏览数据结构与算法知识点
- **智能学习路径规划** - 基于知识点依赖关系自动规划学习顺序
- **题目与知识点关联** - 1300+道竞赛题目与444个核心知识点关联
- **智能搜索** - 支持关键词检索、自动补全、模糊匹配

## 技术栈

| 模块 | 技术选型 |
|------|----------|
| 图数据库 | Neo4j 5.x |
| 后端框架 | FastAPI + Python 3.11 |
| 前端框架 | Vue 3 + Element Plus |
| 图谱可视化 | vis-network |
| 知识表示 | 属性图模型 |

## 项目结构

```
knowledge/
├── application/
│   ├── backend/                  # FastAPI 后端服务
│   │   ├── api/                  # API 接口
│   │   │   ├── graph.py         # 图谱数据接口
│   │   │   ├── search.py        # 智能搜索接口
│   │   │   └── path.py          # 学习路径接口
│   │   ├── database/            # 数据库服务
│   │   │   └── neo4j_service.py # Neo4j 操作封装
│   │   ├── main.py              # 应用入口
│   │   └── config.py            # 配置管理
│   └── frontend/                 # Vue 3 前端
│       └── src/
│           ├── views/            # 页面组件
│           │   ├── Home.vue         # 首页
│           │   ├── GraphPage.vue    # 图谱浏览
│           │   ├── KnowledgePage.vue # 知识详情
│           │   ├── PathPage.vue     # 学习路径
│           │   └── SearchPage.vue   # 智能搜索
│           └── api/              # API 请求封装
│
├── knowledge_graph/              # 知识图谱构建工具
│   ├── graph_builder.py         # 图谱构建核心
│   ├── neo4j_connector.py       # Neo4j 连接封装
│   ├── schema_manager.py        # 数据库 Schema 管理
│   └── schema/
│       ├── ontology.json        # 本体定义
│       ├── constraints.cql      # Neo4j 5 Schema 创建脚本
│       └── drop_schema.cql      # 项目 Schema 回滚脚本
│
├── data/                         # 数据目录
│   └── processed/                # 处理后数据
│       ├── knowledge_graph_v3/   # 知识点图谱数据
│       └── matiji_knowledge_graph.json  # 题目关联数据
│
├── import_data.py               # 数据导入脚本（统一入口）
└── docs/                         # 文档目录
```

## 快速开始

### 环境要求

- Python 3.11+
- Node.js 18+
- Neo4j 5.x

### 安装依赖

```bash
# 安装 Python 依赖
pip install -r requirements.txt

# 安装前端依赖
cd application/frontend && npm install
```

### 知识图谱数据导入

```bash
# 1. 配置数据库连接
# 复制本机环境变量文件（不要提交 .env）
cd application/backend
cp .env.example .env
# 编辑 .env，填写 NEO4J_PASSWORD；源码和文档中不要保存真实密码
cd ../..

# 2. 导入知识图谱数据（统一入口）
# 全量导入默认先清空当前数据库
python import_data.py

# 分步导入默认保留现有数据，适合依次补充知识点和题目
python import_data.py --kg-only
python import_data.py --questions-only

# 自定义批次且明确保留现有数据
python import_data.py --no-clear --batch-size 500 --relationship-batch-size 1000
```

**数据文件位置：**
- 知识点数据：`data/processed/knowledge_graph_v3/knowledge_graph.json`
- 题目数据：`data/processed/matiji_knowledge_graph.json`

**导入结果验证：**
脚本使用 `UNWIND` 分批事务，并自动输出节点和关系统计信息，包括：
- 各类型节点数量（KnowledgeNode、Question、Chapter等）
- 各类型关系数量（REQUIRES、BELONGS_TO、HAS_DIFFICULTY等）
- 题目-知识点关联统计

每次运行都会原子写入 `logs/import_failures.json`。报告包含缺失端点、
单条查询失败和最终库内计数；存在失败记录时进程返回非零退出码。

导入后应用当前 Neo4j 5 Schema：

```bash
python scripts/manage_schema.py validate
python scripts/manage_schema.py apply
python scripts/manage_schema.py status
```

`apply` 可重复执行，会创建业务唯一约束、题目筛选/排序索引和 CJK 中文全文索引。

### 启动服务

```bash
# 1. 启动 Neo4j（确保数据库已运行）
neo4j console
# 集成测试可使用一次性 Docker Neo4j；生产部署不强制 Docker

# 2. 启动后端
cd application/backend
python main.py
# 或使用 uvicorn：uvicorn main:app --host 127.0.0.1 --port 8000

# 3. 启动前端（开发模式）
cd application/frontend
npm run dev

# 4. 生产环境构建
cd application/frontend
npm run build
# 构建产物在 dist/ 目录，可部署到 Nginx
```

## 核心功能

### 1. 知识图谱可视化
- 交互式图谱浏览，支持拖拽、缩放、节点筛选
- 节点类型颜色区分（核心抽象/核心实体/关键事件）
- 物理模拟布局，关系高亮

### 2. 智能学习路径规划
- 基于BFS最短路径算法
- 知识点前置依赖分析
- 个性化学习顺序推荐
- 结合已掌握、已完成状态和基础/均衡/挑战训练强度动态调整
- 推荐题综合难度、关系权重和通过率排序

### 3. 智能搜索
- CJK 中文全文检索与相关度排序
- 单字查询兼容回退
- 实时自动补全
- 搜索相关度展示和命中高亮

### 4. 阶段 5 功能
- 图谱路径节点/关系高亮与章节聚类
- 版本化学习进度、掌握度和错题状态接口
- 数据结构/算法设计课程分组与跨课程先修展示
- 离线数据质量报告

### 5. 阶段 6 工程交付
- pytest 后端/API/路径排序测试与隔离 Neo4j 集成测试
- Vitest 前端状态/API 测试和 ESLint 检查
- HTTP 基准、P95 阈值、慢请求/慢查询日志和进程指标
- CI、部署、备份和恢复验收文档

### 6. 阶段 7 总验收
- 后端、前端、严格数据质量、生产构建和隔离 Neo4j 集成测试全量回归
- 真实数据 Schema、全文索引、核心 API、并发请求和性能基准复测
- 桌面端与 390px 移动端真实浏览器验收，覆盖搜索、公式、代码、图谱和学习闭环页面
- 构建产物静态资源引用校验，防止缺失图标或资源进入部署包
- 交付结论与结构性限制见 `docs/阶段7总验收与交付.md`、`docs/已知限制与后续建议.md`

## 数据规模

| 指标 | 数量 |
|------|------|
| 知识点 | 444 |
| 竞赛题目 | 1323 |
| 章节 | 24 |
| 全部关系 | 18369 |
| 题目-知识点关联 | 11905 |

## API 接口

### 图谱数据
```
GET /api/v1/graph/data?limit=2000&node_types=KnowledgeNode
POST /api/v1/graph/nodes/fragment
```

### 数据质量

```bash
python scripts/data_quality_report.py --strict
```

### 智能搜索
```
POST /api/v1/search/
{
  "keyword": "线性表",
  "node_types": ["KnowledgeNode"],
  "limit": 10
}
```

### 阶段 7 验收

```powershell
.\.venv\Scripts\python.exe -m pytest -m "not integration" -q
.\.venv\Scripts\ruff.exe check application/backend knowledge_graph scripts tests import_data.py
.\.venv\Scripts\python.exe scripts\validate_json_data.py
.\.venv\Scripts\python.exe scripts\data_quality_report.py --strict

cd application\frontend
npm run test:run
npm run lint
npm run build
cd ..\..
.\.venv\Scripts\python.exe scripts\validate_frontend_build.py

.\scripts\run_neo4j_integration.ps1
.\.venv\Scripts\python.exe scripts\verify_phase3.py --samples 5 --output logs\phase7_report.json
.\.venv\Scripts\python.exe scripts\verify_async_api.py
.\.venv\Scripts\python.exe scripts\benchmark_api.py --output logs\api_benchmark_phase7.json
```

完整结果、阈值和浏览器抽样范围见 `docs/阶段7总验收与交付.md`。

### 学习路径
```
POST /api/v1/path/shortest
{
  "start": "数据",
  "end": "链表",
  "max_depth": 5
}
```

## 作者信息

- **作者**: 李泊萱 (236004326)
- **指导教师**: 
- **学院**: 宁波大学
- **项目开发时间**: 2026.06 

## 致谢

- [Neo4j](https://neo4j.com/) - 图数据库
- [Vue.js](https://vuejs.org/) - 前端框架
- [Element Plus](https://element-plus.org/) - UI 组件库
- [vis.js](https://visjs.org/) - 网络可视化库

---

**项目状态**: 核心功能已完成
