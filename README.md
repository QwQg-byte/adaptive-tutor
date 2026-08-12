# 自适应算法学习平台（伴学 Agent + 知识图谱）

面向程序设计/算法学科的自适应学习平台。当前仓库已合并伴学 Agent、
Neo4j 图谱 FastAPI、Vue 3 图谱前端和图谱构建/验收工具。
主脑 LLM 把**知识图谱**当工具调：诊断学情 → 规划路径 → 脚手架辅导 → 记忆反思。
暂不接 OJ（权属留待后议）。

## 当前进度（2026-08-03）

| 阶段 | 状态 | 说明 |
|---|---|---|
| 1 学情诊断 | ✅ 已实现 | `diagnose.py`：挑靠下游代表节点出题，答对沿前置边软置信一跳，少考多推断 |
| 2 路径接入 | ✅ 已实现 | `generate_learning_plan` 按画像自动裁剪已覆盖前置 |
| 3 脚手架辅导 | ✅ 已实现 | `get_knowledge_detail` 接地图谱内容 + SYSTEM 分层提示规则，讲解/卡住时循序引导不直接给答案 |
| 4 长期记忆 | ✅ 已实现 | `learner_model.py`：SQLite 存掌握度(EMA)+事件流，供裁剪与反思 |
| 5 GraphRAG | ✅ 已实现 | `graph_rag.py`：自然语言实体检索 + 一跳相关子图扩展 + 学情标注 + 有界证据包 |
| 6 Demo UI | ✅ 已实现并验收 | `web_server.py` + `web_ui.html`，闭环可演示"诊断→画像→路径变短"；顶部「主题」框可切任意知识点 |
| 7 学习状态统一 | ✅ 已实现并验收 | SQLite 成为唯一学习事实源；助手与图谱共用 learner API、`student_id`、`revision`、错题和目标级路径进度 |

## 核心机制

- **意图预路由**（`tutor_agent.route_intent`）：命中明确意图时强制第一跳调对应工具，治 DeepSeek 在 auto 下偷懒不调工具的毛病；其余交给 auto。
- **诊断软置信传播**（`diagnose.py`）：答对一道下游代表题 → 该节点记为掌握，并把它的**直接前置**软置信到一个较高起点（`SEED_PREREQ=0.55`），只传播一跳，稳妥不级联。
- **脚手架辅导接地**（`graph_tools.knowledge_detail`）：讲解或做题卡住时，先从图谱取真实教学内容（概述/基本思想/性质/求解步骤/经典题型/前置），再据此给**分层提示**（先点方向 → 关键概念 → 求解步骤），逐层深入而非直接给答案；绝不凭空编。该检索原语也是阶段5 GraphRAG 的基础。
- **GraphRAG 子图检索**（`graph_rag.retrieve`）：关系/对比/前置类问题先解析多个核心知识点，再扩展一跳前置、后继和语义关系；证据包限制为 3–12 个节点，附 `K1...` 证据编号与学习者掌握状态。LLM 只能依据返回的 `nodes/edges` 作答，图中缺证据时必须明说。
- **统一学习状态**（`learning_state.LearningStateService`）：SQLite 原子记录掌握证据、目标级步骤进度、题目尝试和错题投影；所有写入带幂等键并递增 `revision`。Neo4j 只提供知识、题目关系和无状态路径拓扑。
- **两个掌握度阈值**（刻意区分，别混用）：
  - `MASTERY_THRESHOLD=0.7` —— 判"已掌握"，画像打 ✓、判强弱项，**给人看**；
  - `PRUNE_THRESHOLD=0.5` —— 判"可裁剪"，喂给路径引擎裁前置，**给引擎用**。
  软置信前置(0.55)够得到裁剪线、够不到掌握线：既能立刻让路径变短，画像上又诚实显示为薄弱，后续真题再确认。

## 首次安装

环境要求：Python 3.11+、Node.js 18+、Neo4j 5.x。默认 Neo4j 目录为
`C:\neo4j-community-5.4.0`，也可通过 `NEO4J_HOME` 指定。

```powershell
cd C:\adaptive-tutor
Copy-Item .env.example .env
# 编辑 .env，填写 DEEPSEEK_API_KEY 与 NEO4J_PASSWORD

.\.venv\Scripts\python.exe -m pip install -r requirements.txt
cd graph\application\frontend
npm ci
cd ..\..\..
```

图谱重建所需的最终数据已纳入 `graph/data/processed`（约 12 MB）。已有本地 Neo4j
全量库可直接使用；只有需要重建数据库时才运行：

```powershell
cd C:\adaptive-tutor\graph
..\.venv\Scripts\python.exe import_data.py
```

> `import_data.py` 默认会清理并重建当前 Neo4j 数据库，已有数据时不要运行。

## 一键运行

根目录执行：

```powershell
.\start_all.ps1
```

脚本按顺序启动或复用 Neo4j、图谱 API、Tutor 和图谱前端：

| 服务 | 地址 |
|---|---|
| 伴学 Agent | http://127.0.0.1:8600 |
| Tutor / learner API 文档 | http://127.0.0.1:8600/docs |
| 知识图谱 | http://127.0.0.1:5173 |
| 图谱 API 文档 | http://127.0.0.1:8000/docs |
| Neo4j Browser | http://127.0.0.1:7474 |

两套 UI 顶部可以互相跳转。停止整套服务：

```powershell
.\stop_all.ps1
```

需要保留 Neo4j 时使用 `.\stop_all.ps1 -KeepNeo4j`。

> **主题不限于动态规划**：全量图谱共 1965 个实体（当前 444 个知识点、1335 道题）都能诊断/讲解/规划。Demo UI 顶部有「主题」输入框，
> 「规划路径」「讲讲这个」按钮按该主题走（默认动态规划，可改成 快速排序 / 二分查找 / 哈希表 / 图 等）；
> 摸底诊断会自动轮换 7 个代表知识点（DP、递归、分治、穷举、二分查找、线性表、图），不只考 DP。

## 语音后端

讯飞语音听写和在线语音合成已通过独立服务层接入，DeepSeek 仍负责 Agent 推理。启用配置：

```dotenv
VOICE_ENABLED=true
VOICE_PROVIDER=xfyun
XFYUN_VOICE_APP_ID=
XFYUN_VOICE_API_KEY=
XFYUN_VOICE_API_SECRET=
XFYUN_TTS_VOICE=xiaoyan
```

主要接口：

| 接口 | 作用 |
|---|---|
| `GET /api/voice/capabilities` | 查询功能开关、格式和大小限制 |
| `POST /api/voice/transcriptions` | 上传 WAV、WebM/Opus、Ogg/Opus 或 MP4/M4A，返回待确认文字 |
| `POST /api/voice/speech` | 把 Agent 文本合成为不可缓存的 MP3 |

上传接口使用文件的实际 `Content-Type` 指定格式，并通过 FFmpeg 解码校验内容；兼容 iOS/微信常见的 MP4/M4A 音频。
默认限制为 5 MB、60 秒，TTS 最多 2000 字符。密钥只在服务端使用，语音关闭或上游失败不影响文本接口。
Tutor 页面已接入麦克风、录音计时、转写确认、逐条回复播放/停止和自动朗读开关。转写结果只回填输入框，
不会自动发送；学生确认或修改后仍通过原有 `/api/chat` 进入 Agent。自动朗读默认只作用于语音输入触发的回复，
设置保存在浏览器本地。浏览器不支持录音或语音服务关闭时，文本输入保持可用。公网录音必须使用 HTTPS。

## 统一学习状态与迁移

`data/learner.db` 是学习者动态数据的唯一事实源。助手页面和图谱页面使用同一个
`adaptive_tutor_student_id`，跨端口跳转通过 `?student=...` 显式传递身份。主要接口为：

| 接口 | 作用 |
|---|---|
| `GET /api/learners/{student_id}/state` | 完整画像、掌握状态、路径进度、错题和事件快照 |
| `GET /api/learners/{student_id}/dashboard` | 章节聚合、掌握分布、趋势和推荐目标 |
| `POST /api/learners/{student_id}/plans` | 按服务端画像生成个性化路径并挂接复习任务 |
| `PATCH .../knowledge/{node_id}` | 更新手动学习状态 |
| `PUT .../plans/{target_id}/steps/{node_id}` | 更新目标内的步骤进度 |
| `POST .../attempts` | 原子记录作答、掌握证据和错题状态 |
| `GET/PATCH .../mistakes` | 查询或手动解决错题 |
| `POST .../imports/local-v1` | 预览或幂等导入旧浏览器状态 |

写接口使用 `expected_revision` 检测并发冲突，过期快照返回 `409`；前端刷新整组状态后重试。
客户端不能提交 `mastered` 或知识点归因来伪造掌握度。

图谱前端检测到旧 `kg_learning_state_v1` 时，会先显示迁移摘要，经确认后调用服务端导入，
并报告导入、跳过和冲突数量。旧数据只读保留，可在错题页导出 JSON 备份；新学习事实不再写回
该键。`UNIFIED_LEARNING_STATE=false` 仅用于短期兼容回滚，不会删除已迁移的 SQLite 数据。

## 验证

```powershell
# Tutor / 统一状态
.\.venv\Scripts\python.exe -m pytest -q .\test_graph_rag.py .\test_learning_state.py .\test_voice_service.py

# 图谱后端
cd graph
..\.venv\Scripts\python.exe -m pytest -m "not integration" -q
..\.venv\Scripts\ruff.exe check application/backend knowledge_graph scripts tests import_data.py

# 图谱前端
cd application\frontend
npm run test:run
npm run lint
npm run build
npx playwright test e2e/tutor-voice.spec.js
npm run test:e2e
```

## 结构

| 文件 | 作用 |
|---|---|
| `graph/application/backend/` | 合并后的知识图谱 FastAPI 后端 |
| `graph/application/frontend/` | Vue 3 图谱浏览、搜索、路径与题目 UI |
| `graph/knowledge_graph/` | Neo4j 构图、连接与 Schema 管理 |
| `graph/scripts/` / `graph/tests/` | 图谱质量、性能、契约与集成验收 |
| `graph/data/processed/` | 可重建图谱的最终知识点/题目 JSON |
| `start_all.ps1` / `stop_all.ps1` | 合并项目一键启停 |
| `config.py` | 配置（图谱地址、LLM provider、掌握度/裁剪阈值，读 .env） |
| `llm.py` | LLM 抽象层（DeepSeek / 星火预留） |
| `graph_client.py` | 图谱后端客户端 |
| `graph_tools.py` | 图谱工具 schema + dispatch |
| `graph_rag.py` | GraphRAG：多实体检索、有界子图扩展、证据压缩与学情标注 |
| `learning_state.py` | 统一学习状态服务：迁移、掌握证据、目标进度、尝试、错题和 revision |
| `learner_model.py` | 兼容旧调用的 facade，内部转调 `LearningStateService` |
| `diagnose.py` | 学情诊断：代表题挑选 + 软置信前置传播 |
| `tutor_agent.py` | Agent 主循环 + 意图预路由 |
| `web_server.py` | Demo UI 服务端（FastAPI，:8600） |
| `voice_service.py` | 讯飞 ASR/TTS、FFmpeg 音频转换、限制和统一错误 |
| `voice_smoke.py` | 讯飞真实服务独立冒烟工具 |
| `web_ui.html` | Demo UI 前端（对话 + 语音交互 + 画像 + 路径对比） |
| `smoke_test.py` | 图谱连通冒烟（不需 LLM key） |
| `scaffold_smoke.py` | 脚手架辅导冒烟（讲解/卡住→接地→分层提示） |
| `test_graph_rag.py` | GraphRAG 离线单测（不需要图谱后端或 LLM key） |
| `test_learning_state.py` | SQLite migration、统一 API、幂等、并发、错题与迁移规则测试 |
| `graphrag_smoke.py` | GraphRAG 真对话冒烟（路由→子图证据→LLM 回答） |
| `*_smoke.py` / `diagnose_*.py` | 各环节调试脚本 |

## 备注

- `graph/application/backend/.env` 可作为图谱服务的本机覆盖配置；新环境优先只维护根 `.env`。
- 原 `C:\Know\knowledge` 目录未改动。合并项目验证完成后可独立归档，但不应在确认前删除。
- 星火接入 = 分叉点 B，确认赛题是否强制后在 `llm.py` 补 `SparkClient`。
