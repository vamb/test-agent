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

        if self._asks_for_source_revision(user_input, tools):
            return self._decide_source_revision(user_input, messages, called_tools)

        if self._asks_for_event_revision(user_input, tools):
            return self._decide_event_revision(user_input, messages, called_tools)

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

    def _decide_event_revision(
        self,
        user_input: str,
        messages: list[dict[str, Any]],
        called_tools: list[str],
    ) -> ModelDecision:
        if "resolve_event" not in called_tools:
            return ModelDecision(
                action="call_tool",
                reason="Resolve the event phrase before drafting an event revision.",
                tool_call=ToolCall("resolve_event", {"query": user_input}),
            )

        resolved = self._last_tool_result(messages, "resolve_event")
        event = resolved.get("event", {})
        event_id = event.get("id")
        if not resolved.get("found") or not event_id:
            return ModelDecision(
                action="finish",
                reason="Event resolution failed.",
                answer="当前数据集中没有找到要修订的事件，请先提供事件名称或事件 ID。",
            )

        if "draft_event_revision" not in called_tools:
            updates = self._infer_revision_updates(user_input)
            if not updates:
                return ModelDecision(
                    action="finish",
                    reason="Revision intent was found, but no supported field update was explicit.",
                    answer="我找到了修订意图，但还缺少明确字段。请说明要修改 summary、title、confidence、source_status 或 notes 中的哪一项。",
                )
            return ModelDecision(
                action="call_tool",
                reason="Draft a non-mutating event revision before requesting confirmation.",
                tool_call=ToolCall(
                    "draft_event_revision",
                    {
                        "event_id": str(event_id),
                        "updates": updates,
                        "reason": user_input,
                        "confirmed_by": "agent",
                    },
                ),
            )

        if "apply_event_revision" not in called_tools:
            draft = self._last_tool_result(messages, "draft_event_revision")
            if not draft.get("success"):
                return ModelDecision(
                    action="finish",
                    reason="Revision draft failed.",
                    answer=f"事件修订草案生成失败：{draft.get('error', 'unknown error')}",
                )
            next_step = draft.get("next_step", {})
            arguments = dict(next_step.get("arguments") or {})
            return ModelDecision(
                action="call_tool",
                reason="Request human confirmation before applying the drafted event revision.",
                tool_call=ToolCall("apply_event_revision", arguments),
            )

        applied = self._last_tool_result(messages, "apply_event_revision")
        if not applied.get("success"):
            return ModelDecision(
                action="finish",
                reason="Confirmed revision failed.",
                answer=f"事件修订未完成：{applied.get('error', 'unknown error')}",
            )
        return ModelDecision(
            action="finish",
            reason="Confirmed revision was applied.",
            answer=self._format_event_revision_result(applied),
        )

    def _decide_source_revision(
        self,
        user_input: str,
        messages: list[dict[str, Any]],
        called_tools: list[str],
    ) -> ModelDecision:
        if "resolve_event" not in called_tools:
            return ModelDecision(
                action="call_tool",
                reason="Resolve the event phrase before drafting a source revision.",
                tool_call=ToolCall("resolve_event", {"query": user_input}),
            )

        resolved = self._last_tool_result(messages, "resolve_event")
        event = resolved.get("event", {})
        event_id = event.get("id")
        if not resolved.get("found") or not event_id:
            return ModelDecision(
                action="finish",
                reason="Event resolution failed.",
                answer="当前数据集中没有找到要核验来源的事件，请先提供事件名称或事件 ID。",
            )

        if "draft_source_revision" not in called_tools:
            updates = self._infer_source_revision_updates(user_input)
            if not updates:
                return ModelDecision(
                    action="finish",
                    reason="Source revision intent was found, but no supported field update was explicit.",
                    answer="我找到了来源核验意图，但还缺少明确字段。请说明要调整 reliability、is_primary、citation、excerpt 或 page_ref 中的哪一项。",
                )
            return ModelDecision(
                action="call_tool",
                reason="Draft a non-mutating source revision before requesting confirmation.",
                tool_call=ToolCall(
                    "draft_source_revision",
                    {
                        "event_id": str(event_id),
                        "source_query": self._infer_source_query(user_input),
                        "updates": updates,
                        "reason": user_input,
                        "confirmed_by": "agent",
                    },
                ),
            )

        if "apply_source_revision" not in called_tools:
            draft = self._last_tool_result(messages, "draft_source_revision")
            if not draft.get("success"):
                return ModelDecision(
                    action="finish",
                    reason="Source revision draft failed.",
                    answer=f"来源核验草案生成失败：{draft.get('error', 'unknown error')}",
                )
            next_step = draft.get("next_step", {})
            return ModelDecision(
                action="call_tool",
                reason="Request human confirmation before applying the drafted source revision.",
                tool_call=ToolCall("apply_source_revision", dict(next_step.get("arguments") or {})),
            )

        applied = self._last_tool_result(messages, "apply_source_revision")
        if not applied.get("success"):
            return ModelDecision(
                action="finish",
                reason="Confirmed source revision failed.",
                answer=f"来源核验未完成：{applied.get('error', 'unknown error')}",
            )
        return ModelDecision(
            action="finish",
            reason="Confirmed source revision was applied.",
            answer=self._format_source_revision_result(applied),
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

    def _asks_for_event_revision(self, text: str, tools: list[dict[str, Any]]) -> bool:
        if not any(tool.get("name") == "draft_event_revision" for tool in tools):
            return False
        keywords = ["修订", "修改", "更新", "改成", "改为", "设为", "纠正", "更正", "编辑"]
        return any(keyword in text for keyword in keywords)

    def _asks_for_source_revision(self, text: str, tools: list[dict[str, Any]]) -> bool:
        if not any(tool.get("name") == "draft_source_revision" for tool in tools):
            return False
        source_keywords = ["来源", "引用", "citation", "出处", "可靠度", "可信度", "主来源", "source"]
        action_keywords = ["核验", "修订", "修改", "更新", "改成", "改为", "设为", "纠正", "更正", "标记"]
        lowered = text.lower()
        return any(keyword in lowered for keyword in source_keywords) and any(
            keyword in text for keyword in action_keywords
        )

    def _infer_revision_updates(self, text: str) -> dict[str, Any]:
        updates: dict[str, Any] = {}
        confidence_match = re.search(r"(?:confidence|置信度|可信度)[^\d]*(0(?:\.\d+)?|1(?:\.0+)?)", text, re.I)
        if confidence_match:
            updates["confidence"] = float(confidence_match.group(1))

        status_keywords = {
            "verified": ["verified", "已核验", "已验证", "核验通过"],
            "reviewing": ["reviewing", "待审核", "审核中"],
            "disputed": ["disputed", "有争议", "争议"],
            "archived": ["archived", "归档"],
            "draft": ["draft", "草稿"],
        }
        for status, keywords in status_keywords.items():
            if any(keyword in text for keyword in keywords):
                updates["source_status"] = status
                break

        field_patterns = {
            "title": ["title", "标题", "名称"],
            "summary": ["summary", "摘要", "简介", "概述", "说明"],
            "notes": ["notes", "备注", "注释"],
        }
        value_match = re.search(r"(?:改成|改为|更新为|设为|更正为)[:：\"'“”\s]*(.+)$", text)
        value = value_match.group(1).strip(" ：:\"'“”") if value_match else ""
        if value:
            for field, keywords in field_patterns.items():
                if any(keyword in text for keyword in keywords):
                    updates[field] = value
                    break
            if not any(field in updates for field in field_patterns):
                updates["summary"] = value

        return updates

    def _format_event_revision_result(self, observation: dict) -> str:
        event = observation.get("event", {})
        title = event.get("title") or observation.get("event_title") or observation.get("event_id")
        diff = observation.get("diff", [])
        lines = [f"事件《{title}》已按确认内容完成修订，并写入审计日志。"]
        for item in diff:
            lines.append(f"- {item.get('field')}: {item.get('before')} -> {item.get('after')}")
        return "\n".join(lines)

    def _infer_source_revision_updates(self, text: str) -> dict[str, Any]:
        updates: dict[str, Any] = {}
        reliability_match = re.search(r"(?:reliability|可靠度|可信度)[^\d]*(0(?:\.\d+)?|1(?:\.0+)?)", text, re.I)
        if reliability_match:
            updates["reliability"] = float(reliability_match.group(1))
        if any(keyword in text for keyword in ["主来源", "主要来源", "primary"]):
            updates["is_primary"] = True

        value_match = re.search(r"(?:改成|改为|更新为|设为|更正为)[:：\"'“”\s]*(.+)$", text)
        value = value_match.group(1).strip(" ：:\"'“”") if value_match else ""
        if value:
            field_keywords = {
                "citation": ["citation", "引用", "出处", "引文"],
                "excerpt": ["excerpt", "摘录", "原文"],
                "page_ref": ["page_ref", "页码", "页"],
                "source_title": ["来源标题", "资料名", "来源名称"],
                "url": ["url", "链接"],
            }
            for field, keywords in field_keywords.items():
                if any(keyword in text for keyword in keywords):
                    updates[field] = value
                    break
        return updates

    def _infer_source_query(self, text: str) -> str:
        match = re.search(r"(?:来源|引用|出处|source)[:：\"'“”\s]*([^，。；;]+)", text, re.I)
        return match.group(1).strip(" ：:\"'“”") if match else ""

    def _format_source_revision_result(self, observation: dict) -> str:
        source = observation.get("source", {})
        title = source.get("source_title") or observation.get("source_title") or observation.get("source_id")
        diff = observation.get("diff", [])
        lines = [f"来源《{title}》已按确认内容完成核验/修订，并写入审计日志。"]
        for item in diff:
            lines.append(f"- {item.get('field')}: {item.get('before')} -> {item.get('after')}")
        return "\n".join(lines)

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
