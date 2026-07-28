# AI智能体开发计划表

计划起始日期：2026-07-28  
参考文档：AI智能体开发大纲工作.pdf  
业务方向：历史时间对照 Agent  
总体目标：先完成一个可运行、可追踪、可恢复、可评测的单智能体系统，用于横向对照不同国家、地区和文明在同一时间点或时间段发生的历史事件，再逐步补齐知识库、记忆、安全、MCP 和平台化能力。

## 总体阶段安排

| 阶段 | 时间 | 核心目标 | 主要交付物 | 验收标准 |
|---|---:|---|---|---|
| 阶段 0：产品边界与技术准备 | 第 1 周 | 明确智能体服务对象、任务边界、自主等级和禁止行为 | PRD、任务清单、风险清单、技术选型、项目骨架 | 能说清楚智能体要替用户完成哪些可验收任务，以及哪些操作必须确认或禁止 |
| 阶段 1：基础 MVP | 第 2-3 周 | 做出最小可用单智能体 | React 聊天页、FastAPI 接口、单模型接入、流式回复、3 个只读工具、手写 Agent Loop | 智能体可根据用户目标选择工具，连续执行 2-5 步后返回真实结果 |
| 阶段 2：任务型 Agent | 第 4-6 周 | 引入任务状态、工作流、恢复和人工确认 | LangGraph 工作流、PostgreSQL 任务状态、SSE 步骤流、取消/重试/恢复、Playwright 工具 | 服务重启后任务可恢复，高风险操作会暂停等待用户确认 |
| 阶段 3：知识与记忆 | 第 7-8 周 | 增加 RAG、引用来源、对话摘要和长期偏好 | 文档上传、pgvector、混合检索、来源引用、用户偏好、权限过滤 | 回答能引用正确来源，用户之间无法检索到彼此的数据 |
| 阶段 4：生产安全与评测 | 第 9-11 周 | 建立权限、安全、审计、评测和观测体系 | RBAC、多租户、工具权限策略、Prompt Injection 防护、Trace、成本统计、评测集、回归测试 | 每次 Prompt 或模型升级都能通过自动化评测判断质量变化 |
| 阶段 5：平台化增强 | 第 12 周及以后 | 把单智能体能力产品化、配置化、可运营化 | 工具管理、Prompt 版本、模型配置、MCP 接入、智能体模板、运行监控、用户反馈闭环 | 可以通过配置创建或调整智能体，而不是每次改代码 |

## 每周执行计划

| 周次 | 日期范围 | 本周重点 | 具体任务 | 输出物 |
|---|---|---|---|---|
| 第 1 周 | 2026-07-28 至 2026-08-03 | 产品边界和架构定型 | 明确目标用户；拆出 5-10 个可验收任务；定义 L2/L3 自主等级；列出禁止行为；确定首版工具清单；初始化项目目录 | `docs/product_scope.md`、`docs/risk_policy.md`、项目骨架 |
| 第 2 周 | 2026-08-04 至 2026-08-10 | 基础前后端和模型接入 | 搭建 React + TypeScript + Vite；搭建 FastAPI；封装 Model Adapter；实现 SSE 流式输出；完成基础聊天界面 | 可运行的前后端 Demo |
| 第 3 周 | 2026-08-11 至 2026-08-17 | 手写 Agent Loop 和只读工具 | 实现 Agent Loop；定义 ToolDefinition；实现工具注册表；接入年份查询、时间段查询、事件详情、地区对照工具；加入最大步数、超时和基础日志 | MVP Agent，可完成 2-5 步工具调用 |
| 第 4 周 | 2026-08-18 至 2026-08-24 | PostgreSQL 数据底座和任务状态 | 导入样例历史事件；实现 PostgreSQL Repository；把查询从 JSON 切到 PostgreSQL；设计任务表、步骤表、工具调用表；记录每次模型调用和工具调用 | 查询真实数据库，可查询、可回放的任务执行记录 |
| 第 5 周 | 2026-08-25 至 2026-08-31 | LangGraph 和恢复机制 | 引入 LangGraph；实现 Checkpoint；支持取消、重试、恢复；把步骤状态通过 SSE 推给前端 | 重启后可继续执行的任务型 Agent |
| 第 6 周 | 2026-09-01 至 2026-09-07 | 浏览器工具和人工确认 | 接入 Playwright；设计受控浏览器工具；实现人工确认中断；为高风险工具增加权限判断和审计 | 浏览器自动化任务 Demo，高风险操作可暂停确认 |
| 第 7 周 | 2026-09-08 至 2026-09-14 | 知识库和 RAG | 实现文档上传；文档解析、切分、入库；接入 pgvector；实现混合检索和来源引用 | 能基于文档回答并给出来源 |
| 第 8 周 | 2026-09-15 至 2026-09-21 | 记忆和上下文工程 | 实现对话摘要；区分任务状态、短期上下文、长期偏好、知识库；加入数据权限过滤；裁剪工具返回内容 | 长任务上下文不失控，记忆可控且可追溯 |
| 第 9 周 | 2026-09-22 至 2026-09-28 | 权限和安全基线 | 实现用户身份、RBAC、多租户隔离；工具按风险分级；防 Prompt Injection；限制文件、网络、执行范围 | 权限不依赖模型判断，高风险路径有后端硬校验 |
| 第 10 周 | 2026-09-29 至 2026-10-05 | 可观测性和成本统计 | 接入 OpenTelemetry；记录 Run、Model Call、Tool Call；统计 token、耗时、失败原因、工具成功率 | 每个任务有完整 Trace 和成本视图 |
| 第 11 周 | 2026-10-06 至 2026-10-12 | 评测和回归测试 | 建立 Agent Evaluation Dataset；设计期望工具、禁止工具、最大步数、期望结果；加入 Prompt Injection、权限、断网、并发测试 | Prompt 或模型升级前后可自动对比质量 |
| 第 12 周 | 2026-10-13 至 2026-10-19 | 平台化第一版 | 工具管理页面；Prompt 版本管理；模型配置；MCP 接入试点；运行监控；用户反馈入口 | 具备从项目 Demo 向内部平台演进的基础 |

## 优先学习清单

| 优先级 | 知识点 | 学习目标 |
|---:|---|---|
| 1 | Python 异步编程 | 能写稳定的异步工具执行、超时、取消和并发控制 |
| 2 | FastAPI | 能搭建 Agent API、SSE、鉴权和后台任务接口 |
| 3 | Pydantic + JSON Schema | 能约束模型输出和工具入参 |
| 4 | 大模型消息协议 | 理解 System、Developer、User、Assistant、Tool Call、Tool Result |
| 5 | Function Calling | 能让模型稳定选择工具并传入结构化参数 |
| 6 | Agent Loop / ReAct | 理解模型决策、工具执行、观察结果、继续判断的闭环 |
| 7 | 工具设计 | 能设计单一职责、权限清晰、可审计的工具 |
| 8 | Prompt 和上下文工程 | 能控制上下文长度、摘要、裁剪和抗污染 |
| 9 | LangGraph | 能实现持久化执行、人工中断和失败恢复 |
| 10 | PostgreSQL + Redis | 能保存任务状态、执行日志、锁和队列 |
| 11 | Playwright | 能实现受控浏览器自动化 |
| 12 | RAG + pgvector | 能做文档检索、引用来源和权限过滤 |
| 13 | MCP | 能把外部工具标准化接入 |
| 14 | OAuth2 + RBAC + 多租户 | 能建立真实权限系统 |
| 15 | OpenTelemetry | 能追踪模型调用、工具调用和外部 API |
| 16 | Agent 评测 | 能用任务集衡量智能体质量 |
| 17 | Docker 部署 | 能用 Docker Compose 部署首版系统 |
| 18 | 沙箱和安全隔离 | 能限制模型生成代码、文件访问和网络访问 |

## 首版项目目录建议

```text
ai-agent/
  apps/
    api/
    worker/
    web/
  agent/
    runtime/
    prompts/
    models/
    context/
    memory/
    policies/
    workflows/
  tools/
    registry/
    browser/
    files/
    database/
    business/
  knowledge/
    loaders/
    chunking/
    retrieval/
    reranking/
  evaluation/
    datasets/
    graders/
    regression/
  infrastructure/
    database/
    queue/
    telemetry/
    docker/
  tests/
  docs/
```

## 第一版范围控制

第一版只做：单智能体、少量可靠工具、完整执行记录。  
第二版补：状态持久化、人工确认、评测。  
最后再做：RAG、MCP、多智能体和平台化。

不建议一开始做多智能体。只有当角色权限完全不同、上下文过大、任务可并行、不同步骤需要不同模型，或者单 Agent 工具太多导致选择变差时，再考虑拆分 Planner、Executor、Researcher、Reviewer、Supervisor 等角色。

## 当前实际进度

更新时间：2026-07-28

### 最近一次进度更新

| 时间 | 本次完成 | 验证结果 | 下一步 |
|---|---|---|---|
| 2026-07-28 | 完成 checkpoint 恢复执行 MVP：从 `agent_steps` 重建已完成工具调用上下文，worker 恢复时从下一步继续执行 | 单元测试 40/40 通过；MVP 评测 4/4 通过 | 进入 React 查询页和横向对照表 UI，或把手写 checkpoint 迁移到 LangGraph |

### 当前状态摘要

| 项目 | 当前状态 |
|---|---|
| 当前阶段 | 后端基础 MVP、任务型 Agent 运行状态 MVP、Redis 队列/Worker MVP、checkpoint 恢复 MVP、数据导入审核流 MVP、RAG 检索 MVP、事件管理/人工确认 MVP 已完成 |
| 已完成主链路 | FastAPI API、PostgreSQL、pgvector、历史查询工具、Agent Loop、Function Calling、执行记录、自动评测、SSE 步骤流、运行取消、异步提交/Worker 执行、checkpoint 恢复、数据导入审核、知识库检索、受控事件管理 |
| 当前可运行能力 | 用户可通过 `/agent/query` 同步提问，通过 `/agent/query/stream` 实时查看 Agent 工具调用过程，也可通过 `/agent/query/async` 异步提交并由 Redis Worker 执行和恢复 |
| 当前验证结果 | 单元测试 40/40 通过，MVP 评测 4/4 通过 |
| 下一步重点 | React 查询页和横向对照表 UI，或把手写 checkpoint 迁移到 LangGraph |
| 暂不推进 | 多智能体、MCP、Playwright、复杂 RBAC、Kubernetes，等单 Agent 与数据管理链路稳定后再做 |

| 模块 | 状态 | 已在线完成的功能 | 对应 PDF 功能/章节 |
|---|---|---|---|
| 产品边界 | 已完成 | 明确历史时间对照 Agent 的 MVP 范围、首批时间范围和地区范围 | 第一阶段：确定智能体产品边界 |
| 项目骨架 | 已完成 | 创建 `apps`、`agent`、`tools`、`data`、`evaluation`、`infrastructure`、`docs`、`tests` 等目录 | 十八：推荐项目目录 |
| 技术总纲 | 已完成 | PDF 已放入项目目录，并转化为本项目计划表和技术设计文档 | 总体技术栈、十九：推荐开发顺序 |
| PostgreSQL 数据库 | 已完成 | 创建 `historical_agent` 数据库并接入本地 PostgreSQL，默认用户 `postgres` | 最终技术选型：主数据库 PostgreSQL |
| pgvector | 已完成 | 安装并启用 `vector 0.8.2`，`historical_events.embedding vector` 字段已存在 | 第八阶段：RAG 知识库；最终技术选型：pgvector |
| 表结构 | 已完成 | 创建 22 张表，覆盖地区、政权、事件、来源、关系、导入、Agent 运行、评测、知识库和事件审计 | 第七阶段：状态、记忆和上下文；第十三阶段：评测体系 |
| 样例数据 | 已完成 | 准备并导入 `600-900` 年 9 条样例事件、9 条来源、18 条事件分类 | 第八阶段：RAG 知识库前的数据底座 |
| FastAPI 查询接口 | 已完成 | `/health`、`/health/db`、年份查询、时间段查询、地区对照、事件详情接口已可用 | 最终技术选型：API FastAPI |
| 历史查询工具 | 已完成 MVP | 支持 `search_events_by_year`、`search_events_by_range`、`compare_regions`、`get_event_detail`、`find_contemporary_events`、`find_related_events` | 第四阶段：设计工具系统 |
| PostgreSQL Repository | 已完成 | API 默认查询 PostgreSQL，JSON 样例数据作为 fallback | 最终技术选型：PostgreSQL；工具返回真实系统结果 |
| Agent 执行记录 | 已完成 MVP | 每次 Agent 查询写入 `agent_runs` 和 `agent_steps`，可按 `run_id` 回放 | 第十一阶段：任务持久化与故障恢复；第十四阶段：可观测性 |
| 自动评测 | 已完成 MVP | `evaluation.runner` 可写入 `evaluation_runs`，当前 MVP 评测 4/4 通过 | 第十三阶段：评测体系 |
| 规则 Agent 路由 | 已完成 | 支持年份题、时间段题、地区对照题、事件关系题的多步工具调用 | 第三阶段：实现最小 Agent Loop |
| ModelAdapter | 已完成 MVP | 已有可替换模型适配器接口、`RuleBasedModelAdapter` 和模型工厂 | 第二阶段：学习大模型基础；系统架构：Model Adapter |
| OpenAI Function Calling | 已完成 MVP | 已把 ToolRegistry 转换为 OpenAI tools，可通过环境变量切换真实模型 | 第二阶段：Structured Output；最终技术选型：JSON Schema Function Calling |
| ToolRegistry / ToolExecutor | 已完成 MVP | 已实现 `ToolDefinition`、`ToolRegistry`、`ToolExecutor`，统一执行历史查询工具 | 第四阶段：设计工具系统 |
| Function Calling 稳定性 | 已完成 MVP | ToolExecutor 已支持 JSON Schema 参数校验、默认值填充、单工具超时、幂等工具重试、失败观察结果 | 第三阶段：参数校验、超时、重试、失败处理 |
| 模型观测和成本统计 | 已完成 MVP | Agent 步骤已记录模型输入摘要、输出摘要、token 输入/输出、模型耗时和估算成本 | 第三阶段：Token/成本预算；第十四阶段：可观测性 |
| SSE 步骤流 | 已完成 MVP | 新增 `/agent/query/stream`，实时输出 run_started、step_started、tool_called、tool_result、final_answer 等事件 | 第十六阶段：前后端通信；系统架构：API Gateway SSE |
| Agent 运行状态增强 | 已完成 MVP | 已新增取消入口 `/agent/runs/{run_id}/cancel`，Loop 会检查 cancelled 状态，失败/取消不会被误标 completed | 第十一阶段：任务持久化与故障恢复 |
| Redis 队列 / Worker | 已完成 MVP | 已新增 `/agent/query/async`、`/agent/queue/health`、`/agent/queue/process-one`、`/agent/queue/recover-stale` 和 `apps.worker.agent_worker`，支持 Redis list 入队、processing 队列、worker 消费、PostgreSQL 原子 claim、成功 ack、失败重试、死信队列、visibility timeout 回收和结果回放 | 系统架构：Task Worker；第十一阶段：任务持久化与故障恢复 |
| checkpoint 恢复执行 | 已完成 MVP | 已新增 `AgentLoop.resume_existing`，可从 `agent_steps` 重建历史工具调用上下文，worker 恢复 pending run 时从下一步继续 | 第十一阶段：Checkpoint；LangGraph 迁移前置能力 |
| 数据导入审核流 | 已完成 MVP | 已支持 import batch、staging、逐行校验、确认入库、拒绝批次，错误行不会进入正式表 | 第十阶段：人工确认机制；第十二阶段：安全体系 |
| RAG / pgvector 检索 | 已完成 MVP | 已新增 `knowledge_documents`、`knowledge_chunks`、本地 embedding、文档入库和 `/knowledge/search` 检索 | 第八阶段：RAG 知识库 |
| 事件管理和人工确认 | 已完成 MVP | 已新增 `/admin/events`、修改、归档、争议标记、来源核验接口；写操作必须带 `admin_token` 和 `confirmed=true`，并写入 `event_change_logs` 审计日志 | 第十阶段：人工确认机制；第十二阶段：安全体系；平台化第一版 |
| 手写 Agent Loop | 已完成 MVP | API 和评测已切换到新 Loop，支持最大步数、步骤记录、工具结果裁剪 | 第三阶段：实现最小 Agent Loop |
| 后端缺口审查 | 已完成 | 已形成 `docs/backend_gap_review.md`，记录与 PDF 技术栈的差距 | 第十九：推荐开发顺序；第二十二：最终技术选型建议 |
| 前端 | 暂后 | 尚未开始 React 查询页和横向对照表 UI | 第一阶段 MVP：React 聊天页面、流式回复 |

### 紧要但未完成的能力

| 优先级 | 后端能力 | 当前状态 | 为什么紧要 | 对应 PDF 功能/章节 |
|---:|---|---|---|---|
| 1 | React 查询页和横向对照表 UI | 未完成 | 后端主链路已经较完整，下一步需要让用户能真实使用年份查询、SSE 步骤流和横向对照表 | 第一阶段 MVP：React 聊天页面；业务可视化前端 |
| 2 | 完整 RBAC / 多租户权限 | 未完成 | 当前只有 admin token + confirmed MVP，后续上线需要用户身份、角色、租户隔离和权限策略落库 | 第十二阶段：安全体系 |
| 3 | LangGraph checkpoint / 恢复机制 | 未完成 | 当前手写 Agent Loop 已有 checkpoint 恢复 MVP；还未迁移到 LangGraph 原生 checkpoint / interrupt | 第六阶段：模型决策和固定工作流结合；第十一阶段：Checkpoint |
| 4 | RAG 增强 | 部分完成 | MVP 已有本地 embedding 和 pgvector 检索；还缺真实模型 embedding、混合检索、引用注入 Agent 回答 | 第八阶段：RAG 知识库 |
| 5 | 数据导入审核增强 | 部分完成 | MVP 已有 staging、校验、确认入库；还缺差异预览、批量修正和导入任务异步化 | 第十阶段：人工确认机制；第十二阶段：安全体系 |
| 6 | 标准 Trace / 成本汇总 | 部分完成 | 已有数据库记录，但还没有 OpenTelemetry、Langfuse/LangSmith 或成本报表 | 第十四阶段：可观测性 |

## 后端下一步建议

对照 PDF 技术栈，后端 MVP 已完成查询、数据库、执行记录、评测闭环和手写 Agent Loop。建议下一步优先补：

| 优先级 | 接下来准备做什么 | 目标 | 对应 PDF 功能/章节 |
|---:|---|---|---|
| 1 | Function Calling 参数校验、工具超时、错误重试 | 已完成 MVP：模型错误参数会被拦截，工具超时会失败返回，幂等工具支持重试 | 第三阶段：最小 Agent Loop 必须补齐参数校验、超时、重试 |
| 2 | 模型 token、耗时、成本统计 | 已完成 MVP：步骤记录可查看模型摘要、token、耗时和估算成本 | 第十四阶段：可观测性 |
| 3 | SSE 步骤流 | 已完成 MVP：`/agent/query/stream` 可逐步输出 Agent 运行事件 | 第十六阶段：前后端通信；系统架构：API Gateway SSE |
| 4 | Agent 运行状态增强 | 已完成 MVP：支持 cancelled 入口，失败/取消状态不会误标 completed | 第十一阶段：任务持久化与故障恢复 |
| 5 | 数据导入审核流 | 已完成 MVP：支持 staging、校验、人工确认、正式入库，避免污染历史事件表 | 第十阶段：人工确认机制；第十二阶段：安全体系 |
| 6 | RAG / embedding / pgvector 检索 | 已完成 MVP：pgvector 已参与知识文档语义检索 | 第八阶段：RAG 知识库 |
| 7 | 事件管理接口和权限/人工确认 | 已完成 MVP：新增、修改、归档、争议标记、来源核验，写操作需 admin token 和显式确认 | 平台化第一版；工具权限策略；第十二阶段：安全体系 |
| 8 | React 查询页和横向对照表 UI | 做出可交互的年份查询、时间段对照表和 Agent 分析区 | 第一阶段基础 MVP；前端 React + TypeScript |
| 9 | Redis / Worker / 任务队列 | 已完成 Redis 队列/Worker、processing ack、失败重试、死信队列、visibility timeout 回收和 checkpoint 恢复 MVP | 系统架构：Task Worker；最终技术选型：Redis |
| 10 | LangGraph 工作流 | 后续增强：把当前手写 Loop、checkpoint 和人工确认迁移到 LangGraph | 第六阶段：模型决策和固定工作流结合；第十一阶段：Checkpoint |
| 11 | MCP 接入 | 等本地工具边界稳定后，把核心工具服务标准化给外部智能体复用 | 第九阶段：MCP 能力标准化 |

详细缺口见 [backend_gap_review.md](docs/backend_gap_review.md)。
