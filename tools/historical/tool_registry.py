from __future__ import annotations

from typing import Any

from knowledge.service import KnowledgeService
from tools.historical.event_management import EventManagementService
from tools.historical.event_revision import EventRevisionToolService
from tools.historical.service import HistoricalQueryService
from tools.historical.source_revision import SourceRevisionToolService
from tools.registry.base import ToolDefinition, ToolRegistry


def build_historical_tool_registry(
    service: HistoricalQueryService,
    knowledge_service: KnowledgeService | None = None,
    event_management_service: EventManagementService | None = None,
    admin_token: str = "",
    enable_confirmation_probe: bool = False,
) -> ToolRegistry:
    registry = ToolRegistry()

    registry.register(
        ToolDefinition(
            name="search_events_by_year",
            description="Search historical events in one year, optionally with a nearby window.",
            input_schema={
                "type": "object",
                "properties": {
                    "year": {"type": "integer"},
                    "regions": {"type": ["array", "null"], "items": {"type": "string"}},
                    "polities": {"type": ["array", "null"], "items": {"type": "string"}},
                    "categories": {"type": ["array", "null"], "items": {"type": "string"}},
                    "limit": {"type": "integer", "default": 50},
                    "nearby_window": {"type": "integer", "default": 0},
                },
                "required": ["year"],
            },
        ),
        lambda args: service.search_events_by_year(**args),
    )

    registry.register(
        ToolDefinition(
            name="search_events_by_range",
            description="Search historical events in a year range.",
            input_schema={
                "type": "object",
                "properties": {
                    "start_year": {"type": "integer"},
                    "end_year": {"type": "integer"},
                    "regions": {"type": ["array", "null"], "items": {"type": "string"}},
                    "polities": {"type": ["array", "null"], "items": {"type": "string"}},
                    "categories": {"type": ["array", "null"], "items": {"type": "string"}},
                    "limit": {"type": "integer", "default": 100},
                },
                "required": ["start_year", "end_year"],
            },
        ),
        lambda args: service.search_events_by_range(**args),
    )

    registry.register(
        ToolDefinition(
            name="compare_regions",
            description="Compare events grouped by regions in a year range.",
            input_schema={
                "type": "object",
                "properties": {
                    "start_year": {"type": "integer"},
                    "end_year": {"type": "integer"},
                    "regions": {"type": "array", "items": {"type": "string"}},
                    "categories": {"type": ["array", "null"], "items": {"type": "string"}},
                },
                "required": ["start_year", "end_year", "regions"],
            },
        ),
        lambda args: service.compare_regions(**args),
    )

    registry.register(
        ToolDefinition(
            name="get_event_detail",
            description="Get a single event with sources and metadata.",
            input_schema={
                "type": "object",
                "properties": {"event_id": {"type": "string"}},
                "required": ["event_id"],
            },
        ),
        lambda args: service.get_event_detail(**args),
    )

    registry.register(
        ToolDefinition(
            name="find_contemporary_events",
            description="Find events around a known event in nearby years.",
            input_schema={
                "type": "object",
                "properties": {
                    "event_id": {"type": "string"},
                    "window_years": {"type": "integer", "default": 10},
                    "regions": {"type": ["array", "null"], "items": {"type": "string"}},
                    "limit": {"type": "integer", "default": 50},
                },
                "required": ["event_id"],
            },
        ),
        lambda args: service.find_contemporary_events(**args),
    )

    registry.register(
        ToolDefinition(
            name="find_related_events",
            description="Find curated relation records for a known event.",
            input_schema={
                "type": "object",
                "properties": {
                    "event_id": {"type": "string"},
                    "relation_types": {"type": ["array", "null"], "items": {"type": "string"}},
                    "limit": {"type": "integer", "default": 20},
                },
                "required": ["event_id"],
            },
        ),
        lambda args: service.find_related_events(**args),
    )

    registry.register(
        ToolDefinition(
            name="resolve_event",
            description="Resolve a user phrase or event title to an event id.",
            input_schema={
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        ),
        lambda args: _resolve_event(service, str(args["query"])),
    )

    if event_management_service:
        revision_tools = EventRevisionToolService(event_management_service, admin_token)
        revision_schema = {
            "type": "object",
            "properties": {
                "event_id": {"type": "string"},
                "updates": {"type": "object"},
                "reason": {"type": "string", "default": ""},
                "confirmed_by": {"type": "string", "default": "agent"},
            },
            "required": ["event_id", "updates"],
        }
        registry.register(
            ToolDefinition(
                name="draft_event_revision",
                description=(
                    "Draft proposed changes for one historical event. "
                    "This tool only returns a field diff and never writes to the database."
                ),
                input_schema=revision_schema,
            ),
            revision_tools.draft_event_revision,
        )
        registry.register(
            ToolDefinition(
                name="apply_event_revision",
                description=(
                    "Apply confirmed changes for one historical event using the admin update path "
                    "and event_change_logs audit trail."
                ),
                input_schema={
                    **revision_schema,
                    "properties": {
                        **revision_schema["properties"],
                        "confirmed": {"type": "boolean", "default": False},
                    },
                },
                risk_level="high",
                idempotent=False,
                requires_confirmation=True,
                max_retries=0,
            ),
            revision_tools.apply_event_revision,
        )

        source_revision_tools = SourceRevisionToolService(event_management_service, admin_token)
        source_revision_schema = {
            "type": "object",
            "properties": {
                "source_id": {"type": "string", "default": ""},
                "event_id": {"type": "string", "default": ""},
                "source_query": {"type": "string", "default": ""},
                "updates": {"type": "object"},
                "reason": {"type": "string", "default": ""},
                "confirmed_by": {"type": "string", "default": "agent"},
            },
            "required": ["updates"],
        }
        registry.register(
            ToolDefinition(
                name="draft_source_revision",
                description=(
                    "Draft proposed reliability, primary-source, citation, or excerpt changes "
                    "for one event source. This tool never writes to the database."
                ),
                input_schema=source_revision_schema,
            ),
            source_revision_tools.draft_source_revision,
        )
        registry.register(
            ToolDefinition(
                name="apply_source_revision",
                description=(
                    "Apply confirmed changes for one event source using the admin source update path "
                    "and event_change_logs audit trail."
                ),
                input_schema={
                    **source_revision_schema,
                    "properties": {
                        **source_revision_schema["properties"],
                        "confirmed": {"type": "boolean", "default": False},
                    },
                },
                risk_level="high",
                idempotent=False,
                requires_confirmation=True,
                max_retries=0,
            ),
            source_revision_tools.apply_source_revision,
        )

    if knowledge_service:
        registry.register(
            ToolDefinition(
                name="search_knowledge",
                description="Search knowledge document chunks for citations and source-backed context.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "limit": {"type": "integer", "default": 3},
                    },
                    "required": ["query"],
                },
            ),
            lambda args: knowledge_service.search(
                query=str(args["query"]),
                limit=int(args.get("limit", 3)),
            ),
        )

    if enable_confirmation_probe:
        registry.register(
            ToolDefinition(
                name="confirmation_probe",
                description=(
                    "Local end-to-end probe for the human confirmation flow. "
                    "It performs no data mutation and should only be enabled in development."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "target": {"type": "string"},
                        "confirmed": {"type": "boolean", "default": False},
                    },
                    "required": ["target"],
                },
                risk_level="high",
                requires_confirmation=True,
            ),
            lambda args: {
                "success": True,
                "target": str(args.get("target", "")),
                "confirmed": bool(args.get("confirmed", False)),
                "message": "确认探针已执行，没有修改业务数据。",
            },
        )

    return registry


def _resolve_event(service: HistoricalQueryService, query: str) -> dict[str, Any]:
    known_titles = ["怛罗斯之战", "安史之乱", "大化改新", "阿拔斯王朝", "唐朝建立"]
    candidates = service.search_events_by_range(600, 900, limit=200)["events"]
    for title in known_titles:
        if title not in query:
            continue
        for event in candidates:
            if title in event["title"] or event["title"] in title:
                return {"found": True, "query": query, "event": event}

    for event in candidates:
        if event["title"] in query or query in event["title"]:
            return {"found": True, "query": query, "event": event}

    return {"found": False, "query": query}
