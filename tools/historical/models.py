from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator


TimePrecision = Literal[
    "day",
    "month",
    "year",
    "decade",
    "century",
    "range",
    "approximate",
    "unknown",
]
SourceStatus = Literal["draft", "reviewing", "verified", "disputed", "archived"]
SourceType = Literal[
    "book",
    "paper",
    "primary_source",
    "encyclopedia",
    "website",
    "dataset",
    "note",
]


class EventSource(BaseModel):
    id: str | None = None
    source_title: str
    source_type: SourceType
    url: str = ""
    citation: str = ""
    excerpt: str = ""
    reliability: float = Field(default=0.5, ge=0, le=1)


class HistoricalEvent(BaseModel):
    id: str | None = None
    title: str
    start_year: int
    end_year: int | None = None
    start_date_text: str = ""
    end_date_text: str = ""
    time_precision: TimePrecision = "year"
    region: str
    polity: str
    modern_country: str = ""
    category: list[str] = Field(default_factory=list)
    summary: str
    causes: list[str] = Field(default_factory=list)
    effects: list[str] = Field(default_factory=list)
    actors: list[str] = Field(default_factory=list)
    source_status: SourceStatus = "draft"
    confidence: float = Field(default=0.5, ge=0, le=1)
    sources: list[EventSource] = Field(default_factory=list)

    @model_validator(mode="after")
    def ensure_end_year(self) -> "HistoricalEvent":
        if self.end_year is None:
            self.end_year = self.start_year
        if self.end_year < self.start_year:
            raise ValueError("end_year cannot be earlier than start_year")
        return self

    def overlaps_year(self, year: int) -> bool:
        return self.start_year <= year <= (self.end_year or self.start_year)

    def overlaps_range(self, start_year: int, end_year: int) -> bool:
        actual_end_year = self.end_year or self.start_year
        return self.start_year <= end_year and actual_end_year >= start_year


class HistoricalEventRepositoryProtocol:
    def get(self, event_id: str) -> HistoricalEvent | None:
        raise NotImplementedError

    def search_by_year(
        self,
        year: int,
        regions: list[str] | None = None,
        polities: list[str] | None = None,
        categories: list[str] | None = None,
        limit: int = 50,
    ) -> list[HistoricalEvent]:
        raise NotImplementedError

    def search_by_range(
        self,
        start_year: int,
        end_year: int,
        regions: list[str] | None = None,
        polities: list[str] | None = None,
        categories: list[str] | None = None,
        limit: int = 100,
    ) -> list[HistoricalEvent]:
        raise NotImplementedError
