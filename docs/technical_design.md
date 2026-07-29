# 历史时间对照 Agent 技术设计

## 总体架构

系统采用“结构化历史数据库 + 检索系统 + Agent 分析层 + 可视化前端”的架构。

```text
React Web
  -> FastAPI Gateway
    -> Agent Runtime
      -> Model Adapter
      -> Tool Registry
      -> Historical Query Tools
      -> RAG Tools
    -> PostgreSQL + pgvector
    -> Redis
    -> Langfuse Trace / Evaluation
```

## 推荐技术栈

| 层级 | 技术 |
|---|---|
| Web 前端 | React + TypeScript + Vite |
| UI 组件 | Ant Design 或 Tailwind + Radix |
| API 服务 | FastAPI |
| 数据模型 | Pydantic |
| Agent 编排 | 第一版手写 Agent Loop，生产阶段 LangGraph |
| 模型访问 | Model Adapter |
| 工具调用 | JSON Schema Function Calling |
| 数据库 | PostgreSQL |
| 向量检索 | pgvector |
| 缓存和任务锁 | Redis |
| 数据导入 | Python ETL |
| Trace / Evaluation | Langfuse |
| 测试 | Pytest + Agent Evaluation Dataset，评测结果后续接入 Langfuse |
| 部署 | Docker Compose |

## 核心数据模型

### 结构设计说明

正式数据库结构见 `infrastructure/database/schema.sql`，设计说明见 `infrastructure/database/schema_notes.md`。

核心上分为六类表：

| 类型 | 表 |
|---|---|
| 地理和政权 | `regions`、`modern_countries`、`polities`、`polity_modern_country_links` |
| 分类和参与者 | `categories`、`actors` |
| 历史事件 | `historical_events`、`event_aliases`、`event_categories`、`event_actors` |
| 来源和关系 | `event_sources`、`event_relations` |
| 数据导入 | `import_batches`、`import_event_staging` |
| Agent 和评测 | `tools`、`agent_runs`、`agent_steps`、`evaluation_cases`、`evaluation_runs` |

### historical_events 核心字段

| 字段 | 类型 | 说明 |
|---|---|---|
| id | uuid | 事件 ID |
| title | text | 事件标题 |
| canonical_title | text | 规范标题 |
| start_year | int | 开始年份，公元前用负数 |
| start_month | int | 开始月份，可为空 |
| start_day | int | 开始日期，可为空 |
| end_year | int | 结束年份 |
| end_month | int | 结束月份，可为空 |
| end_day | int | 结束日期，可为空 |
| start_date_text | text | 原始开始时间文本 |
| end_date_text | text | 原始结束时间文本 |
| time_precision | enum | day、month、year、decade、century、range、approximate、unknown |
| is_approximate | boolean | 是否为约略时间 |
| region_id | uuid | 关联大区 |
| polity_id | uuid | 关联政权、国家或文明 |
| primary_modern_country_id | uuid | 主要现代国家映射，可为空 |
| location_text | text | 原始地点文本 |
| summary | text | 事件摘要 |
| causes | text[] | 主要原因 |
| effects | text[] | 主要影响 |
| status | enum | draft、reviewing、verified、disputed、archived |
| confidence | numeric | 置信度 |
| importance_score | numeric | 重要性评分，用于排序 |
| embedding | vector | 向量检索，可选字段，由 `schema_vector_optional.sql` 启用 |
| created_at | timestamptz | 创建时间 |
| updated_at | timestamptz | 更新时间 |

### event_sources

| 字段 | 类型 | 说明 |
|---|---|---|
| id | uuid | 来源 ID |
| event_id | uuid | 对应事件 |
| source_title | text | 来源名称 |
| source_type | enum | book、paper、encyclopedia、website、dataset |
| url | text | 来源链接 |
| citation | text | 引用格式 |
| excerpt | text | 摘要或证据片段 |
| reliability | numeric | 来源可靠度 |

### event_relations

| 字段 | 类型 | 说明 |
|---|---|---|
| id | uuid | 关系 ID |
| source_event_id | uuid | 起点事件 |
| target_event_id | uuid | 终点事件 |
| relation_type | enum | cause、effect、contemporary、influence、trade_link、conflict_link、uncertain |
| explanation | text | 关系说明 |
| confidence | numeric | 关系置信度 |
| evidence_source_id | uuid | 证据来源 |

## Agent 工具设计

第一版工具全部只读，避免安全和数据污染问题。

| 工具名 | 功能 | 风险等级 |
|---|---|---|
| search_events_by_year | 按年份、地区、类型检索事件 | low |
| search_events_by_range | 按时间段检索事件 | low |
| get_event_detail | 获取事件详情、原因、影响、来源 | low |
| find_contemporary_events | 根据某个事件查找同期其他地区事件 | low |
| compare_regions | 对比多个地区在某个时间段的发展 | low |
| find_related_events | 查找可能有关联的事件 | low |
| generate_timeline | 生成时间线或对照表数据 | low |

第二版再增加需要确认的工具：

| 工具名 | 功能 | 风险等级 | 策略 |
|---|---|---|---|
| import_events | 批量导入事件 | medium | 需要用户确认 |
| update_event | 修改事件字段 | medium | 需要用户确认和审计 |
| link_events | 创建事件关系 | medium | 需要来源和确认 |
| mark_source_verified | 标记来源已核验 | medium | 仅管理员 |

## Agent 回答原则

Agent 输出时必须遵守：

1. 区分事实、解释、推断和争议。
2. 历史事件尽量给出来源。
3. 时间不确定时要说明“约”“大约”“时间范围”。
4. 不把现代国家概念强行套到古代政权上。
5. 横向比较时优先按地区、政权、主题组织。
6. 关联分析必须说明证据强弱，不能把同期事件直接说成因果关系。

## 前端页面结构

第一版推荐四个主要区域：

| 区域 | 功能 |
|---|---|
| 查询区 | 输入年份、时间段、事件、地区、主题 |
| 对照表区 | 显示同一时间点或时间段各地区事件 |
| Agent 分析区 | 展示背景说明、关联推断、争议提醒 |
| 来源区 | 展示事件来源、引用、置信度 |

第二版可增加：

| 页面 | 功能 |
|---|---|
| 时间轴视图 | 横向滚动查看多地区历史 |
| 地图视图 | 按区域展示事件分布 |
| 关系图 | 展示事件之间的影响关系 |
| 数据管理后台 | 导入、校对、审核历史事件 |

### 管理后台前端路由

管理后台采用同一个 React/Vite 应用，不单独新建前端工程。当前聊天页继续作为 `/`，后台挂在 `/admin` 下，页面风格延续深色档案工作台，但控件更偏运营系统：信息密度高、表格清晰、编辑表单稳定、批量操作可预期。

| 路由 | 页面 | 核心能力 |
|---|---|---|
| `/admin` | 管理总览 | 数据资产指标、导入待处理、数据质量摘要、向量覆盖率、快速入口 |
| `/admin/imports/new` | 数据导入工作台 | JSON/CSV 粘贴解析、预览错误、创建 import batch |
| `/admin/imports` | 导入批次列表 | 批次状态筛选、分页、进入审核详情 |
| `/admin/imports/:batchId` | 导入审核详情 | staging 行、校验错误、重复候选、差异预览、修正、重校验、合并、确认或拒绝 |
| `/admin/events` | 事件库列表 | 搜索筛选、分页、批量更新、进入事件详情 |
| `/admin/events/:eventId` | 后台事件详情 | 事件字段编辑、来源、关系、审计日志、导入批次、向量状态 |
| `/admin/relations` | 关系管理 | 事件关系搜索、新增、编辑、删除、证据来源维护 |
| `/admin/quality` | 数据质量修复台 | 问题 summary、问题列表、跳转到事件或关系修复 |
| `/admin/knowledge` | 知识库管理 | 文档列表、状态筛选、检索、进入 chunk 详情 |
| `/admin/knowledge/:documentId` | 知识文档详情 | chunk 查看、元数据更新、停用、reembed |
| `/admin/vectors` | 向量管理 | embedding 覆盖率、重建任务创建、任务状态和手动处理 |

前端实现顺序：

| 批次 | 范围 | 验收 |
|---|---|---|
| F1 | 后台壳子、导航、API client、总览 | `/admin` 可运行，能读取 overview 和 vector status |
| F2 | 导入解析、批次、staging 审核、合并、确认 | 可从前端完成一批事件导入入库 |
| F3 | 事件列表、事件详情、来源和关系维护 | 可完成事件日常维护，不依赖 curl |
| F4 | 数据质量、知识库、向量管理 | 可按质量问题修复数据，可管理 RAG 文档和向量任务 |
| F5 | 组件拆分、移动端、视觉 QA、构建验证 | `npm run build` 通过，桌面/移动端无重叠 |

## 管理后台与 Langfuse 分工

本系统自研后台只负责历史知识数据运营，不重复开发 Langfuse 已覆盖的 Agent 观测和评测分析能力。

### 我们开发的后台能力

| 模块 | 功能 |
|---|---|
| 管理总览 | 展示事件总数、待审核批次、低置信事件、无来源事件、知识文档数、向量覆盖率 |
| 数据导入 | 上传或粘贴历史事件数据，创建 import batch |
| 导入审核 | 查看 staging 行、校验错误、修正、拒绝、确认入库 |
| 事件库管理 | 搜索、筛选、编辑、归档、标记争议 |
| 来源管理 | 管理 citation、excerpt、URL、source type、reliability 和核验状态 |
| 关系管理 | 维护事件之间的 contemporary、cause、effect、influence、uncertain 等关系 |
| 知识库管理 | 导入文档、查看 chunk、停用文档、测试语义召回 |
| 向量管理 | 查看 embedding 覆盖率、重算向量、检查索引状态、测试向量检索 |
| 系统设置 | 管理 admin token、embedding provider、向量维度、导入规则和状态枚举 |

### 交给 Langfuse 的能力

| 能力 | 处理方式 |
|---|---|
| Agent 运行详情 | 不自研页面，使用 Langfuse trace |
| 工具调用链 | 不自研分析页，使用 Langfuse spans / observations |
| token、耗时、成本统计 | 不自研看板，后端负责上报到 Langfuse |
| 运行错误分析 | 不自研聚合分析，使用 Langfuse trace 和筛选能力 |
| Prompt 版本与运行关联 | 使用 Langfuse 记录和分析 |
| 评测中心 UI | 不自研，后续接 Langfuse datasets/evals |
| Agent run 搜索与筛选 | 不自研后台列表，使用 Langfuse 搜索能力 |
