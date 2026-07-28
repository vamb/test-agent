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
    -> Trace / Evaluation
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
| Trace | OpenTelemetry + Langfuse/LangSmith |
| 测试 | Pytest + Agent Evaluation Dataset |
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
