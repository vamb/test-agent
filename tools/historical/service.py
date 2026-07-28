from __future__ import annotations

from collections import defaultdict

from tools.historical.models import HistoricalEvent, HistoricalEventRepositoryProtocol
from tools.historical.repository import HistoricalEventRepository


class HistoricalQueryService:
    def __init__(
        self, repository: HistoricalEventRepository | HistoricalEventRepositoryProtocol
    ) -> None:
        self.repository = repository

    def search_events_by_year(
        self,
        year: int,
        regions: list[str] | None = None,
        polities: list[str] | None = None,
        categories: list[str] | None = None,
        limit: int = 50,
        nearby_window: int = 0,
    ) -> dict:
        if nearby_window > 0:
            events = self.repository.search_by_range(
                start_year=year - nearby_window,
                end_year=year + nearby_window,
                regions=regions,
                polities=polities,
                categories=categories,
                limit=limit,
            )
        else:
            events = self.repository.search_by_year(
                year=year,
                regions=regions,
                polities=polities,
                categories=categories,
                limit=limit,
            )
        return {
            "year": year,
            "nearby_window": nearby_window,
            "count": len(events),
            "events": [self._event_summary(event) for event in events],
        }

    def search_events_by_range(
        self,
        start_year: int,
        end_year: int,
        regions: list[str] | None = None,
        polities: list[str] | None = None,
        categories: list[str] | None = None,
        limit: int = 100,
    ) -> dict:
        if end_year < start_year:
            start_year, end_year = end_year, start_year
        events = self.repository.search_by_range(
            start_year=start_year,
            end_year=end_year,
            regions=regions,
            polities=polities,
            categories=categories,
            limit=limit,
        )
        return {
            "start_year": start_year,
            "end_year": end_year,
            "count": len(events),
            "events": [self._event_summary(event) for event in events],
        }

    def get_event_detail(self, event_id: str) -> dict:
        event = self.repository.get(event_id)
        if not event:
            return {"event_id": event_id, "found": False}
        return {"found": True, "event": event.model_dump()}

    def find_contemporary_events(
        self,
        event_id: str,
        window_years: int = 10,
        regions: list[str] | None = None,
        limit: int = 50,
    ) -> dict:
        finder = getattr(self.repository, "find_contemporary_events", None)
        if finder:
            events = finder(
                event_id=event_id,
                window_years=window_years,
                regions=regions,
                limit=limit,
            )
        else:
            event = self.repository.get(event_id)
            if not event:
                return {"event_id": event_id, "found": False, "count": 0, "events": []}
            events = self.repository.search_by_range(
                start_year=event.start_year - window_years,
                end_year=(event.end_year or event.start_year) + window_years,
                regions=regions,
                limit=limit + 1,
            )
            events = [candidate for candidate in events if candidate.id != event_id][:limit]
        return {
            "event_id": event_id,
            "found": True,
            "window_years": window_years,
            "count": len(events),
            "events": [self._event_summary(event) for event in events],
        }

    def find_related_events(
        self,
        event_id: str,
        relation_types: list[str] | None = None,
        limit: int = 20,
    ) -> dict:
        finder = getattr(self.repository, "find_related_events", None)
        if not finder:
            return {
                "event_id": event_id,
                "count": 0,
                "relations": [],
                "note": "Current repository does not support relation queries.",
            }
        relations = finder(
            event_id=event_id,
            relation_types=relation_types,
            limit=limit,
        )
        return {
            "event_id": event_id,
            "count": len(relations),
            "relations": relations,
        }

    def compare_regions(
        self,
        start_year: int,
        end_year: int,
        regions: list[str],
        categories: list[str] | None = None,
    ) -> dict:
        if end_year < start_year:
            start_year, end_year = end_year, start_year

        events = self.repository.search_by_range(
            start_year=start_year,
            end_year=end_year,
            regions=regions,
            categories=categories,
            limit=500,
        )
        grouped: dict[str, list[HistoricalEvent]] = defaultdict(list)
        for event in events:
            grouped[event.region].append(event)

        rows = []
        for region in regions:
            region_events = grouped.get(region, [])
            rows.append(
                {
                    "region": region,
                    "count": len(region_events),
                    "events": [self._event_summary(event) for event in region_events],
                }
            )

        return {
            "start_year": start_year,
            "end_year": end_year,
            "regions": regions,
            "rows": rows,
        }

    def _event_summary(self, event: HistoricalEvent) -> dict:
        return {
            "id": event.id,
            "title": event.title,
            "start_year": event.start_year,
            "end_year": event.end_year,
            "time_precision": event.time_precision,
            "region": event.region,
            "polity": event.polity,
            "modern_country": event.modern_country,
            "category": event.category,
            "summary": event.summary,
            "source_status": event.source_status,
            "confidence": event.confidence,
            "source_count": len(event.sources),
            "sources": [source.model_dump() for source in event.sources],
        }
