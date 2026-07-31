# Web 前端

历史时间对照 Agent 的 React + TypeScript + Vite 工作台界面。

完整产品使用说明见：`docs/user_manual.md`。

## 功能

- Agent 问答输入
- `/agent/query/stream` SSE 步骤流展示
- 年份/时间段/地区横向对照表
- 事件详情、来源、原因和影响展示

## 启动

```bash
npm install
npm run dev
```

默认访问：

```text
http://127.0.0.1:5174
```

默认 API 地址：

```text
http://127.0.0.1:19000
```

可用环境变量覆盖：

```bash
VITE_API_BASE_URL=http://127.0.0.1:19000
```

## 构建验证

```bash
npm run build
```
