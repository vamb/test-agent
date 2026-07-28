# 历史时间对照 Agent

这是一个用于横向比较不同国家、地区和文明在同一时间点或时间段内历史事件的 Agent 项目。

## 当前目标

第一版先完成一个单智能体 MVP：

- 支持按年份查询同期历史事件
- 支持按时间段生成多地区对照表
- 支持查看事件详情、原因、影响和来源
- 支持查找某事件的同期事件
- 支持初步关联分析，但必须区分事实、推断和争议
- 保留 Agent 执行记录，方便后续评测和排查

## 技术依据

- `AI智能体开发大纲工作.pdf`：Agent 技术栈总纲
- `AI智能体开发计划表.md`：12 周开发计划
- `docs/`：历史时间对照 Agent 的业务和技术设计

## MVP 数据范围

- 时间范围：公元 600-900 年
- 地区范围：中国、阿拉伯帝国、拜占庭、法兰克王国、印度、日本、中亚
- 首批数据：200-500 条结构化历史事件

## 目录结构

```text
apps/                 前端、API、Worker
agent/                Agent Runtime、Prompt、模型适配、上下文、策略、工作流
tools/                工具注册表和历史查询工具
knowledge/            文档加载、切分、检索、重排
evaluation/           评测数据集、评分器、回归测试
infrastructure/       数据库、队列、观测、Docker
data/                 样例数据和导入数据
docs/                 产品和技术文档
tests/                自动化测试
```

## 第一阶段开发顺序

1. 完成历史事件数据表和样例数据导入。
2. 实现 FastAPI 查询接口。
3. 实现只读历史查询工具。
4. 实现手写 Agent Loop。
5. 实现 React 查询界面和对照表。
6. 接入执行日志和基础评测集。

## 模型配置

默认使用本地确定性适配器，方便离线开发和评测：

```powershell
$env:MODEL_PROVIDER="rule_based"
```

如需切到 OpenAI Function Calling：

```powershell
$env:MODEL_PROVIDER="openai"
$env:OPENAI_API_KEY="你的 key"
$env:OPENAI_MODEL="gpt-4.1-mini"
```

切换后 `/agent/query` 会继续使用同一套 Agent Loop 和 ToolRegistry，只是由模型通过 Function Calling 选择工具。
