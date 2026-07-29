from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from apps.api.dependencies import service


router = APIRouter()


@router.get("/events/year/{year}")
def search_events_by_year(
    year: int,
    regions: Annotated[list[str] | None, Query()] = None,
    polities: Annotated[list[str] | None, Query()] = None,
    categories: Annotated[list[str] | None, Query()] = None,
    limit: int = 50,
    nearby_window: int = 0,
) -> dict:
    return service.search_events_by_year(
        year=year,
        regions=regions,
        polities=polities,
        categories=categories,
        limit=limit,
        nearby_window=nearby_window,
    )


@router.get("/events/range")
def search_events_by_range(
    start_year: int,
    end_year: int,
    regions: Annotated[list[str] | None, Query()] = None,
    polities: Annotated[list[str] | None, Query()] = None,
    categories: Annotated[list[str] | None, Query()] = None,
    limit: int = 100,
) -> dict:
    return service.search_events_by_range(
        start_year=start_year,
        end_year=end_year,
        regions=regions,
        polities=polities,
        categories=categories,
        limit=limit,
    )


@router.get("/events/{event_id}")
def get_event_detail(event_id: str) -> dict:
    return service.get_event_detail(event_id)


@router.get("/events/{event_id}/contemporary")
def find_contemporary_events(
    event_id: str,
    window_years: int = 10,
    regions: Annotated[list[str] | None, Query()] = None,
    limit: int = 50,
) -> dict:
    return service.find_contemporary_events(
        event_id=event_id,
        window_years=window_years,
        regions=regions,
        limit=limit,
    )


@router.get("/events/{event_id}/relations")
def find_related_events(
    event_id: str,
    relation_types: Annotated[list[str] | None, Query()] = None,
    limit: int = 20,
) -> dict:
    return service.find_related_events(
        event_id=event_id,
        relation_types=relation_types,
        limit=limit,
    )


@router.get("/compare/regions")
def compare_regions(
    start_year: int,
    end_year: int,
    regions: Annotated[list[str], Query()],
    categories: Annotated[list[str] | None, Query()] = None,
) -> dict:
    return service.compare_regions(
        start_year=start_year,
        end_year=end_year,
        regions=regions,
        categories=categories,
    )
