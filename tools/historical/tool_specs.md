# 历史查询工具规格

## 工具设计原则

第一版工具全部只读。Agent 可以查询、比较、生成对照表，但不能自动导入、修改、删除历史事件。

## search_events_by_year

按年份检索历史事件。

```json
{
  "name": "search_events_by_year",
  "description": "Search historical events that overlap with a given year.",
  "input_schema": {
    "type": "object",
    "properties": {
      "year": { "type": "integer" },
      "regions": { "type": "array", "items": { "type": "string" } },
      "polities": { "type": "array", "items": { "type": "string" } },
      "categories": { "type": "array", "items": { "type": "string" } },
      "limit": { "type": "integer", "default": 50 }
    },
    "required": ["year"]
  },
  "risk_level": "low",
  "requires_confirmation": false
}
```

## search_events_by_range

按时间段检索历史事件。

```json
{
  "name": "search_events_by_range",
  "description": "Search historical events that overlap with a year range.",
  "input_schema": {
    "type": "object",
    "properties": {
      "start_year": { "type": "integer" },
      "end_year": { "type": "integer" },
      "regions": { "type": "array", "items": { "type": "string" } },
      "polities": { "type": "array", "items": { "type": "string" } },
      "categories": { "type": "array", "items": { "type": "string" } },
      "limit": { "type": "integer", "default": 100 }
    },
    "required": ["start_year", "end_year"]
  },
  "risk_level": "low",
  "requires_confirmation": false
}
```

## get_event_detail

获取事件详情、来源和已知关系。

```json
{
  "name": "get_event_detail",
  "description": "Get one historical event with sources and relations.",
  "input_schema": {
    "type": "object",
    "properties": {
      "event_id": { "type": "string" }
    },
    "required": ["event_id"]
  },
  "risk_level": "low",
  "requires_confirmation": false
}
```

## compare_regions

比较多个地区在某个时间范围内的历史事件。

```json
{
  "name": "compare_regions",
  "description": "Compare historical events across regions in a given year range.",
  "input_schema": {
    "type": "object",
    "properties": {
      "start_year": { "type": "integer" },
      "end_year": { "type": "integer" },
      "regions": { "type": "array", "items": { "type": "string" } },
      "categories": { "type": "array", "items": { "type": "string" } }
    },
    "required": ["start_year", "end_year", "regions"]
  },
  "risk_level": "low",
  "requires_confirmation": false
}
```

## find_related_events

查找可能有关联的事件。工具只返回候选关系和证据，最终解释由 Agent 输出，并必须说明证据强弱。

```json
{
  "name": "find_related_events",
  "description": "Find known or possible relations between historical events.",
  "input_schema": {
    "type": "object",
    "properties": {
      "event_id": { "type": "string" },
      "relation_types": { "type": "array", "items": { "type": "string" } },
      "limit": { "type": "integer", "default": 20 }
    },
    "required": ["event_id"]
  },
  "risk_level": "low",
  "requires_confirmation": false
}
```

