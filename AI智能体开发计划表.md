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
| 阶段 4：生产安全与评测 | 第 9-11 周 | 建立权限、安全、审计、评测和观测体系 | RBAC、多租户、工具权限策略、Prompt Injection 防护、Langfuse 集成、评测集、回归测试 | 每次 Prompt 或模型升级都能通过自动化评测和 Langfuse 观测判断质量变化 |
| 阶段 5：平台化增强 | 第 12 周及以后 | 把单智能体能力产品化、配置化、可运营化 | 数据管理后台、知识库后台、向量管理、工具配置、模型配置、MCP 接入、用户反馈闭环 | 可以通过管理后台维护业务数据和知识库，通过 Langfuse 查看 Agent 运行与评测 |

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
| 第 10 周 | 2026-09-29 至 2026-10-05 | Langfuse 可观测性集成 | 接入 Langfuse；上报 Run、Model Call、Tool Call、token、耗时、失败原因、成本数据；后台只保留 Langfuse 跳转入口 | 每个任务可在 Langfuse 查看完整 Trace、成本和工具调用链 |
| 第 11 周 | 2026-10-06 至 2026-10-12 | 评测和回归测试 | 建立 Agent Evaluation Dataset；设计期望工具、禁止工具、最大步数、期望结果；评测结果优先接入 Langfuse datasets/evals；加入 Prompt Injection、权限、断网、并发测试 | Prompt 或模型升级前后可通过自动化测试和 Langfuse 对比质量 |
| 第 12 周 | 2026-10-13 至 2026-10-19 | 平台化第一版 | 数据导入审核后台、事件库管理、来源管理、关系管理、知识库管理、向量管理、模型配置、MCP 接入试点、用户反馈入口 | 具备从项目 Demo 向内部数据运营平台演进的基础；观测和评测详情不自研，交给 Langfuse |

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

## 管理后台与 Langfuse 边界

管理后台定位为“历史知识数据运营台”，只负责业务数据资产、内容质量、知识库和向量检索管理。Agent 运行观测、Trace、token/cost、工具调用链和评测分析不自研，后续统一交给 Langfuse。

### 我们需要开发的管理功能

| 模块 | 是否开发 | 主要功能 | 说明 |
|---|---|---|---|
| 管理总览 | 开发 | 事件总数、待审核批次、低置信事件、无来源事件、知识文档数、向量覆盖率 | 只展示业务数据资产状态，不做 Agent Trace 看板 |
| 数据导入 | 开发 | 上传或粘贴 JSON/CSV，创建导入批次，显示校验摘要 | 对接 import batch 和 staging 流程 |
| 导入审核 | 开发 | 查看 staging 行、错误原因、修正、拒绝、确认入库 | 数据建设的第一优先级后台 |
| 事件库管理 | 开发 | 搜索、筛选、查看、编辑、归档、标记争议 | 管理结构化历史事件 |
| 来源管理 | 开发 | 管理 citation、excerpt、URL、source type、reliability、核验状态 | 保证历史回答可追溯 |
| 关系管理 | 开发 | 维护 cause、effect、contemporary、influence、uncertain 等事件关系 | 用于关联分析和横向对照解释 |
| 知识库管理 | 开发 | 导入文档、查看 chunk、停用文档、版本记录、重切分、测试召回 | 管理 RAG 文档资产 |
| 向量管理 | 开发 | 查看 embedding 覆盖率、重算向量、索引状态、语义检索测试 | 不展示原始 1536 维向量，只管理覆盖、质量和任务 |
| 系统设置 | 部分开发 | admin token、embedding provider、向量维度、导入规则、状态枚举 | 不包含 Langfuse 的 Trace 详情页 |

### 交给 Langfuse、不需要我们开发的功能

| 功能 | 是否开发 | Langfuse 职责 | 本系统保留内容 |
|---|---|---|---|
| Agent 运行详情页 | 不开发 | 查看完整 trace、输入输出、span、observation | 只保存必要 run_id，并提供 Langfuse 链接 |
| 工具调用步骤查看 | 不开发 | 展示 tool call 链路、参数、结果、耗时、错误 | 前端聊天页可保留简要状态，不做后台分析页 |
| token、耗时、成本统计看板 | 不开发 | 统计模型调用成本、延迟、token 使用 | 后端只负责上报数据 |
| 运行错误分析 | 不开发 | 聚合失败 trace、错误原因、异常 span | 本后台最多展示失败数量和跳转链接 |
| Prompt 版本观测 | 不开发 | 关联 prompt 版本与 trace/eval 结果 | 本系统只保留实际使用的 prompt 文件或配置 |
| 评测中心 UI | 不开发 | 使用 Langfuse datasets/evals 管理评测结果 | 本仓库保留自动化评测脚本和本地测试数据 |
| Agent run 搜索与筛选 | 不开发 | 按用户、时间、模型、标签搜索 traces | 本后台不重复实现 run 列表 |

### 后台第一版开发顺序

| 优先级 | 模块 | 验收标准 |
|---:|---|---|
| 1 | 数据导入 + 导入审核 | 可以通过前端完成一批历史事件的创建批次、查看 staging、修正错误、确认入库或拒绝 |
| 2 | 事件库 + 来源管理 | 可以搜索事件、编辑核心字段、补充来源、核验来源、标记争议或归档 |
| 3 | 知识库 + 检索测试 | 可以导入文档、查看 chunk 数、执行语义检索并判断召回质量 |
| 4 | 向量管理 | 可以查看 embedding 覆盖率、发现缺失/过期向量、触发重算任务 |
| 5 | 关系管理 + 系统设置 | 可以维护事件关系和基础配置，不涉及 Agent Trace 分析 |

### 管理后台需要补强的后端能力

当前后端已经具备查询、导入审核、事件管理、知识库检索的 MVP，但新的管理后台需要列表、筛选、修正、批量、状态统计和向量任务能力。下面这些是我们要开发的业务后端能力，不和 Langfuse 重叠。

| 优先级 | 后端能力 | 建议 API | 用途 | 状态 |
|---:|---|---|---|---|
| 1 | 管理总览统计 | `GET /admin/overview` | 返回事件总数、待审核批次、低置信事件、无来源事件、知识文档数、向量覆盖率 | 已完成 |
| 2 | 导入批次列表 | `GET /imports/batches` | 支持按 status、created_by、时间分页查看导入批次 | 已完成 |
| 3 | staging 行修正 | `PATCH /imports/staging/{row_id}` | 修正错误行并重新校验，避免只能拒绝整个批次 | 已完成 |
| 4 | 批次重新校验 | `POST /imports/batches/{batch_id}/revalidate` | 对批次中的 staging 行重新跑校验，更新 valid/error 统计 | 已完成 |
| 5 | 后台事件列表 | `GET /admin/events` | 支持关键词、年份、地区、状态、置信度、是否有来源的分页筛选 | 已完成 |
| 6 | 事件审计日志 | `GET /admin/events/{event_id}/changes` | 查看事件新增、修改、归档、争议标记、来源核验记录 | 已完成 |
| 7 | 来源 CRUD | `POST /admin/events/{event_id}/sources`、`PATCH /admin/sources/{source_id}`、`DELETE /admin/sources/{source_id}` | 新增、编辑、删除或停用来源；现有后端只有来源核验 | 已完成 |
| 8 | 关系管理 CRUD | `GET /admin/relations`、`POST /admin/relations`、`PATCH /admin/relations/{relation_id}`、`DELETE /admin/relations/{relation_id}` | 管理事件之间的同期、因果、影响和不确定关系 | 已完成 |
| 9 | 知识文档管理 | `GET /knowledge/documents`、`GET /knowledge/documents/{document_id}/chunks`、`PATCH /knowledge/documents/{document_id}` | 列出文档、查看 chunk、停用或更新文档元数据 | 已完成 |
| 10 | 文档向量重算 | `POST /knowledge/documents/{document_id}/reembed` | 文档内容或 embedding 配置变化后重算 chunk embedding | 已完成 |
| 11 | 向量状态 | `GET /vectors/status` | 返回事件和知识库 embedding 覆盖率、维度、provider、索引状态 | 已完成 |
| 12 | 批量向量重建 | `POST /vectors/rebuild`、`POST /vectors/rebuild-jobs` | 触发历史事件或知识文档的批量 embedding 重算任务，支持任务创建、查看和处理 | 已完成 |
| 13 | 导入批次运营报表 | `GET /admin/import-batches/{batch_id}/report` | 查看单批次入库、质量处理进度、地区/年份/来源可靠度分布和优先处理项 | 已完成 |

### 后端继续加强工作表（暂不考虑权限）

当前后端已经能支撑管理后台第一版。下一轮加强不再以“补 CRUD”为主，而是提高数据运营效率和数据质量。

| 批次 | 优先级 | 工作项 | 建议 API / 交付物 | 目标 | 验收标准 | 状态 |
|---|---:|---|---|---|---|---|
| B1 | 1 | 数据质量检查 summary | `GET /admin/data-quality/summary` | 给总览页提供问题数量和严重程度概览 | 返回无来源、低置信、疑似重复、时间异常、关系缺证据等计数 | 已完成 |
| B1 | 2 | 数据质量问题列表 | `GET /admin/data-quality/issues` | 让运营者可以按问题类型进入修复 | 支持 issue_type、severity、limit、offset；每条问题可跳转事件或关系 | 已完成 |
| B1 | 3 | 数据字典接口 | `GET /admin/dictionaries` | 支撑前端筛选器和编辑表单 | 返回 regions、polities、categories、event_statuses、source_types、relation_types、time_precisions | 已完成 |
| B1 | 4 | 后台事件详情聚合 | `GET /admin/events/{event_id}` | 前端事件详情页一次拿齐管理所需数据 | 返回完整事件字段、分类、来源、关系、审计、导入批次和 embedding 状态 | 已完成 |
| B2 | 5 | 事件批量更新 | `POST /admin/events/bulk-update` | 提升事件维护效率 | 支持批量更新状态、置信度、分类、归档；记录审计日志 | 已完成 |
| B2 | 6 | staging 批量重校验 | `POST /imports/staging/bulk-revalidate` | 批量处理导入错误修复后的行 | 支持 row_ids 或 batch_id；返回成功/失败统计 | 已完成 |
| B2 | 7 | 来源批量核验 | `POST /admin/sources/bulk-verify` | 批量处理来源质量 | 支持 source_ids、reliability、is_primary；记录事件审计 | 已完成 |
| B3 | 8 | 导入合并策略 | `POST /imports/staging/{row_id}/merge` | 让重复预览后可以真正处理冲突 | 支持 keep_existing、replace_existing、merge_sources、merge_categories、merge_sources_and_categories | 已完成 |
| B3 | 9 | 导入文件解析轻量版 | `POST /imports/parse` | 提升导入体验 | 支持 JSON 文本/对象和 CSV 文本解析为标准 events payload | 已完成 |
| B3 | 10 | 数据质量处理台账 | `POST /admin/data-quality/issues/actions`、`data_quality_issue_actions` | 让已修复或决定忽略的问题不再反复干扰运营列表 | 支持 open、resolved、ignored、snoozed；summary/list 合并处理状态；初始化脚本和 schema 测试覆盖 | 已完成 |
| B3 | 11 | 导入批次运营报表 | `GET /admin/import-batches/{batch_id}/report` | 每批导入后可复盘处理进度和质量分布 | 返回 staging/入库总量、质量 open/handled、处理率、地区/年份/置信度/来源分布和优先处理项 | 已完成 |
| B4 | 12 | 知识库版本和重切分 | `knowledge_document_versions`、`GET /knowledge/documents/{document_id}/versions`、`POST /knowledge/documents/{document_id}/rechunk` | 支撑文档更新后的可追溯管理 | 文档更新保留版本，chunk 变化可查看 | 已完成 |
| B4 | 13 | 向量任务自动处理 | `POST /vectors/rebuild-jobs/process-pending`、`apps.worker.vector_worker`、向量页自动处理入口 | 数据量变大后避免手动 process | 创建任务后可自动处理，pending job 可批量领取处理，失败有错误信息和重试入口 | 已完成 |

### 管理后台前端开发工作表

前端管理系统只覆盖历史数据、知识库和向量运营；Agent 运行详情、工具调用链、成本看板和评测分析不做自研页面，后续通过 Langfuse 跳转查看。

| 批次 | 优先级 | 页面 / 能力 | 路由建议 | 对接 API | 验收标准 | 状态 |
|---|---:|---|---|---|---|---|
| F1 | 1 | 管理后台壳子和导航 | `/admin` | `GET /admin/overview`、`GET /vectors/status` | 有后台侧边导航、顶部状态、概览指标、数据质量入口；和聊天页路由互通 | 已完成 |
| F1 | 2 | 管理 API client 和类型拆分 | `apps/web/src/adminApi.ts` | 已有管理后端接口 | 管理接口集中封装，页面不直接拼 URL；失败、加载、空状态统一 | 已完成 |
| F2 | 3 | 数据导入工作台 | `/admin/imports/new` | `POST /imports/parse`、`POST /imports/batches` | 支持粘贴 JSON/CSV、解析预览、错误提示、创建导入批次 | 已完成 |
| F2 | 4 | 导入批次列表和审核详情 | `/admin/imports`、`/admin/imports/:batchId` | `GET /imports/batches`、`GET /imports/batches/{batch_id}/staging`、`GET /imports/batches/{batch_id}/preview`、`GET /admin/import-batches/{batch_id}/report` | 可查看批次、staging 行、校验错误、重复候选、差异和运营报表 | 已完成 |
| F2 | 5 | staging 修正、合并和确认入库 | `/admin/imports/:batchId` | `PATCH /imports/staging/{row_id}`、`POST /imports/staging/{row_id}/merge`、`POST /imports/batches/{batch_id}/confirm`、`POST /imports/batches/{batch_id}/reject` | 可修正错误行、批量重校验、处理重复、确认或拒绝批次 | 已完成 |
| F3 | 6 | 事件库列表和筛选 | `/admin/events` | `GET /admin/events`、`POST /admin/events/bulk-update` | 支持关键词、年份、地区、状态、最低置信度、有无来源筛选和批量归档 | 已完成 |
| F3 | 7 | 后台事件详情编辑 | `/admin/events/:eventId` | `GET /admin/events/{event_id}`、`PATCH /admin/events/{event_id}` | 事件核心字段已改为表单编辑，可保存并查看审计、来源、关系 | 已完成 |
| F3 | 8 | 来源和关系维护 | `/admin/events/:eventId`、`/admin/relations` | 来源新增/编辑/删除/核验、关系列表/新增/编辑/删除 | 可维护来源 reliability、citation、excerpt、URL，也可维护事件关系说明和置信度 | 已完成 |
| F4 | 9 | 数据质量修复台 | `/admin/quality` | `GET /admin/data-quality/summary`、`GET /admin/data-quality/issues`、`POST /admin/data-quality/issues/actions` | 可按问题类型进入事件或关系修复；可标记已处理、忽略和重新打开 | 已完成 |
| F4 | 10 | 知识库管理 | `/admin/knowledge`、`/admin/knowledge/:documentId` | `GET /knowledge/documents`、`GET /knowledge/documents/{document_id}/chunks`、`GET /knowledge/documents/{document_id}/versions`、`PATCH /knowledge/documents/{document_id}`、`POST /knowledge/documents/{document_id}/rechunk`、`POST /knowledge/documents/{document_id}/reembed` | 可查看文档、chunk、版本记录，更新元数据，停用/归档，触发 rechunk 和 reembed | 已完成 |
| F4 | 11 | 向量管理 | `/admin/vectors` | `GET /vectors/status`、`POST /vectors/rebuild-jobs`、`POST /vectors/rebuild-jobs/{job_id}/process`、`POST /vectors/rebuild-jobs/process-pending` | 可看 embedding 覆盖率、创建并自动处理重建任务、批量处理 pending jobs、查看任务状态 | 已完成 |
| F5 | 12 | 前端结构化整理和视觉 QA | 全局 | 无新增 | 已拆出 `AdminPages.tsx` 和 `adminApi.ts`，管理后台移动端表格/工具栏/导航已完成 390px 视口检查，`npm run build` 通过 | 已完成 |

### 不应自研的后端能力

| 能力 | 处理方式 |
|---|---|
| Agent run 搜索与分析接口 | 交给 Langfuse，后端只保留必要 run_id / trace_id 映射 |
| 工具调用链聚合接口 | 交给 Langfuse spans / observations |
| token/cost 汇总报表接口 | 交给 Langfuse 成本统计 |
| 运行错误聚合分析接口 | 交给 Langfuse trace 筛选和错误聚合 |
| 评测中心专用 UI 接口 | 交给 Langfuse datasets/evals，本仓库保留自动化评测脚本 |

## 当前实际进度

更新时间：2026-07-29

### 最近一次进度更新

| 时间 | 本次完成 | 验证结果 | 下一步 |
|---|---|---|---|
| 2026-07-28 | 完成 React 查询页和横向对照表 UI MVP：新增 `apps/web`，支持 Agent SSE 步骤流、年份/时间段地区对照、事件详情和来源展示 | 前端 `npm run build` 通过；后端单元测试 40/40 通过 | 继续做前端联调优化、数据管理后台，或把手写 checkpoint 迁移到 LangGraph |
| 2026-07-29 | 完成前端产品形态调整：从三栏工作台改为主流 AI 聊天页；新增 `react-router-dom` 页面跳转；事件卡片可跳转 `/events/:eventId` 详情页；补齐移动端适配；前端默认后端端口改为 `19000`；明确管理后台与 Langfuse 边界，并倒推后端增强清单 | 前端 `npm.cmd run build` 通过；前端 `http://127.0.0.1:5174` 返回 200；后端 `http://127.0.0.1:19000/health` 正常，数据源为 PostgreSQL | 优先补齐导入审核后台后端接口，再接数据导入审核后台；随后补事件/来源/知识库/向量管理接口 |
| 2026-07-29 | 完成管理后台后端继续加强 B1/B2/B3：数据质量 summary/问题列表、数据字典、后台事件详情聚合、事件/来源/staging 批量操作、导入 JSON/CSV 解析和重复 staging 合并策略 | 后端 `python -m unittest discover tests` 通过，54/54 | 开始开发管理后台前端，优先接入数据导入审核、事件详情维护、数据质量修复和批量操作 |
| 2026-07-29 | 完成管理后台前端可运营版：新增 `/admin` 管理台、导入解析/审核/合并、事件库高级筛选、事件表单编辑、来源新增/编辑/删除/核验、关系新增/编辑/删除、数据质量修复台、知识文档元数据维护和向量任务管理 | 前端 `npm.cmd run build` 通过；`/admin`、`/admin/events`、`/admin/relations` 返回 200 | 开始真实数据导入演练，使用 20-50 条历史事件验证导入、审核、修正、合并、入库、质量修复和事件维护闭环 |
| 2026-07-29 | 完成小批量历史事件种子导入：新增 `data/imports/curated_seed_600_900.json`，通过 ImportReviewService 创建并确认导入 12 条 633-883 年事件，覆盖中东、东亚、西欧、东地中海、南亚、东欧 | `python data/validate_events.py data/imports/curated_seed_600_900.json` 通过；导入批次 `3ab3c564-d324-4b35-ac30-5b5fe82d0a11` 已 imported；相关导入/Repository 测试 11/11 通过 | 在管理后台核验这批 `reviewing` 数据，处理同名“大化改新”候选，再决定是否扩展到 20-50 条真实导入演练 |
| 2026-07-29 | 完成种子数据核验支撑能力：后台事件列表支持 `import_batch_id`，数据质量新增 `duplicate_title`，导入批次详情新增核验摘要面板，后端新增 `GET /admin/import-batches/{batch_id}/review` | 后端 `python -m unittest discover tests` 通过，56/56；前端 `npm.cmd run build` 通过；真实种子批次返回 12 条事件、1 条低置信、12 条弱来源、1 个重复候选、0 个结构缺口 | 继续做实际人工核验和管理后台体验修复，再扩展 20-50 条真实数据导入演练 |
| 2026-07-29 | 完成数据库初始化脚本同步：新增完整初始化入口 `infrastructure/database/init.sql`，纳入事件审计、知识库、事件向量列、向量任务表和基础字典；补管理后台查询索引 | 后端 `python -m unittest discover tests` 通过，58/58；当前本地库已同步新增 5 个索引 | 后续表结构变化要同步更新 `init.sql` 和 schema 文件测试 |

### 当前状态摘要

| 项目 | 当前状态 |
|---|---|
| 当前阶段 | 后端基础 MVP、任务型 Agent 运行状态 MVP、Redis 队列/Worker MVP、checkpoint 恢复 MVP、数据导入审核流 MVP、RAG 检索 MVP、事件管理/人工确认 MVP、管理后台支撑 API B1/B2/B3、React 聊天主界面、React Router 跳转、事件详情页、移动端适配和管理后台可运营版已完成；Agent 观测与评测分析交给 Langfuse |
| 已完成主链路 | FastAPI API、React Web、React Router、PostgreSQL、pgvector、历史查询工具、Agent Loop、Function Calling、执行记录、自动评测、SSE 步骤流、运行取消、异步提交/Worker 执行、checkpoint 恢复、数据导入审核、知识库检索、受控事件管理、管理后台数据运营 |
| 当前可运行能力 | 用户可在聊天页运行 Agent、查看 SSE 工具调用过程、从回答里的事件卡片跳转详情页；也可用管理后台完成导入解析、批次审核、staging 修正/合并、确认入库、事件编辑、来源维护、关系维护、数据质量查看、知识库文档维护和向量任务处理；当前已新增 12 条小批量种子事件入库 |
| 当前验证结果 | 前端 `npm.cmd run build` 通过；前端 `http://127.0.0.1:5174` 返回 200；后端 `http://127.0.0.1:19000/health` 正常；后端单元测试最近一次 58/58 通过，MVP 评测最近一次 4/4 通过 |
| 下一步重点 | 提交 W17 改动、补确认后恢复执行入口、Langfuse datasets/evals 对接 |
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
| 自动评测 | 已完成 MVP，后续评测 UI 交给 Langfuse | `evaluation.runner` 可写入 `evaluation_runs`，当前 MVP 评测 4/4 通过；后续不自研评测中心后台，优先接 Langfuse datasets/evals | 第十三阶段：评测体系 |
| 规则 Agent 路由 | 已完成 | 支持年份题、时间段题、地区对照题、事件关系题的多步工具调用 | 第三阶段：实现最小 Agent Loop |
| ModelAdapter | 已完成 MVP | 已有可替换模型适配器接口、`RuleBasedModelAdapter` 和模型工厂 | 第二阶段：学习大模型基础；系统架构：Model Adapter |
| OpenAI Function Calling | 已完成 MVP | 已把 ToolRegistry 转换为 OpenAI tools，可通过环境变量切换真实模型 | 第二阶段：Structured Output；最终技术选型：JSON Schema Function Calling |
| ToolRegistry / ToolExecutor | 已完成 MVP | 已实现 `ToolDefinition`、`ToolRegistry`、`ToolExecutor`，统一执行历史查询工具 | 第四阶段：设计工具系统 |
| Function Calling 稳定性 | 已完成 MVP | ToolExecutor 已支持 JSON Schema 参数校验、默认值填充、单工具超时、幂等工具重试、失败观察结果 | 第三阶段：参数校验、超时、重试、失败处理 |
| 模型观测和成本统计 | 已完成 MVP，后续不自研后台 | Agent 步骤已记录模型输入摘要、输出摘要、token 输入/输出、模型耗时和估算成本；后续 Trace、成本看板和运行分析交给 Langfuse | 第三阶段：Token/成本预算；第十四阶段：可观测性 |
| SSE 步骤流 | 已完成 MVP | 新增 `/agent/query/stream`，实时输出 run_started、step_started、tool_called、tool_result、final_answer 等事件 | 第十六阶段：前后端通信；系统架构：API Gateway SSE |
| Agent 运行状态增强 | 已完成 MVP | 已新增取消入口 `/agent/runs/{run_id}/cancel`，Loop 会检查 cancelled 状态，失败/取消不会被误标 completed | 第十一阶段：任务持久化与故障恢复 |
| Redis 队列 / Worker | 已完成 MVP | 已新增 `/agent/query/async`、`/agent/queue/health`、`/agent/queue/process-one`、`/agent/queue/recover-stale` 和 `apps.worker.agent_worker`，支持 Redis list 入队、processing 队列、worker 消费、PostgreSQL 原子 claim、成功 ack、失败重试、死信队列、visibility timeout 回收和结果回放 | 系统架构：Task Worker；第十一阶段：任务持久化与故障恢复 |
| checkpoint 恢复执行 | 已完成 MVP | 已新增 `AgentLoop.resume_existing`，可从 `agent_steps` 重建历史工具调用上下文，worker 恢复 pending run 时从下一步继续 | 第十一阶段：Checkpoint；LangGraph 迁移前置能力 |
| 数据导入审核流 | 已完成 MVP | 已支持 import batch、staging、逐行校验、确认入库、拒绝批次，错误行不会进入正式表 | 第十阶段：人工确认机制；第十二阶段：安全体系 |
| RAG / pgvector 检索 | 已完成 MVP | 已新增 `knowledge_documents`、`knowledge_chunks`、本地 embedding、文档入库和 `/knowledge/search` 检索 | 第八阶段：RAG 知识库 |
| 事件管理和人工确认 | 已完成 MVP | 已新增 `/admin/events`、修改、归档、争议标记、来源核验接口；写操作必须带 `admin_token` 和 `confirmed=true`，并写入 `event_change_logs` 审计日志 | 第十阶段：人工确认机制；第十二阶段：安全体系；平台化第一版 |
| 手写 Agent Loop | 已完成 MVP | API 和评测已切换到新 Loop，支持最大步数、步骤记录、工具结果裁剪 | 第三阶段：实现最小 Agent Loop |
| 后端缺口审查 | 已完成 | 已形成 `docs/backend_gap_review.md`，记录与 PDF 技术栈的差距 | 第十九：推荐开发顺序；第二十二：最终技术选型建议 |
| 前端 | 已完成可运营版 | 已新增 `apps/web` React + TypeScript + Vite 聊天主界面和 `/admin` 管理后台；支持 Agent SSE、React Router 页面跳转、事件详情页、事件卡片链接、快捷横向对照、移动端适配、导入审核、事件/来源/关系/知识库/向量管理 | 第一阶段 MVP：React 聊天页面、流式回复；第十六阶段：前后端通信；业务可视化前端；平台化第一版 |

### 紧要但未完成的能力

| 优先级 | 能力 | 当前状态 | 为什么紧要 | 对应 PDF 功能/章节 |
|---:|---|---|---|---|
| 1 | 真实数据导入演练 | 已完成 12 条小批量种子导入和 22 条扩展导入演练 | 管理后台已可用，扩展批次暴露出低置信、弱来源和重复候选，下一步进入体验修复 | 第十阶段：人工确认机制；平台化第一版 |
| 2 | Agent 返回结构标准化 | 已完成 | 后端同步接口和 SSE `final_answer` 已稳定返回 `answer`、`events`、`references`、`links`；前端不再递归解析 observation，改为按标准结构渲染事件卡片和引用来源 | 第二阶段：Structured Output；第十六阶段：前后端通信 |
| 3 | RAG 引用注入回答 | 已完成第一版 | Agent 已注册 `search_knowledge` 工具，回答前会检索知识库 chunk，并把知识文档与事件来源注入 `references` 和回答正文 | 第八阶段：RAG 知识库 |
| 4 | 管理后台真实运营体验 QA | 已完成第一轮 | 已在真实导入演练后修复质量页、重复候选、弱来源处理、移动端布局，并补质量问题处理台账；后续随新增数据继续迭代 | 平台化第一版 |
| 5 | Langfuse 可观测性集成 | 已完成 SDK 第一版 | 已新增 telemetry adapter、Langfuse 环境变量和 trace 链接入口；后端可选加载 Langfuse SDK 上报运行、工具调用、token、成本和错误状态 | 第十四阶段：可观测性 |
| 6 | 完整 RBAC / 多租户权限 | 暂缓 | 当前暂不考虑权限；后续上线需要用户身份、角色、租户隔离和权限策略落库 | 第十二阶段：安全体系 |

## 前端和主链路下一步计划

| 优先级 | 接下来准备做什么 | 目标 | 对应 PDF 功能/章节 |
|---:|---|---|---|
| 1 | 管理后台体验修复 | 已完成质量页、重复候选提示、弱来源快捷处理、移动端视觉 QA 和质量问题处理闭环 | 平台化第一版 |
| 2 | 小批量导入数据核验 | 在 `/admin/events` 和 `/admin/quality` 核验已导入的 `reviewing` 种子数据，必要时合并同名或近似重复记录 | 第十阶段：人工确认机制；平台化第一版 |
| 3 | 真实数据导入演练扩展 | 已完成 22 条扩展批次；后续只在需要验证字段或专题覆盖时继续扩展 | 第十阶段：人工确认机制；平台化第一版 |
| 4 | Agent 返回结构标准化 | 已完成；后端在 `final_answer` 和同步接口中稳定返回 `answer`、`references`、`links`、`events`，前端不再依赖递归解析 observation | 第二阶段：Structured Output；第三阶段：最小 Agent Loop；第十六阶段：前后端通信 |
| 5 | RAG 引用注入回答 | 已完成第一版；知识库检索和事件来源已稳定注入 Agent 答案，回答可显示引用来源和文档 chunk | 第八阶段：RAG 知识库 |
| 6 | Langfuse SDK 接入 | 已完成第一版；后端可选加载 Langfuse SDK 上报 trace、tool call、token、成本和错误状态，前端可展示外部 trace 跳转；后台不自研 Agent run 搜索与分析页 | 第十四阶段：可观测性；第十三阶段：评测体系 |

## 当前工作计划表

| 批次 | 优先级 | 工作项 | 范围 | 验收标准 | 状态 |
|---|---:|---|---|---|---|
| W1 | 1 | 小批量种子数据核验支撑 | 在 `/admin/imports/:batchId`、`/admin/events`、`/admin/quality` 支撑 12 条 `reviewing` 事件核验；已补 `import_batch_id` 筛选、`duplicate_title` 质量问题和批次核验摘要 | 可从导入批次直接查看本批事件、低置信、弱来源、重复候选和结构缺口；`duplicate_title` 可发现“大化改新”等同标题候选 | 已完成 |
| W2 | 2 | 数据库初始化脚本同步 | 更新完整建库入口、管理后台索引和 schema 文件测试 | `init.sql` 覆盖当前后端依赖；后端全量测试通过；当前本地库索引同步 | 已完成 |
| W3 | 3 | 管理后台体验修复 | 根据实际人工核验修复表单字段、错误提示、重复候选提示、空状态、移动端布局 | 已完成质量页、重复候选提示、弱来源快捷处理和移动端视觉 QA；前端 `npm.cmd run build` 通过；后端全量测试通过 | 已完成 |
| W4 | 4 | 数据导入演练扩展 | 已新增 22 条扩展种子数据，并通过导入审核流确认入库 | 新增批次可导入、可审核、可确认，重复和错误行能被后台处理；扩展数据验证和专项测试通过 | 已完成 |
| W5 | 5 | Agent 返回结构标准化 | 后端输出 `answer`、`events`、`references`、`links`；前端按结构渲染 | 聊天页不再递归解析 observation；事件卡片和引用来源按标准字段渲染；后端全量测试和前端构建通过 | 已完成 |
| W6 | 6 | RAG 引用注入回答 | 把事件来源和知识文档 chunk 注入回答上下文和前端展示 | Agent 会调用 `search_knowledge`，回答正文追加参考资料；结构化 `references` 含事件来源和知识 chunk；后端全量测试通过 | 已完成 |
| W7 | 7 | Langfuse 集成预留 | 后端接 trace/tool/token/error 上报；前端只保留跳转入口 | 可从 run_id 对应到 Langfuse trace；不开发自研 Trace 后台；后端全量测试和前端构建通过 | 已完成 |
| W8 | 8 | 数据质量处理闭环 | 新增数据质量问题处理台账、API 和前端操作 | 可把问题标记为已处理、忽略或重新打开；初始化表同步；后端全量测试和前端构建通过 | 已完成 |
| W9 | 9 | 导入批次运营报表 | 新增批次 report API 和批次详情页复盘面板 | 展示入库事件、待处理质量问题、处理率、质量分解、地区/年份/来源可靠度分布和优先处理项；后端全量测试和前端构建通过 | 已完成 |
| W10 | 10 | 知识库版本和重切分 | 新增文档版本表、版本列表 API、rechunk API 和知识详情页版本操作 | 文档 ingest/rechunk 均记录版本快照；可生成新 chunk 版本；后端全量测试和前端构建通过 | 已完成 |
| W11 | 11 | 向量任务自动处理 | 新增 pending vector job 自动领取、批量处理 API、`apps.worker.vector_worker` 和前端自动处理入口 | 创建向量任务后可自动处理；可批量消费 pending jobs；后端全量测试和前端构建通过 | 已完成 |
| W12 | 12 | Langfuse SDK 正式接入 | `AgentTelemetry` 可选加载 Langfuse SDK，创建 deterministic trace、agent observation、model generation、tool observation，并上报 token、成本、完成/失败/取消状态 | 未配置或 SDK 不可用时不影响 Agent 主链路；后端全量测试通过；后台不自研 Trace 分析页 | 已完成第一版 |
| W13 | 13 | LangGraph 迁移前置 | 新增 `AGENT_WORKFLOW_ENGINE`、`agent.runtime.workflow` 工厂和 LangGraph 可选单节点适配器；API/worker 改为统一工作流接口 | 默认 loop 行为不变；`langgraph` 引擎具备切换边界；后端全量测试通过 | 已完成第一版 |
| W14 | 14 | LangGraph 多节点适配第一版 | `LangGraphAgentWorkflow` 拆成 `prepare_state -> execute_agent_loop -> finalize_response` 三节点 pipeline，新增 fake LangGraph 组装测试 | 默认 loop 行为不变；LangGraph 适配器具备 state pipeline；后端全量测试通过 | 已完成第一版 |
| W15 | 15 | LangGraph 细粒度节点第一版 | `LangGraphAgentWorkflow` 推理循环拆成 `prepare_state -> decide -> execute_tool -> decide/finalize_response/max_steps_exceeded`，复用 recorder、telemetry、checkpoint 和工具执行 helper | fake LangGraph 可实际跑通决策/工具 pipeline；默认 loop 行为不变；后端全量测试通过 | 已完成第一版 |
| W16 | 16 | LangGraph SSE streaming | `LangGraphAgentWorkflow.stream()` 复用细粒度节点并输出 `run_started/step_started/tool_called/tool_result/final_answer/run_completed` 等兼容前端的 SSE 事件 | `AGENT_WORKFLOW_ENGINE=langgraph` 时 streaming 不回退旧 Loop；后端全量测试通过 | 已完成第一版 |
| W17 | 17 | LangGraph 人工确认中断节点 | 新增 `confirmation_required` 节点；高风险或需确认工具未带 `confirmed: true` 时暂停执行，run 标记 `waiting_for_user`，streaming 输出 `confirmation_required` | 高风险工具不会被误执行；同步和 streaming 均可返回确认提示；后端全量测试通过 | 已完成第一版 |

## 后端重构工作表

| 批次 | 优先级 | 重构项 | 范围 | 验收标准 | 状态 |
|---|---:|---|---|---|---|
| R1 | 1 | 统一向量任务表 schema 兜底 | `knowledge/service.py` 的运行时建表逻辑与 `schema_vector_jobs.sql` 保持一致 | schema 文件测试覆盖约束；后端全量测试通过 | 已完成 |
| R2 | 2 | 拆分 FastAPI 路由 | 将 `apps/api/main.py` 拆成 agent、events、imports、admin、knowledge、vectors routers | 已拆出 agent、events、imports、admin、knowledge/vector routers；`main.py` 降到 124 行；路由路径不变；后端全量测试通过 | 已完成 |
| R3 | 3 | 拆分管理服务 | 将 `EventManagementService` 拆为事件、来源、关系、数据质量、总览、批次核验服务 | 已拆出 `EventAdminService`、`DataQualityService`、`SourceManagementService`、`RelationManagementService`、`ManagementOverviewService`、`ImportBatchReviewService` 和公共审计基类；原 API 通过门面保持兼容；管理专项测试和后端全量测试通过 | 已完成 |
| R4 | 4 | 抽公共历史实体 upsert | 合并 import 和 management 中 region/country/polity/category ensure 逻辑 | 已新增 `HistoricalEntityResolver`；导入确认和后台事件编辑复用同一套地区/国家/政权/分类 upsert；导入+管理专项测试和后端全量测试通过 | 已完成 |
| R5 | 5 | 写接口 Pydantic 化 | 为事件、来源、关系、导入、向量任务写接口补 request/response models | 已为 admin、imports、knowledge/vector 写接口补 Pydantic request/response models；OpenAPI schema 测试覆盖关键写接口；前端调用和现有测试兼容 | 已完成 |
| R6 | 6 | 清理轻微代码味道 | 重复 import、分页/JSON safe/helper 重复逻辑 | 已清理重复 payload 转换、分页 clamp 和管理审计/JSON safe helper；后端全量测试通过 | 已完成 |

## 后端下一步建议

对照新的管理后台计划，后端和前端管理系统第一轮已基本补齐。下一步后端不再优先补 CRUD，而是围绕真实数据演练和 Agent 输出协议增强：

| 优先级 | 接下来准备做什么 | 目标 | 对应 PDF 功能/章节 |
|---:|---|---|---|
| 1 | 真实数据导入演练脚本和样例数据 | 准备可重复导入的 20-50 条事件样例，用于验证管理后台和数据校验 | 第十阶段：人工确认机制；平台化第一版 |
| 2 | Agent 返回结构标准化 | 稳定返回 `answer`、`references`、`links`、`events`，支撑前端引用和跳转 | 第二阶段：Structured Output；第十六阶段：前后端通信 |
| 3 | RAG 引用注入 | 已完成第一版；事件来源和知识文档 chunk 已作为引用注入 Agent 回答 | 第八阶段：RAG 知识库 |
| 4 | Langfuse 集成 | 已完成 SDK 第一版；后续可继续把本地评测结果接入 Langfuse datasets/evals；不开发自研运行分析后台 | 第十四阶段：可观测性 |
| 5 | LangGraph 工作流 | 已完成迁移前置、细粒度 decision/tool/finalize 节点、LangGraph SSE streaming 和人工确认中断节点；后续补确认后恢复执行入口 | 第六阶段：模型决策和固定工作流结合；第十一阶段：Checkpoint |
| 6 | MCP 接入 | 等本地工具边界稳定后，把核心工具服务标准化给外部智能体复用 | 第九阶段：MCP 能力标准化 |

详细缺口见 [backend_gap_review.md](docs/backend_gap_review.md)。
