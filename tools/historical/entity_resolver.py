from __future__ import annotations

import psycopg


class HistoricalEntityResolver:
    def ensure_region(self, cur: psycopg.Cursor, name: str) -> str | None:
        if not name:
            return None
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

    def ensure_country(
        self,
        cur: psycopg.Cursor,
        name: str,
        region_id: str | None,
    ) -> str | None:
        if not name:
            return None
        first_name = name.split("、", maxsplit=1)[0]
        cur.execute(
            """
            INSERT INTO modern_countries (name, region_id)
            VALUES (%s, %s)
            ON CONFLICT (name) DO UPDATE SET
              region_id = coalesce(modern_countries.region_id, EXCLUDED.region_id)
            RETURNING id::text
            """,
            [first_name, region_id],
        )
        return cur.fetchone()["id"]

    def ensure_polity(
        self,
        cur: psycopg.Cursor,
        name: str,
        region_id: str | None,
        start_year: int,
        end_year: int | None,
    ) -> str | None:
        if not name:
            return None
        cur.execute("SELECT id::text FROM polities WHERE name = %s", [name])
        row = cur.fetchone()
        if row:
            return row["id"]

        cur.execute(
            """
            INSERT INTO polities (name, region_id, start_year, end_year)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (name, start_year, end_year) DO UPDATE SET
              region_id = EXCLUDED.region_id
            RETURNING id::text
            """,
            [name, region_id, start_year, end_year],
        )
        return cur.fetchone()["id"]

    def ensure_category(self, cur: psycopg.Cursor, name: str) -> str:
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
