from __future__ import annotations

import re
from typing import Any

from agent.models.base import ModelDecision, ToolCall


class RuleBasedModelAdapter:
    """Deterministic adapter that mimics model decisions for local MVP validation."""

    model_name = "rule-based-model-adapter"

    def decide(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> ModelDecision:
        user_input = self._user_input(messages)
        called_tools = [message["name"] for message in messages if message.get("role") == "tool"]
        years = [int(item) for item in re.findall(r"-?\d{3,4}", user_input)]

        if self._asks_for_confirmation_probe(user_input, tools):
            if "confirmation_probe" not in called_tools:
                return ModelDecision(
                    action="call_tool",
                    reason="The user requested a local confirmation flow probe.",
                    tool_call=ToolCall(
                        "confirmation_probe",
                        {"target": "chat-confirmation-e2e"},
                    ),
                )
            return ModelDecision(
                action="finish",
                reason="Confirmation probe completed.",
                answer=self._format_confirmation_probe_result(
                    self._last_tool_result(messages, "confirmation_probe"),
                ),
            )

        if self._asks_for_relation(user_input):
            return self._decide_relation(user_input, years, messages, called_tools, tools)

        if len(years) >= 2:
            return self._decide_range(user_input, years, messages, called_tools, tools)

        if years:
            if "search_events_by_year" not in called_tools:
                return ModelDecision(
                    action="call_tool",
                    reason="The user asks about one time point, so query events around that year.",
                    tool_call=ToolCall(
                        "search_events_by_year",
                        {
                            "year": years[0],
                            "regions": self._infer_regions(user_input) or None,
                            "nearby_window": 10
                            if self._asks_for_contemporary_context(user_input)
                            else 0,
                        },
                    ),
                )
            if self._should_search_knowledge(tools, called_tools):
                return self._knowledge_search_decision(user_input)
            return ModelDecision(
                action="finish",
                reason="Year search completed.",
                answer=self._format_year_result(
                    self._last_tool_result(messages, "search_events_by_year"),
                    self._last_tool_result(messages, "search_knowledge"),
                ),
            )

        if "search_events_by_range" not in called_tools:
            return ModelDecision(
                action="call_tool",
                reason="No explicit year found, so provide the MVP sample range.",
                tool_call=ToolCall(
                    "search_events_by_range",
                    {"start_year": 600, "end_year": 900, "regions": None},
                ),
            )
        if self._should_search_knowledge(tools, called_tools):
            return self._knowledge_search_decision(user_input)
        return ModelDecision(
            action="finish",
            reason="Default range search completed.",
            answer=self._format_range_result(
                self._last_tool_result(messages, "search_events_by_range"),
                self._last_tool_result(messages, "search_knowledge"),
            ),
        )

    def _decide_relation(
        self,
        user_input: str,
        years: list[int],
        messages: list[dict[str, Any]],
        called_tools: list[str],
        tools: list[dict[str, Any]],
    ) -> ModelDecision:
        if "resolve_event" not in called_tools:
            return ModelDecision(
                action="call_tool",
                reason="Resolve the event phrase before relation analysis.",
                tool_call=ToolCall("resolve_event", {"query": user_input}),
            )

        resolved = self._last_tool_result(messages, "resolve_event")
        event = resolved.get("event", {})
        event_id = event.get("id")
        if not resolved.get("found") or not event_id:
            return ModelDecision(
                action="finish",
                reason="Event resolution failed.",
                answer="当前数据集中没有找到该事件，无法分析关系。",
            )

        if "get_event_detail" not in called_tools:
            return ModelDecision(
                action="call_tool",
                reason="Get event details before explaining relations.",
                tool_call=ToolCall("get_event_detail", {"event_id": event_id}),
            )

        if "search_events_by_year" not in called_tools:
            year = years[0] if years else int(event["start_year"])
            return ModelDecision(
                action="call_tool",
                reason="Collect same-period context for relation explanation.",
                tool_call=ToolCall(
                    "search_events_by_year",
                    {
                        "year": year,
                        "regions": self._infer_regions(user_input) or None,
                        "nearby_window": 10,
                    },
                ),
            )

        if "find_related_events" not in called_tools:
            return ModelDecision(
                action="call_tool",
                reason="Query curated relation records.",
                tool_call=ToolCall("find_related_events", {"event_id": event_id}),
            )

        if self._should_search_knowledge(tools, called_tools):
            return self._knowledge_search_decision(user_input)

        return ModelDecision(
            action="finish",
            reason="Relation context and relation records are available.",
            answer=self._format_relation_result(
                self._last_tool_result(messages, "get_event_detail"),
                self._last_tool_result(messages, "find_related_events"),
                self._last_tool_result(messages, "search_knowledge"),
            ),
        )

    def _decide_range(
        self,
        user_input: str,
        years: list[int],
        messages: list[dict[str, Any]],
        called_tools: list[str],
        tools: list[dict[str, Any]],
    ) -> ModelDecision:
        start_year, end_year = min(years[0], years[1]), max(years[0], years[1])
        regions = self._infer_regions(user_input)
        if not regions and self._asks_for_eurasian_context(user_input):
            regions = ["东亚", "中东", "中亚", "西欧"]

        if "search_events_by_range" not in called_tools:
            return ModelDecision(
                action="call_tool",
                reason="The user asks for a range, so first collect range events.",
                tool_call=ToolCall(
                    "search_events_by_range",
                    {
                        "start_year": start_year,
                        "end_year": end_year,
                        "regions": regions or None,
                    },
                ),
            )

        if "compare_regions" not in called_tools:
            return ModelDecision(
                action="call_tool",
                reason="A comparison request needs grouped regional rows.",
                tool_call=ToolCall(
                    "compare_regions",
                    {
                        "start_year": start_year,
                        "end_year": end_year,
                        "regions": regions or ["东亚", "中东", "中亚", "西欧"],
                    },
                ),
            )

        if self._should_search_knowledge(tools, called_tools):
            return self._knowledge_search_decision(user_input)

        return ModelDecision(
            action="finish",
            reason="Regional comparison completed.",
            answer=self._format_comparison(
                self._last_tool_result(messages, "compare_regions"),
                self._last_tool_result(messages, "search_knowledge"),
            ),
        )

    def _user_input(self, messages: list[dict[str, Any]]) -> str:
        for message in messages:
            if message.get("role") == "user":
                return str(message.get("content", ""))
        return ""

    def _last_tool_result(self, messages: list[dict[str, Any]], tool_name: str) -> dict:
        for message in reversed(messages):
            if message.get("role") == "tool" and message.get("name") == tool_name:
                return dict(message.get("content", {}))
        return {}

    def _should_search_knowledge(self, tools: list[dict[str, Any]], called_tools: list[str]) -> bool:
        return "search_knowledge" not in called_tools and any(
            tool.get("name") == "search_knowledge" for tool in tools
        )

    def _knowledge_search_decision(self, user_input: str) -> ModelDecision:
        return ModelDecision(
            action="call_tool",
            reason="Retrieve knowledge chunks to cite source-backed context before final answer.",
            tool_call=ToolCall("search_knowledge", {"query": user_input, "limit": 3}),
        )

    def _infer_regions(self, text: str) -> list[str]:
        region_keywords = {
            "东亚": ["东亚", "中国", "日本", "唐朝", "隋朝"],
            "中东": ["中东", "阿拉伯", "伊斯兰", "阿拔斯"],
            "中亚": ["中亚", "怛罗斯"],
            "西欧": ["西欧", "欧洲", "法兰克", "查理曼"],
        }
        regions: list[str] = []
        for region, keywords in region_keywords.items():
            if any(keyword in text for keyword in keywords):
                regions.append(region)
        return regions

    def _asks_for_contemporary_context(self, text: str) -> bool:
        keywords = ["同时", "同期", "同一时期", "发生时", "背景", "横向"]
        return any(keyword in text for keyword in keywords) or ("发生" in text and "时" in text)

    def _asks_for_eurasian_context(self, text: str) -> bool:
        keywords = ["欧亚", "世界", "各地区", "各国", "对照表", "横向", "比较", "对比"]
        return any(keyword in text for keyword in keywords)

    def _asks_for_relation(self, text: str) -> bool:
        keywords = ["关系", "关联", "影响", "因果", "有关"]
        return any(keyword in text for keyword in keywords)

    def _asks_for_confirmation_probe(self, text: str, tools: list[dict[str, Any]]) -> bool:
        if not any(tool.get("name") == "confirmation_probe" for tool in tools):
            return False
        keywords = ["确认联调", "确认恢复联调", "人工确认联调", "confirmation probe"]
        return any(keyword in text.lower() for keyword in keywords)

    def _format_year_result(self, observation: dict, knowledge: dict | None = None) -> str:
        events = observation.get("events", [])
        if not events:
            return f"当前数据集中没有找到 {observation.get('year')} 年的相关事件。"

        if observation.get("nearby_window", 0):
            lines = [
                f"{observation['year']} 年前后 {observation['nearby_window']} 年历史事件对照："
            ]
        else:
            lines = [f"{observation['year']} 年历史事件对照："]
        for event in events:
            lines.append(
                f"- {event['region']} / {event['polity']}：{event['title']}。{event['summary']}"
            )
        lines.append("说明：以上为同期事件；请区分同期与因果，是否存在因果关系需要进一步查看来源和事件关系。")
        self._append_knowledge_references(lines, knowledge)
        return "\n".join(lines)

    def _format_range_result(self, observation: dict, knowledge: dict | None = None) -> str:
        events = observation.get("events", [])
        if not events:
            return (
                f"当前数据集中没有找到 {observation.get('start_year')}-"
                f"{observation.get('end_year')} 年的相关事件。"
            )

        lines = [f"{observation['start_year']}-{observation['end_year']} 年历史事件："]
        for event in events:
            lines.append(
                f"- {event['start_year']}-{event.get('end_year') or event['start_year']} "
                f"{event['region']} / {event['polity']}：{event['title']}"
            )
        self._append_knowledge_references(lines, knowledge)
        return "\n".join(lines)

    def _format_comparison(self, observation: dict, knowledge: dict | None = None) -> str:
        rows = observation.get("rows", [])
        if not rows:
            return (
                f"当前数据集中没有找到 {observation.get('start_year')}-"
                f"{observation.get('end_year')} 年的对照事件。"
            )

        lines = [f"{observation['start_year']}-{observation['end_year']} 年中国与欧亚地区横向对照表："]
        for row in rows:
            title_list = "；".join(event["title"] for event in row["events"]) or "暂无样例事件"
            lines.append(f"- {row['region']}：{title_list}")
        lines.append("分析提示：横向对照先展示同一时期背景，因果或影响关系需要单独验证。")
        self._append_knowledge_references(lines, knowledge)
        return "\n".join(lines)

    def _format_relation_result(self, detail: dict, relations: dict, knowledge: dict | None = None) -> str:
        if not detail.get("found"):
            return "当前数据集中没有找到该事件，无法分析关系。"

        event = detail["event"]
        lines = [
            f"{event['title']}关系分析：",
            f"- 事件背景：{event['summary']}",
        ]
        relation_items = relations.get("relations", [])
        if not relation_items:
            lines.append("- 已知关系：当前数据库没有记录明确关系。")
        else:
            lines.append("- 已知关系：")
            for relation in relation_items:
                other_title = (
                    relation["target_title"]
                    if relation["source_event_id"] == event["id"]
                    else relation["source_title"]
                )
                lines.append(
                    f"  - {relation['relation_type']} / {other_title}："
                    f"{relation['explanation']} 证据强弱：{relation['confidence']}"
                )
        lines.append("说明：同期不等于因果；关系分析需要看 relation_type、confidence 和来源证据。")
        self._append_knowledge_references(lines, knowledge)
        return "\n".join(lines)

    def _append_knowledge_references(self, lines: list[str], knowledge: dict | None) -> None:
        results = (knowledge or {}).get("results", [])
        if not results:
            return
        lines.append("参考资料：")
        for item in results[:3]:
            citation = item.get("citation") or item.get("title") or "知识库资料"
            content = str(item.get("content", "")).strip().replace("\n", " ")
            excerpt = content[:80]
            lines.append(f"- {citation}：{excerpt}")

    def _format_confirmation_probe_result(self, observation: dict) -> str:
        if observation.get("success"):
            return (
                "确认恢复链路联调已完成：前端确认按钮触发后，后端已带 "
                "`confirmed: true` 恢复执行确认探针。"
            )
        return "确认恢复链路联调未完成，请查看工具返回。"
