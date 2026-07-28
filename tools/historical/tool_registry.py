from __future__ import annotations

from typing import Any

from tools.historical.service import HistoricalQueryService
from tools.registry.base import ToolDefinition, ToolRegistry


def build_historical_tool_registry(service: HistoricalQueryService) -> ToolRegistry:
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
