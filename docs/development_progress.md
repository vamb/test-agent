# 历史时间对照 Agent 开发进度计划

计划起始日期：2026-07-28  
参考依据：AI智能体开发大纲工作.pdf、AI智能体开发计划表.md、历史时间对照 Agent 业务需求

## 最近一次进度更新

| 时间 | 本次完成 | 验证结果 | 下一步 |
|---|---|---|---|
| 2026-07-28 | 完成 React 查询页和横向对照表 UI MVP：新增 `apps/web`，支持 Agent SSE 步骤流、年份/时间段地区对照、事件详情和来源展示 | 前端 `npm run build` 通过；后端单元测试 40/40 通过 | 继续做前端联调优化、数据管理后台，或把手写 checkpoint 迁移到 LangGraph |
| 2026-07-29 | 完成前端主流程改造：聊天页成为主入口；引入 `react-router-dom`；事件卡片跳转 `/events/:eventId`；详情页独立展示事件档案；补齐移动端适配；前端默认 API 切换到 `19000`；明确管理后台与 Langfuse 边界，并倒推后端增强清单 | 前端 `npm.cmd run build` 通过；前端 `http://127.0.0.1:5174` 返回 200；后端 `http://127.0.0.1:19000/health` 正常 | 优先补齐导入审核后台后端接口，再接数据导入审核后台；随后补事件/来源/知识库/向量管理接口；Agent 观测和评测详情后续接 Langfuse，不自研后台 |
| 2026-07-29 | 完成种子数据核验支撑能力：后台事件列表支持 `import_batch_id`，数据质量新增 `duplicate_title`，导入批次详情新增核验摘要面板，后端新增 `GET /admin/import-batches/{batch_id}/review` | 后端 `python -m unittest discover tests` 通过，56/56；前端 `npm.cmd run build` 通过；真实种子批次返回 12 条事件、1 条低置信、12 条弱来源、1 个重复候选、0 个结构缺口 | 继续做实际人工核验和管理后台体验修复，再扩展 20-50 条真实数据导入演练 |
| 2026-07-29 | 完成数据库初始化脚本同步：新增 `infrastructure/database/init.sql`，纳入事件审计、知识库、事件向量列、向量任务表和基础字典；补管理后台查询索引和 schema 文件测试 | 后端 `python -m unittest discover tests` 通过，58/58；当前本地库已同步新增 5 个索引 | 后续每次表结构变化同步更新 `init.sql` 和 schema 文件测试 |
| 2026-07-30 | 完成后端 R3 管理服务拆分：新增 `EventAdminService`、`DataQualityService`、`SourceManagementService`、`RelationManagementService`、`ManagementOverviewService`、`ImportBatchReviewService` 和公共审计基类；`EventManagementService` 保留兼容门面并删除重复私有实现 | 后端 `python -m unittest tests.test_event_management` 通过，12/12；后端 `python -m unittest discover tests` 通过，59/59；`EventManagementService` 降到 371 行 | 进入 R4，抽取 import 和 management 共享的地区/国家/政权/分类 upsert |
| 2026-07-30 | 完成后端 R4 公共历史实体 upsert 抽取：新增 `HistoricalEntityResolver`，导入确认和后台事件编辑共用地区、国家、政权、分类 upsert | 后端 `python -m unittest tests.test_import_review tests.test_event_management` 通过，19/19；后端 `python -m unittest discover tests` 通过，59/59 | 进入 R5，为管理写接口补 Pydantic request/response models |
| 2026-07-30 | 完成后端 R5 写接口 Pydantic 化：admin、imports、knowledge/vector 写接口新增 request/response models，并补 OpenAPI schema 回归测试 | 后端 `python -m unittest tests.test_api_admin_schemas tests.test_import_review tests.test_knowledge_service tests.test_event_management` 通过，25/25；后端 `python -m unittest discover tests` 通过，61/61 | 下一步收尾 R6 轻微代码味道，随后进入 Agent 返回结构标准化 |
| 2026-07-30 | 完成后端 R6 轻微代码味道清理：新增 `payload_to_dict` 统一路由 payload 转换，新增 `normalize_pagination` 统一分页 clamp，并复用公共审计/JSON safe helper | 后端 `python -m unittest tests.test_import_review tests.test_event_management tests.test_api_admin_schemas` 通过，21/21；后端 `python -m unittest discover tests` 通过，61/61；`EventManagementService` 降到 370 行 | 后端重构工作表 R1-R6 收口，下一步推进 Agent 返回结构标准化 |
| 2026-07-30 | 完成 Agent 返回结构标准化：新增结构化 response normalizer，同步接口和 SSE `final_answer` 均输出 `answer`、`events`、`references`、`links`；前端聊天页改为按标准字段渲染事件卡片和引用来源 | 后端 `python -m unittest tests.test_agent_loop tests.test_api_agent` 通过，10/10；后端 `python -m unittest discover tests` 通过，61/61；前端 `npm.cmd run build` 通过 | 下一步推进 RAG 引用注入回答，让回答正文和引用来源更紧密 |
| 2026-07-30 | 完成 RAG 引用注入回答第一版：Agent registry 新增 `search_knowledge` 工具，RuleBased Agent 在最终回答前检索知识库 chunk，回答正文追加参考资料，结构化 `references` 同时包含事件来源和知识文档 chunk | 后端 `python -m unittest tests.test_agent_loop tests.test_api_agent tests.test_agent_worker tests.test_knowledge_service` 通过，22/22；后端 `python -m unittest discover tests` 通过，62/62 | 下一步做 Langfuse 集成预留，或提交 W5-W6 改动 |
| 2026-07-30 | 完成 Langfuse 集成预留第一版：新增 telemetry adapter 和环境变量配置，AgentLoop 在 run/stream/worker 路径预留 trace、tool、token、错误上报入口；同步接口、SSE final、运行详情和聊天页可承接 Langfuse 外部 trace 链接 | 后端 `python -m unittest tests.test_agent_loop tests.test_api_agent tests.test_agent_worker` 通过，19/19；后端 `python -m unittest discover tests` 通过，63/63；前端 `npm.cmd run build` 通过 | 下一步提交 W5-W7 改动，或进入真实数据导入演练和管理后台体验修复 |
| 2026-07-30 | 完成真实数据导入演练扩展 W4：新增 22 条 `600-900` 年扩展种子数据，通过导入审核流创建并确认批次 `2d9ea246-3d79-4753-89c2-03f853406452`，入库后可按批次筛选和核验质量问题 | `python data/validate_events.py data/imports/curated_seed_600_900_extended.json` 通过；后端 `python -m unittest tests.test_import_review tests.test_seed_import_dataset tests.test_event_management` 通过，21/21；批次核验返回 22 条事件、8 条低置信、6 条弱来源、1 个重复候选、0 个结构缺口 | 下一步根据这批质量信号修复管理后台体验，优先优化弱来源/低置信处理入口和重复候选提示 |
| 2026-07-30 | 完成管理后台体验修复 W3 第一批：数据质量页改为可点击摘要卡片，修复 issue message 展示，补 metadata 辅助信息和完整 issue_type 筛选；真实数据导致的同期事件测试假设也改为按目标 id 断言 | 后端 `python -m unittest discover tests` 通过，65/65；前端 `npm.cmd run build` 通过 | 下一步继续优化导入详情页重复候选提示和事件详情页弱来源处理效率 |
| 2026-07-30 | 完成管理后台体验修复 W3 第二批：导入详情页重复候选改为可读候选卡片和字段差异列表，事件详情页弱来源高亮并增加“标为可靠来源”快捷操作 | 后端 `python -m unittest discover tests` 通过，65/65；前端 `npm.cmd run build` 通过 | 下一步做移动端视觉 QA，或提交 W3/W4 改动 |
| 2026-07-30 | 完成管理后台体验修复 W3 第三批：移动端后台表格卡片化，压缩工具栏、指标卡和代码块高度，修复单列布局下导航区域被拉伸导致的大空白 | 后端 `python -m unittest discover tests` 通过，65/65；前端 `npm.cmd run build` 通过；浏览器 390px 视口检查 `/admin`、`/admin/events`、`/admin/quality` 均无横向溢出 | W3/W4 已可提交；下一步可进入 Langfuse SDK 正式接入或继续数据质量运营 |
| 2026-07-30 | 完成数据质量处理闭环 W8：新增 `data_quality_issue_actions` 台账表、`POST /admin/data-quality/issues/actions` 接口，质量页支持标记已处理、忽略和重新打开问题 | 后端 `python -m unittest discover tests` 通过，66/66；前端 `npm.cmd run build` 通过；schema 文件测试覆盖新表和状态约束 | 下一步可做导入批次运营报表，或进入 Langfuse SDK 正式接入 |
| 2026-07-30 | 完成导入批次运营报表 W9：新增 `GET /admin/import-batches/{batch_id}/report`，批次详情页展示入库事件、待处理质量问题、处理率、质量分解、地区/年份/来源可靠度分布和优先处理项 | 后端 `python -m unittest discover tests` 通过，67/67；前端 `npm.cmd run build` 通过；专项管理测试 19/19 通过 | 下一步建议进入 Langfuse SDK 正式接入，或补知识库版本和重切分 |
| 2026-07-30 | 完成知识库版本和重切分 W10：新增 `knowledge_document_versions` 版本快照表，文档 ingest/rechunk 会记录版本；新增版本列表和 rechunk API，知识详情页可查看版本并生成新 chunk 版本 | 后端 `python -m unittest discover tests` 通过，68/68；前端 `npm.cmd run build` 通过；知识库专项测试和 schema/OpenAPI 测试 10/10 通过 | 下一步建议做向量任务自动处理，或进入 Langfuse SDK 正式接入 |
| 2026-07-30 | 完成向量任务自动处理 W11：新增 pending vector job 自动领取和批量处理接口，新增 `apps.worker.vector_worker` 常驻/单次处理器，向量页支持创建并自动处理以及批量处理 pending jobs | 后端 `python -m unittest discover tests` 通过，71/71；前端 `npm.cmd run build` 通过；知识库/向量专项和 schema/OpenAPI 测试 13/13 通过 | 下一步建议进入 Langfuse SDK 正式接入，或做 LangGraph 工作流迁移预研 |
| 2026-07-30 | 完成 Langfuse SDK 正式接入 W12：`AgentTelemetry` 可选加载 Langfuse SDK，创建 deterministic trace、agent observation、model generation、tool observation，并上报 token、成本、完成/失败/取消状态；未配置或 SDK 不可用时不影响 Agent 主链路 | 后端 `python -m unittest tests.test_agent_loop` 通过，9/9；后端 `python -m unittest discover tests` 通过，72/72 | 下一步建议做 LangGraph 工作流迁移预研，或把本地评测结果接入 Langfuse datasets/evals |
| 2026-07-30 | 完成 LangGraph 迁移前置 W13：新增 `AGENT_WORKFLOW_ENGINE`、`agent.runtime.workflow` 工厂和 LangGraph 可选单节点适配器；API 同步/SSE 与 worker 不再直接依赖具体 Loop，为后续拆 decision/tool/confirm/finish 节点做切换边界 | 后端 `python -m unittest tests.test_agent_workflow tests.test_agent_loop tests.test_api_agent tests.test_agent_worker` 通过，24/24；后端 `python -m unittest discover tests` 通过，76/76 | 下一步建议把 LangGraph 适配器从单节点拆成多节点工作流，或接 Langfuse datasets/evals |

## 12 周开发周期

| 周次 | 日期范围 | 阶段 | 业务目标 | 技术任务 | 交付物 | 状态 |
|---|---|---|---|---|---|---|
| 第 1 周 | 2026-07-28 至 2026-08-03 | 产品边界 | 明确历史时间对照 Agent 的第一版范围 | 完成 PRD、技术设计、数据模型、首批事件字段标准 | 产品边界文档、技术设计文档、数据模板 | 已完成 |
| 第 2 周 | 2026-08-04 至 2026-08-10 | 基础 MVP | 搭建可提问的历史 Agent 雏形 | 初始化 FastAPI 入口、数据库健康检查、规则版 Agent、基础查询服务 | 可运行的后端查询 Demo | 已完成 |
| 第 3 周 | 2026-08-11 至 2026-08-17 | 基础 MVP | 支持按年份和时间段查询事件 | 实现手写 Agent Loop、ModelAdapter、工具注册表、工具执行器、年份查询、时间段查询、事件详情工具；查询源从 JSON 切换到 PostgreSQL | 可查询真实数据库的历史事件 Agent | 已完成 |
| 第 4 周 | 2026-08-18 至 2026-08-24 | 数据底座 | 建立历史事件结构化数据库 | PostgreSQL 表设计、pgvector、导入脚本、事件来源表、基础校验 | PostgreSQL 历史事件数据底座 | 已完成 |
| 第 5 周 | 2026-08-25 至 2026-08-31 | 任务型 Agent | 展示 Agent 每一步执行过程 | 任务表、步骤表、工具调用表、SSE 步骤流、执行日志、取消入口 | 可回放、可流式观察、可取消的 Agent 执行记录 | 已完成 MVP |
| 第 6 周 | 2026-09-01 至 2026-09-07 | 横向对照 | 生成多地区时间对照表 | compare_regions、React 横向对照表组件、事件详情和来源展示 | 600-900 年欧亚历史对照表 Demo | 已完成 MVP |
| 第 7 周 | 2026-09-08 至 2026-09-14 | RAG 和来源 | 支持来源引用和文本检索 | pgvector、文档切分、来源检索、引用格式输出 | 带来源的历史问答 | 已完成检索 MVP 和引用注入第一版 |
| 第 8 周 | 2026-09-15 至 2026-09-21 | 关联分析 | 分析同期事件是否有关联 | event_relations、find_related_events、证据强弱提示 | 事件关系分析 Demo | 已完成 MVP |
| 第 9 周 | 2026-09-22 至 2026-09-28 | 安全和权限 | 防止错误导入、错误修改和无来源结论 | 只读工具权限、管理员导入确认、审计日志、争议标记 | 安全策略和数据修改确认机制 | 已完成写操作确认 MVP，完整 RBAC 待做 |
| 第 10 周 | 2026-09-29 至 2026-10-05 | Langfuse 可观测性集成 | 能排查每次回答为什么这么回答 | 接入 Langfuse，上报 Trace、工具耗时、模型输入输出摘要、token 和成本 | Langfuse 中可查看 Agent 运行详情；本系统后台只保留跳转入口 | 已完成模型/工具记录 MVP 和 Langfuse 预留第一版，完整 SDK 接入待做 |
| 第 11 周 | 2026-10-06 至 2026-10-12 | 评测 | 判断 Agent 回答质量是否稳定 | 构建评测集、年份查询评测、对照表评测、关联分析评测 | 回归测试报告 | 已完成 MVP |
| 第 12 周 | 2026-10-13 至 2026-10-19 | 平台化 | 形成可持续扩展的内部数据运营版本 | 数据导入审核后台、事件库管理、来源管理、关系管理、知识库管理、向量管理、模型配置、反馈入口 | Alpha 版本；运行观测、成本看板和评测分析由 Langfuse 提供 | 待开始 |

## 第一批数据建设计划

| 批次 | 范围 | 数量目标 | 用途 |
|---|---|---:|---|
| Batch 1 | 600-900 年中国、阿拉伯帝国、拜占庭、日本 | 100 条 | 验证年份查询和事件详情 |
| Batch 2 | 600-900 年法兰克王国、印度、中亚 | 100 条 | 验证横向对照 |
| Batch 3 | 战争、宗教传播、贸易、王朝更替专题 | 150 条 | 验证主题查询 |
| Batch 4 | 关键事件关系和来源 | 50-150 条 | 验证关联分析 |

## MVP 验收清单

| 编号 | 验收项 | 标准 |
|---|---|---|
| A1 | 年份查询 | 输入 755 年，能返回中国、阿拉伯帝国、拜占庭、日本等地区相关事件 |
| A2 | 时间段查询 | 输入 700-800 年，能按地区输出对照表 |
| A3 | 事件详情 | 查询安史之乱，能返回时间、地点、政权、原因、影响、来源 |
| A4 | 同期事件 | 查询安史之乱，能找出同一时期其他地区事件 |
| A5 | 关联分析 | 对可能有关联的事件，能说明证据强弱和不确定性 |
| A6 | 来源引用 | 核心事件至少显示一个来源 |
| A7 | 执行记录 | 每次回答能看到调用了哪些工具 |
| A8 | 风险控制 | Agent 不能自动修改或导入历史事件数据 |

## 当前任务队列

当前状态：后端查询、Agent Loop、Function Calling、工具稳定性、模型观测、SSE 步骤流、运行取消、Redis 队列/Worker、processing ack、失败重试、死信队列、visibility timeout 回收、checkpoint 恢复、数据导入审核流、真实数据导入演练扩展、RAG 检索、RAG 引用注入第一版、事件管理、人工确认、React 聊天主界面、React Router 页面跳转、事件详情页、移动端适配、`/admin` 管理后台可运营版、种子数据核验支撑能力、完整数据库初始化入口、后端重构 R1-R6、Agent 返回结构标准化、Langfuse 集成预留第一版、Langfuse SDK 正式接入 W12、LangGraph 迁移前置 W13、管理后台体验修复 W3、数据质量处理闭环 W8、导入批次运营报表 W9、知识库版本和重切分 W10、向量任务自动处理 W11 已完成；管理后台边界已明确为数据资产、知识库和向量管理；Agent Trace、token/cost、工具调用链和评测分析使用 Langfuse，不自研重复后台。下一步提交 W13 改动，或拆 LangGraph 多节点工作流。

| 优先级 | 任务 | 负责人 | 状态 | 对应 PDF 功能/章节 |
|---:|---|---|---|---|
| 1 | 确定 MVP 时间范围和地区范围 | 产品 | 已确定 | 第一阶段：确定智能体产品边界 |
| 2 | 定义历史事件数据模板 | 后端/数据 | 已完成 | 第四阶段：设计工具系统；第八阶段：知识库数据结构 |
| 3 | 搭建项目目录 | 工程 | 已完成 | 十八：推荐项目目录 |
| 4 | 准备首批 600-900 年事件样例 | 数据 | 已完成 | 第八阶段：RAG 知识库的数据基础 |
| 5 | 搭建 FastAPI + React 基础项目 | 工程 | 已完成，React 前端已支持聊天页、路由跳转和移动端适配 | 第一阶段 MVP：React 聊天页面、FastAPI 接口 |
| 6 | 实现历史查询工具 | 后端 | 已完成 PostgreSQL 版 | 第四阶段：设计工具系统 |
| 7 | 接入本地 PostgreSQL 连接 | 后端 | 已完成 | 最终技术选型：PostgreSQL |
| 8 | 创建 `historical_agent` 数据库并建表 | 后端 | 已完成 | 第七阶段：任务状态；第十三阶段：评测体系 |
| 9 | 安装并启用 pgvector | 后端 | 已完成 | 第八阶段：RAG 知识库；最终技术选型：pgvector |
| 10 | 导入样例历史事件到 PostgreSQL | 后端/数据 | 已完成 | 第八阶段：知识库和来源 |
| 11 | 实现 PostgreSQL Repository | 后端 | 已完成 | 工具返回真实系统结果，避免只靠 Prompt |
| 12 | 启动并验证 FastAPI 查询接口 | 后端 | 已完成 | 最终技术选型：FastAPI |
| 13 | 建立 Agent 执行记录写入 | 后端 | 已完成 | 第十一阶段：任务持久化；第十四阶段：可观测性 |
| 14 | 完善事件详情、同期事件、事件关系查询 | 后端 | 已完成 | 第四阶段：查询型工具；第八阶段：引用来源 |
| 15 | 建立 Agent 评测样例和自动评测运行器 | 测试 | 已完成，MVP 评测 4/4 通过；后续评测 UI 交给 Langfuse | 第十三阶段：评测体系 |
| 16 | 增强规则版 Agent 任务识别 | 后端 | 已完成，支持关系题、对照题、多步工具记录 | 第三阶段：实现最小 Agent Loop |
| 17 | 实现 ModelAdapter / ToolRegistry / ToolExecutor / Agent Loop | 后端 | 已完成，MVP 评测 4/4 通过 | 第二阶段：大模型消息协议；第三阶段：Agent Loop；第四阶段：工具系统 |
| 18 | 接入 OpenAI Function Calling | 后端 | 已完成 MVP，默认仍可用 rule_based fallback | 第二阶段：Structured Output；最终技术选型：JSON Schema Function Calling |
| 19 | 完善 Function Calling 参数校验、超时和重试 | 后端 | 已完成 MVP | 第三阶段：参数校验、超时、重试 |
| 20 | 记录模型 token、耗时和成本统计 | 后端 | 已完成 MVP；后续不自研成本统计看板，统一接 Langfuse | 第三阶段：Token/成本预算；第十四阶段：可观测性 |
| 21 | 实现 SSE 步骤流 | 后端 | 已完成 MVP | 第十六阶段：前后端通信；系统架构：API Gateway SSE |
| 22 | 增强 Agent 运行状态、取消和失败处理 | 后端 | 已完成 MVP | 第十一阶段：任务持久化与故障恢复 |
| 23 | 实现数据导入审核流 | 后端/数据 | 已完成 MVP | 第十阶段：人工确认机制；第十二阶段：安全体系 |
| 24 | 实现 RAG / embedding / pgvector 检索 | 后端/知识库 | 已完成 MVP | 第八阶段：RAG 知识库 |
| 25 | 实现事件管理接口和权限/人工确认 | 后端 | 已完成 MVP，完整 RBAC 待做 | 平台化第一版；第十二阶段：安全体系 |
| 26 | 实现 Redis / Worker / 任务恢复 | 后端 | 已完成 Redis 队列/Worker、processing ack、失败重试、死信队列、visibility timeout 回收和 checkpoint 恢复 MVP | 系统架构：Task Worker；第十一阶段：任务持久化与故障恢复 |
| 27 | 实现横向对照表 UI | 前端 | 已完成 MVP | 第一阶段 MVP：React 聊天页面；业务可视化前端 |
| 28 | 聊天主界面、事件详情页和移动端适配 | 前端 | 已完成 MVP，已接入 `react-router-dom` | 第一阶段 MVP：React 聊天页面；第十六阶段：前后端通信；业务可视化前端 |
| 29 | Agent 返回结构标准化 | 前端/后端 | 已完成；后端同步接口和 SSE final 输出 `answer`、`events`、`references`、`links`，前端按标准字段渲染事件卡片和引用来源 | 第二阶段：Structured Output；第十六阶段：前后端通信 |
| 30 | 横向对照结果详情页 | 前端/后端 | 待开始 | 第四阶段：工具系统；业务可视化前端 |
| 31 | 数据导入审核后台 | 前端/后端 | 已完成；支持导入解析、批次列表、staging 审核、修正、合并、确认/拒绝 | 第十阶段：人工确认机制；第十二阶段：安全体系；平台化第一版 |
| 32 | 事件库、来源、关系、知识库和向量管理后台 | 前端/后端 | 已完成；支持事件筛选/编辑、来源 CRUD/核验、关系 CRUD、知识文档维护和向量任务 | 第八阶段：RAG 知识库；平台化第一版 |
| 33 | Langfuse 集成 | 后端/平台 | 已完成 SDK 接入第一版；Agent 运行、工具调用、token/cost、失败/取消状态可上报 Langfuse；不自研对应后台 | 第十三阶段：评测体系；第十四阶段：可观测性 |
| 34 | 导入审核后台后端增强 | 后端 | 已完成；已补批次列表、staging 修正、重新校验、导入预览 | 第十阶段：人工确认机制；第十二阶段：安全体系；平台化第一版 |
| 35 | 管理总览和事件列表后端 | 后端 | 已完成；已补后台首页统计、事件分页搜索筛选、事件审计日志、后台事件扩展字段更新 | 平台化第一版；第十二阶段：安全体系 |
| 36 | 来源、关系、知识库、向量管理后端 | 后端 | 已完成；已补来源 CRUD、关系 CRUD、文档列表/chunk/reembed、向量覆盖率/重建和向量任务 | 第八阶段：RAG 知识库；平台化第一版 |
| 37 | 数据质量检查 | 后端 | 已完成；已补 summary 和问题列表，暂不涉及权限 | 平台化第一版；数据质量运营 |
| 38 | 数据字典和后台事件详情聚合 | 后端 | 已完成；支撑前端筛选器、表单和详情页 | 平台化第一版 |
| 39 | 批量操作和导入合并策略 | 后端 | 已完成；已补事件批量更新、staging 批量重校验、来源批量核验、导入解析和合并策略 | 数据导入审核；平台化第一版 |
| 40 | 管理后台前端计划 | 前端 | 已完成计划；拆为 F1-F5，先做管理壳子和导入审核闭环 | 平台化第一版；数据运营后台 |
| 41 | 管理后台前端可运营版 | 前端 | 已完成；事件高级筛选、事件表单编辑、来源编辑/删除、关系编辑/删除、知识文档元数据维护均已接入 | 平台化第一版；数据运营后台 |
| 42 | 小批量历史事件种子导入 | 数据/前端/后端 | 已完成；新增 `data/imports/curated_seed_600_900.json`，通过审核流导入 12 条 633-883 年事件，批次 `3ab3c564-d324-4b35-ac30-5b5fe82d0a11` | 第十阶段：人工确认机制；平台化第一版 |
| 43 | 真实数据导入演练扩展 | 数据/前端/后端 | 已完成；新增 22 条扩展种子数据，通过导入审核流确认入库，批次 `2d9ea246-3d79-4753-89c2-03f853406452` 可用于后台质量修复 | 第十阶段：人工确认机制；平台化第一版 |
| 44 | 种子数据核验支撑能力 | 后端/前端 | 已完成；`/admin/events` 支持 `import_batch_id` 筛选，数据质量新增 `duplicate_title` 同标题候选检测，新增 `GET /admin/import-batches/{batch_id}/review`，导入详情页可查看本批低置信、弱来源、重复候选和结构缺口 | 第十阶段：人工确认机制；平台化第一版 |
| 45 | 数据库初始化脚本同步 | 后端/数据库 | 已完成；新增 `infrastructure/database/init.sql`，完整初始化当前后端依赖的基础表、事件审计、知识库、事件向量列、向量任务表和基础字典，并补 schema 文件测试 | 数据底座；平台化第一版 |
| 46 | 后端重构计划 | 后端 | 已完成；R1 统一向量任务表 schema 兜底、R2 FastAPI 路由拆分、R3 管理服务拆分、R4 公共历史实体 upsert 抽取、R5 写接口 Pydantic 化、R6 轻微代码味道清理均已完成 | 平台化第一版；工程可维护性 |
| 47 | 数据质量处理闭环 | 前端/后端 | 已完成；新增质量问题处理台账、API 和前端操作，支持已处理、忽略和重新打开 | 平台化第一版；数据质量运营 |
| 48 | 导入批次运营报表 | 前端/后端 | 已完成；批次详情页可复盘质量处理进度、质量分解、地区/年份/来源分布和优先处理项 | 平台化第一版；数据导入运营 |

## 下一阶段执行计划

| 优先级 | 任务 | 目标 | 验收标准 | 对应 PDF 功能/章节 |
|---:|---|---|---|---|
| 1 | 管理后台体验修复 | 已完成 W3 和 W8：质量页、重复候选、弱来源处理、移动端视觉 QA、质量问题处理台账均已收口 | 数据维护不再依赖 curl 或脚本，后台可稳定日常使用 | 平台化第一版 |
| 2 | 真实数据导入演练扩展 | 已完成 22 条扩展批次；后续仅按专题需要继续扩展 | 用真实数据验证后台可运营性，并整理需要修复的问题清单 | 第十阶段：人工确认机制；平台化第一版 |
| 3 | Agent 返回结构标准化 | 后端明确输出 `answer`、`references`、`links`、`events`，前端根据类型渲染事件、来源、对照卡片 | 前端不再依赖递归解析工具 observation；刷新和跳转后链接仍可用 | 第二阶段：Structured Output；第十六阶段：前后端通信 |
| 4 | RAG 引用注入回答 | 把知识库检索和事件来源稳定注入 Agent 回答 | 回答能展示引用来源和知识文档 chunk，降低无来源结论风险 | 第八阶段：RAG 知识库 |
| 5 | Langfuse SDK 接入 | 已完成第一版；后端可选加载 Langfuse SDK，上报 agent/tool observation、token、成本和错误状态；本系统后台只提供跳转入口，不做 Agent run 搜索与分析页 | 可以从本系统 run_id 跳转到 Langfuse 查看完整运行详情 | 第十三阶段：评测体系；第十四阶段：可观测性 |

## 管理后台前端开发工作表

| 批次 | 优先级 | 工作项 | 目标 | 验收标准 | 状态 |
|---|---:|---|---|---|---|
| F1 | 1 | 管理后台壳子和导航 | 建立 `/admin`、侧边导航、总览指标、后台入口 | 聊天页和后台可互跳；总览可读取 `/admin/overview` 和 `/vectors/status` | 已完成 |
| F1 | 2 | 管理 API client 和类型 | 将管理接口从聊天 API 中拆出 | 页面不直接拼 URL；统一处理 loading/error/empty | 已完成 |
| F2 | 3 | 数据导入工作台 | 粘贴 JSON/CSV、解析预览、创建批次 | 可调用 `/imports/parse` 和 `/imports/batches` 创建真实批次 | 已完成 |
| F2 | 4 | 导入审核详情 | 查看 staging、错误、重复候选和差异 | 可调用批次 staging 和 preview 接口，定位问题行 | 已完成 |
| F2 | 5 | staging 修正和合并 | 修正、重校验、合并重复、确认或拒绝 | 可完成导入审核闭环 | 已完成 |
| F3 | 6 | 事件库列表 | 搜索、筛选、分页、批量操作 | 支持关键词、年份、地区、状态、最低置信度、有无来源筛选和批量归档 | 已完成 |
| F3 | 7 | 事件详情编辑 | 编辑事件字段、查看来源/关系/审计 | 事件字段已改为表单编辑，可保存编辑并看到审计日志 | 已完成 |
| F3 | 8 | 来源和关系维护 | 管理来源、核验来源、维护关系证据 | 支持来源新增/编辑/删除/核验，关系新增/编辑/删除 | 已完成 |
| F4 | 9 | 数据质量修复台 | 问题 summary 和问题列表 | 可从问题跳转到修复目标 | 已完成 |
| F4 | 10 | 知识库管理 | 文档列表、chunk、更新、版本记录、rechunk、reembed | 可查看文档和 chunk，更新元数据，停用/归档，查看版本，生成新 chunk 版本，触发 reembed | 已完成 |
| F4 | 11 | 向量管理 | 覆盖率、重建任务、任务处理 | 可创建并处理 vector rebuild job | 已完成 |
| F5 | 12 | 前端拆分和视觉 QA | 拆分 pages/components，补移动端和构建验证 | `npm run build` 通过；更细移动端视觉 QA 后续继续 | 已完成第一版 |

## 后端继续加强工作表（暂不考虑权限）

| 批次 | 优先级 | 工作项 | 目标 | 验收标准 | 状态 |
|---|---:|---|---|---|---|
| B1 | 1 | 数据质量检查 summary | 给后台总览页提供数据问题概览 | 返回无来源、低置信、疑似重复、时间异常、关系缺证据等计数 | 已完成 |
| B1 | 2 | 数据质量问题列表 | 让运营者按问题类型进入修复 | 支持 issue_type、severity、分页；每条问题可跳转对应事件或关系 | 已完成 |
| B1 | 3 | 数据字典接口 | 支撑前端筛选器和编辑表单 | 返回地区、政权、分类、状态、source_type、relation_type、time_precision | 已完成 |
| B1 | 4 | 后台事件详情聚合 | 前端事件详情页一次拿齐管理数据 | 返回完整事件、分类、来源、关系、审计、导入批次和 embedding 状态 | 已完成 |
| B2 | 5 | 批量操作第一版 | 提升运营效率 | 支持事件批量更新、staging 批量重校验、来源批量核验 | 已完成 |
| B3 | 6 | 导入合并策略 | 重复预览后可处理冲突 | 支持 keep_existing、replace_existing、merge_sources、merge_categories、merge_sources_and_categories | 已完成 |
| B3 | 7 | 导入文件解析轻量版 | 提升导入体验 | 支持 JSON/CSV 解析为标准 events payload | 已完成 |
| B4 | 8 | 知识库版本和重切分 | 支撑文档更新可追溯 | 文档更新保留版本，chunk 变化可查看 | 已完成 |
| B4 | 9 | 向量任务自动处理 | 避免手动处理向量任务 | 向量 job 可自动领取 pending 任务并处理，失败可查看和重试 | 已完成 |
