# API 服务

## 当前状态

核心查询逻辑已经可用，FastAPI 入口已写好。PostgreSQL 默认连接本机：

```text
host=localhost
port=5432
database=historical_agent
user=postgres
password=admin
```

API 会优先使用 PostgreSQL Repository；数据库不可用时，回退到样例 JSON 数据。

## 安装依赖

```bash
python -m pip install -r apps/api/requirements.txt
```

## 启动服务

```bash
python -m uvicorn apps.api.main:app --reload
```

本地前端开发地址 `http://127.0.0.1:5173` 已加入 CORS 允许列表。

## Langfuse 可观测性

默认关闭。开启后，Agent 同步查询、SSE 查询和 worker 执行会通过 `AgentTelemetry` 上报 Langfuse trace、agent observation、model generation、tool observation、token、成本以及完成/失败/取消状态。本系统后台只保留 Langfuse trace 跳转入口，不自研运行分析页。

```bash
set LANGFUSE_ENABLED=true
set LANGFUSE_PUBLIC_KEY=pk-lf-...
set LANGFUSE_SECRET_KEY=sk-lf-...
set LANGFUSE_BASE_URL=https://cloud.langfuse.com
```

如果是自建 Langfuse，把 `LANGFUSE_BASE_URL` 改成自建地址。旧配置 `LANGFUSE_HOST` 仍兼容。

## Agent 工作流引擎

默认使用现有手写 loop：

```bash
set AGENT_WORKFLOW_ENGINE=loop
```

可选开启 LangGraph 适配器：

```bash
set AGENT_WORKFLOW_ENGINE=langgraph
```

当前 LangGraph 第一版是单节点适配器，用来先打通 API、worker、checkpoint 和 telemetry 的引擎切换边界；后续再把模型决策、工具执行、人工确认和完成节点拆成独立 graph nodes。

## 首批接口

```text
GET /health
GET /health/db
GET /events/year/{year}
GET /events/range?start_year=600&end_year=650
GET /events/{event_id}
GET /events/{event_id}/contemporary
GET /events/{event_id}/relations
GET /compare/regions?start_year=600&end_year=650&regions=中东&regions=东亚
POST /agent/query
POST /agent/query/async
POST /agent/query/stream
GET /agent/queue/health
POST /agent/queue/process-one
POST /agent/queue/recover-stale
POST /agent/runs/{run_id}/cancel
POST /imports/batches
GET /imports/batches/{batch_id}
GET /imports/batches/{batch_id}/staging
POST /imports/batches/{batch_id}/confirm
POST /imports/batches/{batch_id}/reject
POST /knowledge/documents
GET /knowledge/search?query=安史之乱&limit=5
POST /admin/events
PATCH /admin/events/{event_id}
POST /admin/events/{event_id}/archive
POST /admin/events/{event_id}/dispute
POST /admin/sources/{source_id}/verify
```

## Agent 查询

同步查询：

```bash
curl -X POST http://127.0.0.1:8000/agent/query ^
  -H "Content-Type: application/json" ^
  -d "{\"input\":\"755年中国发生安史之乱时，中东和中亚发生了什么？\"}"
```

SSE 步骤流：

```bash
curl -N -X POST http://127.0.0.1:8000/agent/query/stream ^
  -H "Content-Type: application/json" ^
  -d "{\"input\":\"帮我生成一张700到800年欧亚大陆历史对照表\"}"
```

SSE 事件类型：

```text
run_started
step_started
tool_called
tool_result
final_answer
run_completed
run_failed
run_cancelled
```

异步提交。接口会创建 `pending` 状态的 `agent_runs`，由 worker 后续领取执行：

```bash
curl -X POST http://127.0.0.1:8000/agent/query/async ^
  -H "Content-Type: application/json" ^
  -d "{\"input\":\"755年中国发生安史之乱时，中东发生了什么？\",\"user_id\":\"demo\"}"
```

查看队列健康状态：

```bash
curl http://127.0.0.1:8000/agent/queue/health
```

本地手动处理一个排队任务：

```bash
curl -X POST http://127.0.0.1:8000/agent/queue/process-one
```

也可以用 worker CLI：

```bash
python -m apps.worker.agent_worker --once
```

手动回收超时 processing 任务：

```bash
curl -X POST http://127.0.0.1:8000/agent/queue/recover-stale
python -m apps.worker.agent_worker --recover-stale
```

取消运行：

```bash
curl -X POST http://127.0.0.1:8000/agent/runs/{run_id}/cancel ^
  -H "Content-Type: application/json" ^
  -d "{\"reason\":\"用户取消\"}"
```

## 数据导入审核

创建导入批次。数据会先进入 `import_event_staging`，不会直接写入正式事件表：

```bash
curl -X POST http://127.0.0.1:8000/imports/batches ^
  -H "Content-Type: application/json" ^
  -d "{\"filename\":\"events.json\",\"created_by\":\"admin\",\"events\":[...]}"
```

查看批次和逐行校验结果：

```bash
curl http://127.0.0.1:8000/imports/batches/{batch_id}
curl http://127.0.0.1:8000/imports/batches/{batch_id}/staging
```

确认入库。只有没有校验错误的批次可以确认：

```bash
curl -X POST http://127.0.0.1:8000/imports/batches/{batch_id}/confirm ^
  -H "Content-Type: application/json" ^
  -d "{\"confirmed_by\":\"admin\"}"
```

拒绝批次：

```bash
curl -X POST http://127.0.0.1:8000/imports/batches/{batch_id}/reject ^
  -H "Content-Type: application/json" ^
  -d "{\"reason\":\"来源不足\"}"
```

## 知识库检索

写入知识文档。当前会用本地确定性 embedding 生成器写入 `knowledge_chunks.embedding vector(1536)`，方便离线开发和测试：

```bash
curl -X POST http://127.0.0.1:8000/knowledge/documents ^
  -H "Content-Type: application/json" ^
  -d "{\"title\":\"安史之乱资料\",\"content\":\"安史之乱爆发于755年...\",\"citation\":\"资料来源\"}"
```

语义检索：

```bash
curl "http://127.0.0.1:8000/knowledge/search?query=安史之乱 唐朝 755&limit=5"
```

## 事件管理和人工确认

写操作需要后端硬校验 `admin_token` 和 `confirmed=true`。本地默认 token 是 `admin`，可通过 `ADMIN_API_TOKEN` 环境变量覆盖。

新增事件会先复用导入审核流校验，再确认入库：

```bash
curl -X POST http://127.0.0.1:8000/admin/events ^
  -H "Content-Type: application/json" ^
  -d "{\"admin_token\":\"admin\",\"confirmed\":true,\"confirmed_by\":\"admin\",\"event\":{...}}"
```

修改、归档、争议标记和来源核验：

```bash
curl -X PATCH http://127.0.0.1:8000/admin/events/{event_id} ^
  -H "Content-Type: application/json" ^
  -d "{\"admin_token\":\"admin\",\"confirmed\":true,\"confirmed_by\":\"admin\",\"updates\":{\"summary\":\"修订后的摘要\",\"confidence\":0.85},\"reason\":\"来源复核\"}"

curl -X POST http://127.0.0.1:8000/admin/events/{event_id}/dispute ^
  -H "Content-Type: application/json" ^
  -d "{\"admin_token\":\"admin\",\"confirmed\":true,\"reason\":\"来源存在争议\"}"

curl -X POST http://127.0.0.1:8000/admin/sources/{source_id}/verify ^
  -H "Content-Type: application/json" ^
  -d "{\"admin_token\":\"admin\",\"confirmed\":true,\"reliability\":0.9,\"reason\":\"来源核验通过\"}"
```

所有事件和来源写操作会记录到 `event_change_logs`。

## 说明

当前 Agent Runtime 已支持 ModelAdapter、OpenAI Function Calling、ToolRegistry、ToolExecutor、工具参数校验、超时、重试、模型 token/耗时/成本记录、SSE 步骤流、运行取消、Redis 队列/Worker、processing ack、失败重试、死信队列、visibility timeout 回收、checkpoint 恢复执行、数据导入审核流、知识库 pgvector 检索、事件管理和人工确认 MVP。React 工作台在 `apps/web`，支持 Agent SSE、横向对照表和事件详情。
