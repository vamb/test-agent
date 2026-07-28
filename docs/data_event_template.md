# 历史事件数据模板

## JSON 模板

```json
{
  "title": "安史之乱爆发",
  "start_year": 755,
  "end_year": 763,
  "start_date_text": "755年",
  "end_date_text": "763年",
  "time_precision": "year",
  "region": "东亚",
  "polity": "唐朝",
  "modern_country": "中国",
  "category": ["战争", "政治"],
  "summary": "唐朝中期由安禄山、史思明等发动的大规模叛乱，是唐朝由盛转衰的重要事件。",
  "causes": ["藩镇势力扩张", "边镇将领权力过大", "中央政治腐败"],
  "effects": ["唐朝国力衰退", "藩镇割据加重", "人口和财政受到严重冲击"],
  "actors": ["安禄山", "史思明", "唐玄宗", "唐肃宗"],
  "source_status": "draft",
  "confidence": 0.9,
  "sources": [
    {
      "source_title": "旧唐书",
      "source_type": "book",
      "url": "",
      "citation": "旧唐书相关本纪与列传",
      "excerpt": "",
      "reliability": 0.8
    }
  ],
  "relations": []
}
```

## CSV 字段

```csv
title,start_year,end_year,start_date_text,end_date_text,time_precision,region,polity,modern_country,category,summary,causes,effects,actors,source_status,confidence,sources
```

## 字段规范

| 字段 | 必填 | 说明 |
|---|---|---|
| title | 是 | 简短事件名称 |
| start_year | 是 | 开始年份，公元前用负数 |
| end_year | 否 | 结束年份，单年事件可等于 start_year |
| time_precision | 是 | year、month、day、range、approximate |
| region | 是 | 大区，不等同于现代国家 |
| polity | 是 | 当时的政权、国家、文明或组织 |
| modern_country | 否 | 现代国家映射，仅用于筛选辅助 |
| category | 是 | 可多选：政治、战争、宗教、经济、贸易、科技、文化、灾害 |
| summary | 是 | 100-300 字摘要 |
| causes | 否 | 原因列表 |
| effects | 否 | 影响列表 |
| actors | 否 | 人物、政权、组织 |
| source_status | 是 | draft、verified、disputed |
| confidence | 是 | 0-1 之间 |
| sources | 是 | 至少 1 个来源，MVP 样例可先 draft |

## 数据原则

1. 古代事件优先使用当时政权或文明名称，不强行套现代国家。
2. 时间不确定时保留原始时间文本，并把 time_precision 标为 approximate。
3. 有争议的事件不要删除争议，而是标记 disputed。
4. 同期不等于因果，关系必须单独记录证据。
5. 每条核心事件都应能追溯来源。

