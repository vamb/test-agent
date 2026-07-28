from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, uuid5

import psycopg
from psycopg.rows import dict_row

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from apps.api.settings import AppSettings
from tools.historical.models import HistoricalEvent


SAMPLE_PATH = ROOT_DIR / "data" / "samples" / "events_600_900_sample.json"


def stable_event_id(event: HistoricalEvent) -> str:
    key = f"{event.title}:{event.start_year}:{event.region}:{event.polity}"
    return str(uuid5(NAMESPACE_URL, key))


def get_id(cur: psycopg.Cursor, table: str, name: str) -> str | None:
    cur.execute(f"SELECT id::text FROM {table} WHERE name = %s", [name])
    row = cur.fetchone()
    return row["id"] if row else None


def ensure_region(cur: psycopg.Cursor, name: str) -> str:
    cur.execute(
        """
        INSERT INTO regions (name)
        VALUES (%s)
        ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name
        RETURNING id::text
        """,
        [name],
    )
    return cur.fetchone()["id"]


def ensure_country(cur: psycopg.Cursor, name: str, region_id: str) -> str | None:
    if not name:
        return None
    first_name = name.split("、", maxsplit=1)[0]
    cur.execute(
        """
        INSERT INTO modern_countries (name, region_id)
        VALUES (%s, %s)
        ON CONFLICT (name) DO UPDATE SET region_id = coalesce(modern_countries.region_id, EXCLUDED.region_id)
        RETURNING id::text
        """,
        [first_name, region_id],
    )
    return cur.fetchone()["id"]


def ensure_polity(cur: psycopg.Cursor, event: HistoricalEvent, region_id: str) -> str:
    existing = get_id(cur, "polities", event.polity)
    if existing:
        return existing

    cur.execute(
        """
        INSERT INTO polities (name, region_id, start_year, end_year)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (name, start_year, end_year) DO UPDATE SET region_id = EXCLUDED.region_id
        RETURNING id::text
        """,
        [event.polity, region_id, event.start_year, event.end_year],
    )
    return cur.fetchone()["id"]


def ensure_category(cur: psycopg.Cursor, name: str) -> str:
    cur.execute(
        """
        INSERT INTO categories (name)
        VALUES (%s)
        ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name
        RETURNING id::text
        """,
        [name],
    )
    return cur.fetchone()["id"]


def insert_event(cur: psycopg.Cursor, event: HistoricalEvent) -> str:
    event_id = event.id or stable_event_id(event)
    region_id = ensure_region(cur, event.region)
    country_id = ensure_country(cur, event.modern_country, region_id)
    polity_id = ensure_polity(cur, event, region_id)

    cur.execute(
        """
        INSERT INTO historical_events (
          id,
          title,
          canonical_title,
          start_year,
          end_year,
          start_date_text,
          end_date_text,
          time_precision,
          is_approximate,
          region_id,
          polity_id,
          primary_modern_country_id,
          location_text,
          summary,
          causes,
          effects,
          status,
          confidence
        )
        VALUES (
          %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
        )
        ON CONFLICT (id) DO UPDATE SET
          title = EXCLUDED.title,
          canonical_title = EXCLUDED.canonical_title,
          start_year = EXCLUDED.start_year,
          end_year = EXCLUDED.end_year,
          start_date_text = EXCLUDED.start_date_text,
          end_date_text = EXCLUDED.end_date_text,
          time_precision = EXCLUDED.time_precision,
          is_approximate = EXCLUDED.is_approximate,
          region_id = EXCLUDED.region_id,
          polity_id = EXCLUDED.polity_id,
          primary_modern_country_id = EXCLUDED.primary_modern_country_id,
          location_text = EXCLUDED.location_text,
          summary = EXCLUDED.summary,
          causes = EXCLUDED.causes,
          effects = EXCLUDED.effects,
          status = EXCLUDED.status,
          confidence = EXCLUDED.confidence
        """,
        [
            event_id,
            event.title,
            event.title,
            event.start_year,
            event.end_year,
            event.start_date_text,
            event.end_date_text,
            event.time_precision,
            event.time_precision == "approximate",
            region_id,
            polity_id,
            country_id,
            event.modern_country,
            event.summary,
            event.causes,
            event.effects,
            event.source_status,
            event.confidence,
        ],
    )

    cur.execute("DELETE FROM event_categories WHERE event_id = %s", [event_id])
    for category in event.category:
        category_id = ensure_category(cur, category)
        cur.execute(
            """
            INSERT INTO event_categories (event_id, category_id)
            VALUES (%s, %s)
            ON CONFLICT DO NOTHING
            """,
            [event_id, category_id],
        )

    cur.execute("DELETE FROM event_sources WHERE event_id = %s", [event_id])
    for source in event.sources:
        cur.execute(
            """
            INSERT INTO event_sources (
              event_id,
              source_title,
              source_type,
              url,
              citation,
              excerpt,
              reliability
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            [
                event_id,
                source.source_title,
                source.source_type,
                source.url,
                source.citation,
                source.excerpt,
                source.reliability,
            ],
        )

    return event_id


def load_events(path: Path) -> list[HistoricalEvent]:
    raw_events: list[dict[str, Any]] = json.loads(path.read_text(encoding="utf-8"))
    return [HistoricalEvent.model_validate(raw_event) for raw_event in raw_events]


def main() -> int:
    settings = AppSettings.from_env().postgres
    events = load_events(SAMPLE_PATH)
    with psycopg.connect(settings.dsn, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            for event in events:
                insert_event(cur, event)
        conn.commit()

    print(f"Imported {len(events)} events into {settings.database}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
