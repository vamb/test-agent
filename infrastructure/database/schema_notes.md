# 历史时间对照 Agent 表结构设计说明

## 设计原则

这版表结构不是只为了存几条历史事件，而是为了支撑后续的横向对照、来源追溯、事件关系分析、数据导入审核和 Agent 评测。

核心原则：

1. 古代政权和现代国家分开存。
2. 地区、政权、分类、人物尽量规范化。
3. 历史时间允许不精确，保留原始时间文本。
4. 同期事件和因果关系分开表达。
5. 所有重要事件都能追溯来源。
6. 导入数据先进入 staging，验证后再进入正式事件表。
7. Agent 每次运行和每一步工具调用都要留痕。

## 核心业务表

| 表 | 用途 |
|---|---|
| `regions` | 大区和子区域，如东亚、中东、中亚、西欧 |
| `modern_countries` | 现代国家，用于筛选和地图映射 |
| `polities` | 古代政权、王朝、文明、国家 |
| `polity_modern_country_links` | 古代政权与现代国家的多对多映射 |
| `categories` | 事件分类，如政治、战争、宗教、贸易、科技 |
| `actors` | 人物、组织、政权实体 |
| `historical_events` | 历史事件主表 |
| `event_aliases` | 事件别名和多语言名称 |
| `event_categories` | 事件和分类的多对多关系 |
| `event_actors` | 事件和人物/组织的多对多关系 |
| `event_sources` | 事件来源和引用 |
| `event_relations` | 事件之间的因果、影响、贸易、战争、同期等关系 |

## 为什么不直接把 region、polity、category 都写成 text

MVP 可以这么做，但历史对照产品会很快遇到问题：

- “中国”可能指现代国家，也可能指唐朝、宋朝、明朝等政权。
- “欧洲”下面还要分西欧、拜占庭、法兰克、教廷等。
- 同一事件可能属于战争、政治、宗教多个分类。
- 同一政权可能覆盖多个现代国家。

所以正式结构中用 ID 关联，避免后期数据混乱。

## 时间字段设计

`historical_events` 同时存结构化时间和原始时间文本：

| 字段 | 说明 |
|---|---|
| `start_year` | 查询和排序用，公元前用负数 |
| `start_month` / `start_day` | 精确到月/日时使用 |
| `end_year` / `end_month` / `end_day` | 持续事件结束时间 |
| `start_date_text` / `end_date_text` | 保留原始表述，如“约公元前5世纪” |
| `time_precision` | 标记时间精度 |
| `is_approximate` | 是否为约略时间 |

这样既能做 SQL 查询，也不会丢掉历史叙述中的不确定性。

## 来源和置信度

`event_sources` 记录每个事件的来源，`reliability` 表示来源可靠度。`historical_events.confidence` 表示当前系统对事件结构化信息的置信度。

这两个字段不同：

- `source reliability`：来源本身可信度。
- `event confidence`：这条事件记录是否可信、是否完整、是否存在争议。

## 事件关系

`event_relations` 不只存因果，也存弱关系：

- `cause` / `effect`：强因果。
- `contemporary`：同期，不代表因果。
- `influence`：影响关系。
- `trade_link`：贸易关联。
- `conflict_link`：冲突关联。
- `migration_link`：迁徙关联。
- `religion_link`：宗教传播关联。
- `technology_link`：技术传播关联。
- `uncertain`：有线索但证据不足。

Agent 做关联分析时必须根据 `relation_type` 和 `confidence` 区分强弱。

## 导入流程

导入数据不直接写入正式表：

1. 创建 `import_batches`。
2. 原始 JSON/CSV 每行写入 `import_event_staging`。
3. 校验字段、时间、分类、来源。
4. 人工确认。
5. 写入正式表。

这样可以避免脏数据污染历史事件库。

## Agent 运行记录

| 表 | 用途 |
|---|---|
| `agent_runs` | 一次用户请求 |
| `agent_steps` | 模型调用、工具调用、观察结果、错误信息 |
| `tools` | 工具注册、风险等级、是否需要确认 |
| `event_change_logs` | 管理后台对事件、来源和关系的写操作审计 |

这些表用于：

- 排查 Agent 为什么这么回答。
- 统计工具成功率和耗时。
- 判断 Prompt 或模型升级是否让质量变好。
- 防止高风险工具被自动调用。

## 评测表

| 表 | 用途 |
|---|---|
| `evaluation_cases` | 固定评测问题和期望点 |
| `evaluation_runs` | 每次评测结果 |

## pgvector

本地基础 schema 不强依赖 `pgvector`，这样没有安装扩展时也可以先开发 SQL 查询、导入和 Agent 流程。

向量检索放在独立脚本：

```text
infrastructure/database/schema_vector_optional.sql
```

安装 PostgreSQL 的 pgvector 扩展后，再执行该脚本为 `historical_events` 增加 `embedding vector(1536)` 字段和向量索引。

当前完整管理后台还需要知识库和向量任务表：

```text
infrastructure/database/schema_knowledge.sql
infrastructure/database/schema_vector_jobs.sql
```

为了避免新环境漏执行脚本，推荐使用完整初始化入口：

```text
infrastructure/database/init.sql
```

`init.sql` 会执行基础 schema、事件审计、知识库、事件向量列、向量重建任务表和基础字典种子。样例事件关系种子 `seed_sample_relations.sql` 依赖样例事件数据，不放入默认初始化入口。

历史 Agent 很容易“看起来回答得像”，所以必须用评测集检查：

- 是否调用了正确工具。
- 是否没有调用禁止工具。
- 是否包含关键事实。
- 是否区分事实、推断和争议。
