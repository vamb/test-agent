from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid5, NAMESPACE_URL

from tools.historical.models import HistoricalEvent


class HistoricalEventRepository:
    def __init__(self, events: list[HistoricalEvent]) -> None:
        self.events = events
        self._events_by_id = {event.id: event for event in events if event.id}

    @classmethod
    def from_default_sample(cls) -> "HistoricalEventRepository":
        root_dir = Path(__file__).resolve().parents[2]
        data_path = root_dir / "data" / "samples" / "events_600_900_sample.json"
        return cls.from_json(data_path)

    @classmethod
    def from_json(cls, path: str | Path) -> "HistoricalEventRepository":
        path = Path(path)
        raw_events = json.loads(path.read_text(encoding="utf-8"))
        events: list[HistoricalEvent] = []
        for raw_event in raw_events:
            event = HistoricalEvent.model_validate(raw_event)
            if not event.id:
                stable_key = f"{event.title}:{event.start_year}:{event.region}:{event.polity}"
                event.id = str(uuid5(NAMESPACE_URL, stable_key))
            events.append(event)
        return cls(events)

    def get(self, event_id: str) -> HistoricalEvent | None:
        return self._events_by_id.get(event_id)

    def search_by_year(
        self,
        year: int,
        regions: list[str] | None = None,
        polities: list[str] | None = None,
        categories: list[str] | None = None,
        limit: int = 50,
    ) -> list[HistoricalEvent]:
        return self._filter_events(
            [event for event in self.events if event.overlaps_year(year)],
            regions=regions,
            polities=polities,
            categories=categories,
            limit=limit,
        )

    def search_by_range(
        self,
        start_year: int,
        end_year: int,
        regions: list[str] | None = None,
        polities: list[str] | None = None,
        categories: list[str] | None = None,
        limit: int = 100,
    ) -> list[HistoricalEvent]:
        if end_year < start_year:
            start_year, end_year = end_year, start_year
        return self._filter_events(
            [event for event in self.events if event.overlaps_range(start_year, end_year)],
            regions=regions,
            polities=polities,
            categories=categories,
            limit=limit,
        )

    def _filter_events(
        self,
        events: list[HistoricalEvent],
        regions: list[str] | None,
        polities: list[str] | None,
        categories: list[str] | None,
        limit: int,
    ) -> list[HistoricalEvent]:
        filtered = events
        if regions:
            region_set = set(regions)
            filtered = [event for event in filtered if event.region in region_set]
        if polities:
            polity_set = set(polities)
            filtered = [event for event in filtered if event.polity in polity_set]
        if categories:
            category_set = set(categories)
            filtered = [
                event for event in filtered if category_set.intersection(event.category)
            ]
        return sorted(filtered, key=lambda event: (event.start_year, event.region, event.title))[
            :limit
        ]

