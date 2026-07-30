# 下一步实施清单

## 立即要做

1. 真实数据导入演练：
   - 已先导入 12 条 633-883 年小批量种子事件
   - 已补导入批次核验面板，可查看低置信、弱来源、重复候选和结构缺口
   - 处理同名“大化改新”候选
   - 稳定后再扩展到 20-50 条历史事件
   - 通过 `/admin/imports/new` 解析 JSON/CSV
   - 审核 staging 行
   - 修正错误行
   - 处理重复候选和合并策略
   - 确认入库
   - 进入数据质量和事件详情页修复问题
2. Agent 返回结构标准化：
   - 稳定输出 `answer`
   - 稳定输出 `references`
   - 稳定输出 `links`
   - 稳定输出 `events`
   - 前端不再依赖递归解析工具 observation
3. 管理后台体验修复：
   - 根据真实导入演练修复字段校验
   - 优化错误提示和空状态
   - 优化重复合并提示
   - 做更细的移动端视觉 QA
4. RAG 引用注入回答：
   - 把事件来源注入回答
   - 把知识文档 chunk 注入回答
   - 前端展示引用来源
5. Langfuse 集成预留：
   - 上报 Agent trace
   - 上报工具调用链
   - 上报 token、耗时和成本
   - 评测结果后续接入 Langfuse datasets/evals
6. 已完成的管理后端增强：
   - 数据质量检查
   - 数据字典接口
   - 后台事件详情聚合
   - 批量操作第一版
   - 导入合并策略
   - JSON/CSV 导入解析轻量版
7. 已完成的管理前端：
   - 管理后台壳子和导航
   - 数据导入和审核
   - 事件库管理
   - 来源和关系维护
   - 数据质量修复
   - 知识库和向量管理
8. 已完成的数据库初始化同步：
   - 新增完整初始化入口 `infrastructure/database/init.sql`
   - 纳入事件审计、知识库、事件向量列、向量重建任务和基础字典
   - 补充管理后台筛选和核验所需索引

## 我们要开发的管理功能

| 模块 | 目标 |
|---|---|
| 管理总览 | 查看业务数据资产状态，包括事件数量、待审核批次、低置信事件、无来源事件、知识文档和向量覆盖率 |
| 数据导入 | 上传或粘贴历史事件数据，创建导入批次 |
| 导入审核 | 查看 staging 行、错误原因、修正、拒绝、确认入库 |
| 事件库管理 | 搜索、筛选、编辑、归档、标记争议 |
| 来源管理 | 补充和核验 citation、excerpt、URL、source type、reliability |
| 关系管理 | 维护事件之间的同期、因果、影响和不确定关系 |
| 知识库管理 | 导入文档、查看 chunk、停用文档、测试召回 |
| 向量管理 | 查看 embedding 覆盖率、重算向量、检查索引状态、测试语义检索 |

## 管理后台前端计划表

| 批次 | 优先级 | 页面 / 能力 | 路由建议 | 目标 | 状态 |
|---|---:|---|---|---|---|
| F1 | 1 | 管理后台壳子和导航 | `/admin` | 后台信息架构、侧边导航、概览指标、聊天页入口 | 已完成 |
| F1 | 2 | 管理 API client 和类型 | `apps/web/src/adminApi.ts` | 集中封装管理接口，统一 loading/error/empty 状态 | 已完成 |
| F2 | 3 | 数据导入工作台 | `/admin/imports/new` | 粘贴 JSON/CSV，解析预览，创建导入批次 | 已完成 |
| F2 | 4 | 导入批次列表和审核详情 | `/admin/imports`、`/admin/imports/:batchId` | 查看批次、staging、错误、重复候选和差异 | 已完成 |
| F2 | 5 | staging 修正、合并和确认 | `/admin/imports/:batchId` | 修正错误行、重校验、处理重复、确认或拒绝入库 | 已完成 |
| F3 | 6 | 事件库列表和筛选 | `/admin/events` | 关键词、年份、地区、状态、最低置信度、有无来源筛选和批量归档 | 已完成 |
| F3 | 7 | 后台事件详情编辑 | `/admin/events/:eventId` | 表单编辑事件字段，查看来源、关系、审计、导入批次、向量状态 | 已完成 |
| F3 | 8 | 来源和关系维护 | `/admin/events/:eventId`、`/admin/relations` | 来源新增/编辑/删除/核验，关系新增/编辑/删除 | 已完成 |
| F4 | 9 | 数据质量修复台 | `/admin/quality` | 数据质量 summary、问题列表、跳转修复 | 已完成 |
| F4 | 10 | 知识库管理 | `/admin/knowledge`、`/admin/knowledge/:documentId` | 文档列表、chunk 查看、元数据更新、停用/归档、reembed | 已完成 |
| F4 | 11 | 向量管理 | `/admin/vectors` | embedding 覆盖率、重建任务创建/处理、任务状态 | 已完成 |
| F5 | 12 | 前端结构化和视觉 QA | 全局 | 拆分 `AdminPages.tsx` 和 `adminApi.ts`，完成构建验证 | 已完成第一版 |

## 已导入的小批量种子数据

| 批次 | 文件 | 数量 | 年份范围 | 状态 | 说明 |
|---|---|---:|---|---|---|
| `3ab3c564-d324-4b35-ac30-5b5fe82d0a11` | `data/imports/curated_seed_600_900.json` | 12 | 633-883 | 已导入，事件为 `reviewing` | 覆盖中东、东亚、西欧、东地中海、南亚、东欧；用于验证后台导入和横向对照 |

导入事件包括：雅尔穆克战役、伊斯兰征服萨珊波斯、大化改新、白江口之战、倭马亚征服西班牙、第二次阿拉伯围攻君士坦丁堡、帕拉王朝兴起、平安京迁都、凡尔登条约、保加利亚基督教化、维京大军入侵英格兰、赞吉起义爆发。

## 当前工作计划表

| 批次 | 优先级 | 工作项 | 验收标准 | 状态 |
|---|---:|---|---|---|
| W1 | 1 | 小批量种子数据核验支撑 | 已补按 `import_batch_id` 定位种子数据、`duplicate_title` 同标题候选检测、`GET /admin/import-batches/{batch_id}/review` 和导入详情核验面板 | 已完成 |
| W2 | 2 | 数据库初始化脚本同步 | `init.sql` 覆盖当前后端依赖；新增 schema 文件测试；当前本地库同步新增索引 | 已完成 |
| W3 | 3 | 管理后台体验修复 | 根据实际核验结果修复表单、错误提示、重复候选提示、空状态和移动端问题 | 进行中 |
| W4 | 4 | 数据导入演练扩展 | 扩展到 20-50 条事件，新增批次可导入、审核、确认和质量修复 | 待开始 |
| W5 | 5 | Agent 返回结构标准化 | 后端稳定输出 `answer`、`events`、`references`、`links`，前端不再递归解析 observation | 待开始 |
| W6 | 6 | RAG 引用注入回答 | 回答能展示事件来源和知识文档 chunk 引用 | 待开始 |
| W7 | 7 | Langfuse 集成预留 | run_id 可对应到 Langfuse trace，本系统不自研 Trace 后台 | 待开始 |

## 后端重构工作表

| 批次 | 优先级 | 重构项 | 验收标准 | 状态 |
|---|---:|---|---|---|
| R1 | 1 | 统一向量任务表 schema 兜底 | 运行时建表和正式 schema 约束一致，schema 文件测试覆盖 | 已完成 |
| R2 | 2 | 拆分 FastAPI 路由 | 已拆出 agent、events、imports、admin、knowledge/vector routers；路径不变，现有 API 测试全过 | 已完成 |
| R3 | 3 | 拆分管理服务 | 已拆出事件主体、数据质量、来源、关系、总览、批次核验和公共审计服务 | 已完成 |
| R4 | 4 | 抽公共历史实体 upsert | 已新增 `HistoricalEntityResolver`，导入确认和后台编辑共用地区/国家/政权/分类 upsert | 已完成 |
| R5 | 5 | 写接口 Pydantic 化 | admin、imports、knowledge/vector 写接口已有 Pydantic request/response models，OpenAPI schema 测试覆盖 | 已完成 |
| R6 | 6 | 清理轻微代码味道 | 已清理重复 payload 转换、分页 clamp 和管理审计/JSON safe helper | 已完成 |

## 管理后台优先补的后端接口

| 优先级 | API | 目标 |
|---:|---|---|
| 1 | `GET /admin/data-quality/summary` | 已完成；提供无来源、低置信、疑似重复、时间异常、关系缺证据等计数 |
| 2 | `GET /admin/data-quality/issues` | 已完成；按问题类型分页查看可修复的数据问题 |
| 3 | `GET /admin/dictionaries` | 已完成；返回地区、政权、分类、状态和枚举选项 |
| 4 | `GET /admin/events/{event_id}` | 已完成；后台事件详情聚合，返回事件、来源、关系、审计、导入批次和向量状态 |
| 5 | `POST /admin/events/bulk-update` | 已完成；批量更新事件状态、置信度、分类或归档 |
| 6 | `POST /imports/staging/bulk-revalidate` | 已完成；批量重新校验 staging 行 |
| 7 | `POST /admin/sources/bulk-verify` | 已完成；批量核验来源可靠度 |
| 8 | `POST /imports/staging/{row_id}/merge` | 已完成；对重复导入行执行保留、替换或合并策略 |
| 9 | `POST /imports/parse` | 已完成；将 JSON/CSV 输入解析为标准 events payload |

## 交给 Langfuse，不需要我们开发

| 功能 | 处理方式 |
|---|---|
| Agent 运行详情页 | 使用 Langfuse trace |
| 工具调用步骤分析 | 使用 Langfuse spans / observations |
| token、耗时、成本统计看板 | 使用 Langfuse 成本和指标能力 |
| 运行错误分析 | 使用 Langfuse trace 筛选和错误聚合 |
| Prompt 版本观测 | 使用 Langfuse 关联 prompt 和运行结果 |
| 评测中心 UI | 使用 Langfuse datasets/evals |
| Agent run 搜索与筛选 | 使用 Langfuse 搜索能力 |

## 暂缓

1. 多智能体。
2. 自动爬虫导入。
3. 复杂知识图谱。
4. 用户系统和多租户。
5. MCP 接入。
6. 地图视图。
7. 自研 Agent Trace / 成本 / 评测分析后台。

## 第一版判断标准

当系统能稳定回答下面四类问题时，MVP 就算跑通：

1. “755 年各地区发生了什么？”
2. “600-650 年东亚和中东有什么重大变化？”
3. “怛罗斯之战和唐朝、阿拉伯帝国有什么关系？”
4. “生成 700-800 年欧亚历史对照表。”
