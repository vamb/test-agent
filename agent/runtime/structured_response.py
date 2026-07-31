from __future__ import annotations

from typing import Any


def build_structured_response(
    answer: str,
    steps: list[Any],
    run_id: str | None = None,
) -> dict[str, Any]:
    events: list[dict[str, Any]] = []
    references: list[dict[str, Any]] = []
    links: list[dict[str, Any]] = []
    seen_events: set[str] = set()
    seen_references: set[str] = set()
    seen_links: set[tuple[str, str]] = set()

    def add_event(event: dict[str, Any]) -> None:
        event_id = event.get("id")
        if not isinstance(event_id, str) or event_id in seen_events:
            return
        if not isinstance(event.get("title"), str) or not isinstance(event.get("start_year"), int):
            return
        seen_events.add(event_id)
        events.append(event)
        add_link(
            {
                "type": "event",
                "target_id": event_id,
                "title": str(event["title"]),
                "href": f"/events/{event_id}",
            }
        )
        for source in event.get("sources") or []:
            if isinstance(source, dict):
                add_reference(source, event_id=event_id, event_title=str(event["title"]))

    def add_reference(
        source: dict[str, Any],
        event_id: str | None = None,
        event_title: str | None = None,
    ) -> None:
        source_id = source.get("id") or source.get("source_id")
        title = source.get("source_title") or source.get("title")
        if not title:
            return
        key = str(source_id or f"{event_id}:{title}:{source.get('citation', '')}")
        if key in seen_references:
            return
        seen_references.add(key)
        references.append(
            {
                "id": str(source_id) if source_id else "",
                "title": str(title),
                "source_type": str(source.get("source_type", "")),
                "citation": str(source.get("citation", "")),
                "excerpt": str(source.get("excerpt", "")),
                "event_id": event_id or "",
                "event_title": event_title or "",
                "reliability": source.get("reliability"),
                "untrusted": True,
                "context_label": "event_source",
            }
        )

    def add_link(link: dict[str, Any]) -> None:
        href = str(link.get("href", ""))
        link_type = str(link.get("type", ""))
        if not href or not link_type:
            return
        key = (link_type, href)
        if key in seen_links:
            return
        seen_links.add(key)
        links.append(link)

    def add_knowledge_reference(item: dict[str, Any]) -> None:
        chunk_id = item.get("chunk_id")
        title = item.get("title")
        if not title:
            return
        key = str(chunk_id or f"knowledge:{item.get('document_id')}:{item.get('chunk_index')}")
        if key in seen_references:
            return
        seen_references.add(key)
        document_id = str(item.get("document_id", ""))
        references.append(
            {
                "id": key,
                "title": str(title),
                "source_type": str(item.get("source_type", "")),
                "citation": str(item.get("citation", "")),
                "excerpt": str(item.get("content", "")),
                "event_id": "",
                "event_title": "",
                "document_id": document_id,
                "chunk_id": str(chunk_id or ""),
                "score": item.get("score"),
                "untrusted": True,
                "context_label": "knowledge_chunk",
            }
        )
        if document_id:
            add_link(
                {
                    "type": "knowledge_document",
                    "target_id": document_id,
                    "title": str(title),
                    "href": f"/admin/knowledge/{document_id}",
                }
            )

    def collect_from_observation(observation: dict[str, Any]) -> None:
        event = observation.get("event")
        if isinstance(event, dict):
            add_event(event)
        for item in observation.get("events") or []:
            if isinstance(item, dict):
                add_event(item)
        for row in observation.get("rows") or []:
            if not isinstance(row, dict):
                continue
            for item in row.get("events") or []:
                if isinstance(item, dict):
                    add_event(item)
        for item in observation.get("results") or []:
            if isinstance(item, dict):
                add_knowledge_reference(item)

    for step in steps:
        collect_from_observation(step.observation)

    return {
        "run_id": run_id,
        "answer": answer,
        "events": events,
        "references": references,
        "links": links,
    }
