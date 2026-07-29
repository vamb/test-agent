# 后端技术栈缺口审查

审查日期：2026-07-28  
依据：`AI智能体开发大纲工作.pdf`、当前代码和数据库状态

当前状态：后端基础 MVP、Function Calling 稳定性、模型观测/成本记录、SSE 步骤流、运行取消、Redis 队列/Worker、processing ack、失败重试、死信队列、visibility timeout 回收、checkpoint 恢复执行、数据导入审核流、RAG 检索、事件管理、权限/人工确认、React 查询页和横向对照表 UI MVP 已完成；管理后台边界已明确为数据资产、知识库和向量管理；Agent Trace、工具调用链、token/cost 和评测分析后续交给 Langfuse，不自研重复后台。

## 当前后端已完成

| 模块 | 状态 | 说明 |
|---|---|---|
| FastAPI | 已完成 MVP | 已有 API 入口、健康检查、查询接口、Agent 查询接口 |
| Pydantic | 已完成 MVP | 历史事件、来源等模型已定义 |
| PostgreSQL | 已完成 | 已创建 `historical_agent` 专用库和 19 张表 |
| pgvector | 已安装 | `vector 0.8.2` 已启用，`historical_events.embedding` 已存在 |
| 历史查询工具 | 已完成 MVP | 年份、时间段、地区对照、详情、同期、关系查询 |
| Tool Registry | 已完成 MVP | 已有 `ToolDefinition`、`ToolRegistry` 和历史查询工具注册表 |
| ToolExecutor | 已完成 MVP | 已有统一工具执行器，记录入参、结果和耗时 |
| Agent Loop | 已完成 MVP | 已有可替换 `ModelAdapter` 的手写 Loop，支持最大步数和工具结果裁剪 |
| Model Adapter | 已完成 MVP | 已有 `RuleBasedModelAdapter` 和 OpenAI Function Calling 适配器 |
| Agent 执行记录 | 已完成 MVP | `agent_runs`、`agent_steps` 已写入 |
| Worker / 队列 | 已完成 MVP | 支持 `/agent/query/async` 创建 pending run，Redis list 入队，processing 队列、成功 ack、失败重试、死信队列和 visibility timeout 回收 |
| checkpoint 恢复 | 已完成 MVP | 支持从 `agent_steps` 重建已完成工具调用上下文，恢复 run 时从下一步继续 |
| 自动评测 | 已完成 MVP | `evaluation.runner` 可跑评测并写入 `evaluation_runs`，当前 4/4 通过 |
| 数据导入 | 已完成审核流 MVP | 支持批次、staging、校验、确认入库、拒绝批次 |
| 事件管理 | 已完成 MVP | 支持事件新增、修改、归档、争议标记、来源核验和 `event_change_logs` 审计 |
| 权限/人工确认 | 已完成 MVP | 写操作必须带 `admin_token` 和 `confirmed=true`，后端硬校验；完整 RBAC/多租户未完成 |
| 事件关系 | 已完成样例关系 | 已有 `influence`、`conflict_link`、`contemporary` 示例 |

## 对照 PDF 技术栈的后端缺口

| 技术/能力 | PDF 建议 | 当前状态 | 缺口 | 优先级 |
|---|---|---|---|---|
| Model Adapter | 统一接入 OpenAI/Anthropic/Gemini/私有模型 | 已完成 OpenAI MVP | 还缺 Anthropic/Gemini/私有模型适配器 | 中 |
| Function Calling | 用 JSON Schema 工具调用 | 已完成 MVP | 参数校验、超时、重试、token 和成本统计已完成 MVP；还缺模型失败 fallback | 中 |
| Agent Loop | 先手写，后生产用 LangGraph | 已完成 MVP | 手写 Loop 已支持重试、恢复和 checkpoint MVP；还缺 LangGraph 正式化 | 中 |
| Tool Registry | 工具定义、风险等级、确认策略 | 已完成 MVP | 还缺后台动态启停工具、确认策略落库 | 中 |
| SSE 流式输出 | 前后端传输运行事件 | 已完成 MVP | 已有 `/agent/query/stream`，前端已可消费并展示步骤；还缺断线恢复 | 中 |
| 任务取消/重试/恢复 | 任务型 Agent 必备 | 已完成 MVP | 已支持取消、Redis 队列、异步 Worker、失败重试、死信队列、visibility timeout 回收和 checkpoint 恢复执行 | 中 |
| Redis | 缓存、队列、锁 | 已完成队列 MVP | 已支持 Redis list、processing 队列、ack、失败重试、死信队列和 visibility timeout 回收 | 低 |
| LangGraph | Checkpoint、Interrupt、恢复 | 未实现 | 目前无 LangGraph 工作流 | 中 |
| RAG | 文档上传、切分、混合检索、引用 | 已完成检索 MVP | 已有本地 embedding 和 pgvector 检索；还缺混合检索、真实 embedding、引用注入 Agent 回答 | 中 |
| Langfuse 集成 | Trace、模型调用、工具调用、评测分析 | 未实现 | 当前已有数据库级模型/工具记录，但还没有上报 Langfuse；后台不自研 Trace 分析页 | 中 |
| 成本统计 | token、耗时、模型成本 | 已完成 MVP | 已采集到 `agent_steps`；后续成本看板交给 Langfuse，本系统只保留必要配置和上报能力 | 中 |
| 权限/RBAC | 后端真实权限判断 | 已完成 MVP | 当前是 admin token + confirmed，缺用户、角色、租户隔离和权限策略落库 | 高，上线前必须补 |
| 人工确认 | 高风险操作暂停确认 | 已完成 MVP | 当前写接口需要显式确认字段，缺可恢复的 interrupt / approval 工作流 | 中 |
| Prompt Injection 防护 | 工具边界、来源隔离、安全策略 | 未实现 | 当前还没有外部文档/RAG，后续必须补 |
| 数据导入审核 | staging -> 校验 -> 人工确认 -> 入库 | 已完成 MVP | 还缺导入差异预览、批量修正和异步执行 | 中 |
| 管理接口 | 导入审核、事件、来源、关系、知识库、向量管理 | 已完成事件管理 MVP | 还缺前端后台、批量操作、知识库管理、向量覆盖率/重算能力和更细粒度权限 | 中 |
| MCP | 标准工具协议 | 未实现 | 当前只是本地工具函数 | 低，等单 Agent 稳定后做 |
| Docker Compose | 部署 FastAPI/PostgreSQL/Redis | 未实现 | 当前依赖本机服务 | 中 |
| Pytest | 自动化测试 | 部分完成 | 当前用 `unittest`，未引入 pytest | 低 |

## 管理后台后端增强清单

新的前端管理后台需要后端补齐以下业务接口。这些能力服务数据资产、知识库和向量管理，不包含 Langfuse 已覆盖的 Agent Trace、工具调用链、成本看板和评测分析。

| 优先级 | 能力 | 建议 API | 状态 | 说明 |
|---:|---|---|---|---|
| 1 | 管理总览统计 | `GET /admin/overview` | 已完成 | 汇总事件数、待审核批次、低置信事件、无来源事件、知识文档数、向量覆盖率 |
| 2 | 导入批次列表 | `GET /imports/batches` | 已完成 | 支持 status、created_by 和分页 |
| 3 | staging 行修正 | `PATCH /imports/staging/{row_id}` | 已完成 | 更新 raw payload，重新校验该行，刷新 row status |
| 4 | 批次重新校验 | `POST /imports/batches/{batch_id}/revalidate` | 已完成 | 重新校验批次并更新 valid_rows、error_rows、status |
| 5 | 后台事件列表 | `GET /admin/events` | 已完成 | 支持关键词、年份、地区、状态、置信度、是否有来源的分页筛选 |
| 6 | 事件审计日志 | `GET /admin/events/{event_id}/changes` | 已完成 | 查看 create/update/archive/dispute/source verify 等变更 |
| 7 | 来源 CRUD | `POST /admin/events/{event_id}/sources`、`PATCH /admin/sources/{source_id}`、`DELETE /admin/sources/{source_id}` | 已完成 | 支持新增、编辑、删除来源 |
| 8 | 关系 CRUD | `GET /admin/relations`、`POST /admin/relations`、`PATCH /admin/relations/{relation_id}`、`DELETE /admin/relations/{relation_id}` | 已完成 | 维护 contemporary、cause、effect、influence、uncertain 等关系 |
| 9 | 知识文档管理 | `GET /knowledge/documents`、`GET /knowledge/documents/{document_id}/chunks`、`PATCH /knowledge/documents/{document_id}` | 已完成 | 支持文档列表、chunk 查看、停用和元数据更新 |
| 10 | 文档向量重算 | `POST /knowledge/documents/{document_id}/reembed` | 已完成 | 文档内容或 embedding 配置变化后重算 chunk embedding |
| 11 | 向量状态 | `GET /vectors/status` | 已完成 | 展示 embedding 覆盖率、维度、provider、索引状态 |
| 12 | 批量向量重建 | `POST /vectors/rebuild`、`POST /vectors/rebuild-jobs` | 已完成 | 触发历史事件或知识文档的批量 embedding 重算，支持 job 创建、查看和处理 |

## 下一轮后端加强工作表（暂不考虑权限）

| 批次 | 优先级 | 能力 | 建议 API / 交付物 | 说明 | 状态 |
|---|---:|---|---|---|---|
| B1 | 1 | 数据质量检查 summary | `GET /admin/data-quality/summary` | 返回无来源、低置信、疑似重复、时间异常、关系缺证据等计数 | 已完成 |
| B1 | 2 | 数据质量问题列表 | `GET /admin/data-quality/issues` | 支持 issue_type、severity、分页和目标跳转 | 已完成 |
| B1 | 3 | 数据字典接口 | `GET /admin/dictionaries` | 返回 regions、polities、categories 和各类枚举 | 已完成 |
| B1 | 4 | 后台事件详情聚合 | `GET /admin/events/{event_id}` | 返回完整事件、来源、关系、审计、导入批次和 embedding 状态 | 已完成 |
| B2 | 5 | 事件批量更新 | `POST /admin/events/bulk-update` | 批量更新状态、置信度、分类或归档 | 已完成 |
| B2 | 6 | staging 批量重校验 | `POST /imports/staging/bulk-revalidate` | 支持 row_ids 或 batch_id | 已完成 |
| B2 | 7 | 来源批量核验 | `POST /admin/sources/bulk-verify` | 批量更新 reliability / is_primary | 已完成 |
| B3 | 8 | 导入合并策略 | `POST /imports/staging/{row_id}/merge` | 支持 keep_existing、replace_existing、merge_sources、merge_categories、merge_sources_and_categories | 已完成 |
| B3 | 9 | 导入解析轻量版 | `POST /imports/parse` | 支持 JSON/CSV 解析成标准 events payload | 已完成 |
| B4 | 10 | 知识库版本和重切分 | 文档版本字段 / re-chunk 接口 | 文档更新保留版本，chunk 变化可查看 | 暂缓 |
| B4 | 11 | 向量任务自动处理 | Worker 或队列消费 vector jobs | 向量 job 自动完成，失败可查看和重试 | 暂缓 |

## 建议后端下一步顺序

### 第一优先级：前端联调优化和数据管理后台

目标：在 Web 工作台 MVP 基础上补齐真实使用流程和数据维护入口。该后台只负责业务数据、来源、关系、知识库和向量管理；Agent 运行观测和评测分析交给 Langfuse。

要做：

1. 先补数据质量检查 summary 和问题列表。
2. 再补数据字典接口和后台事件详情聚合接口。
3. 接着补事件、staging、来源的批量操作。
4. 然后补导入合并策略和 JSON/CSV 解析轻量版。
5. 前端再接数据导入审核、事件库、来源、关系、知识库和向量管理页面。
6. Langfuse 只保留 trace 跳转入口，不开发自研运行分析后台。

验收：

- 长任务不阻塞 API。
- 用户可以完成从查询、查看来源到管理事件的闭环。
- 数据维护不再依赖 curl 或脚本。

### 第二优先级：数据导入审核增强

目标：在已完成 MVP 基础上增强权限、差异预览和批量修正。

要做：

1. 导入前差异预览。
2. 批量修正 staging 行。
3. 导入任务异步化。
4. 导入结果回放和失败重试。

验收：

- 导入不会直接污染正式表。
- 错误行可回看、可修正。

### 第三优先级：完整 RBAC / 多租户

目标：把当前 admin token MVP 升级为真实用户权限系统。

要做：

1. 用户身份表和角色表。
2. 工具风险等级和权限策略落库。
3. 租户/项目级数据隔离。
4. 管理接口按角色授权。

验收：

- 权限不依赖模型判断。
- 写操作、导入和知识库检索都有后端隔离。

## 当前不建议立刻做

| 能力 | 原因 |
|---|---|
| 多智能体 | 当前单 Agent 边界还没完全成熟 |
| MCP | 工具协议化可以晚一点，先把本地工具做好 |
| Playwright 浏览器 Agent | 这个产品第一阶段核心不是浏览器自动化 |
| 复杂权限多租户 | 数据管理接口前再上更合适 |
| Kubernetes | Docker Compose 都还没做，不需要提前复杂化 |
