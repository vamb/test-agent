from __future__ import annotations

from typing import Any

import psycopg
from psycopg.rows import dict_row

from apps.api.settings import PostgresSettings


class ManagementOverviewService:
    def __init__(self, postgres_settings: PostgresSettings) -> None:
        self.postgres_settings = postgres_settings

    def overview(self) -> dict[str, Any]:
        with psycopg.connect(self.postgres_settings.dsn, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                event_embedding_expr = (
                    "count(*) FILTER (WHERE embedding IS NOT NULL)"
                    if self.column_exists(cur, "historical_events", "embedding")
                    else "0"
                )
                cur.execute(
                    f"""
                    SELECT
                      count(*) AS total_events,
                      count(*) FILTER (WHERE status = 'draft') AS draft_events,
                      count(*) FILTER (WHERE status = 'reviewing') AS reviewing_events,
                      count(*) FILTER (WHERE status = 'verified') AS verified_events,
                      count(*) FILTER (WHERE status = 'disputed') AS disputed_events,
                      count(*) FILTER (WHERE status = 'archived') AS archived_events,
                      count(*) FILTER (WHERE confidence < 0.7) AS low_confidence_events,
                      count(*) FILTER (
                        WHERE NOT EXISTS (
                          SELECT 1 FROM event_sources s WHERE s.event_id = historical_events.id
                        )
                      ) AS events_without_sources,
                      {event_embedding_expr} AS events_with_embedding
                    FROM historical_events
                    """
                )
                event_stats = dict(cur.fetchone())
                cur.execute(
                    """
                    SELECT
                      count(*) AS total_batches,
                      count(*) FILTER (WHERE status = 'pending') AS pending_batches,
                      count(*) FILTER (WHERE status = 'validated') AS validated_batches,
                      count(*) FILTER (WHERE status = 'imported') AS imported_batches,
                      count(*) FILTER (WHERE status = 'rejected') AS rejected_batches
                    FROM import_batches
                    """
                )
                import_stats = dict(cur.fetchone())
                cur.execute(
                    """
                    SELECT
                      count(*) AS total_sources,
                      count(*) FILTER (WHERE reliability >= 0.8) AS reliable_sources,
                      count(*) FILTER (WHERE citation = '' AND excerpt = '') AS weak_sources
                    FROM event_sources
                    """
                )
                source_stats = dict(cur.fetchone())
                knowledge_stats = self._knowledge_overview(cur)

        total_events = int(event_stats["total_events"] or 0)
        events_with_embedding = int(event_stats["events_with_embedding"] or 0)
        event_stats["embedding_coverage"] = (
            events_with_embedding / total_events if total_events else 0
        )
        return {
            "events": event_stats,
            "imports": import_stats,
            "sources": source_stats,
            "knowledge": knowledge_stats,
        }

    def column_exists(self, cur: psycopg.Cursor, table_name: str, column_name: str) -> bool:
        cur.execute(
            """
            SELECT EXISTS (
              SELECT 1
              FROM information_schema.columns
              WHERE table_name = %s
                AND column_name = %s
            ) AS exists
            """,
            [table_name, column_name],
        )
        return bool(cur.fetchone()["exists"])

    def _knowledge_overview(self, cur: psycopg.Cursor) -> dict[str, Any]:
        cur.execute(
            """
            SELECT EXISTS (
              SELECT 1 FROM information_schema.tables
              WHERE table_name = 'knowledge_documents'
            ) AS exists
            """
        )
        if not cur.fetchone()["exists"]:
            return {
                "total_documents": 0,
                "active_documents": 0,
                "total_chunks": 0,
                "chunks_with_embedding": 0,
                "embedding_coverage": 0,
            }
        cur.execute(
            """
            SELECT
              (SELECT count(*) FROM knowledge_documents) AS total_documents,
              (SELECT count(*) FROM knowledge_documents WHERE status = 'active') AS active_documents,
              (SELECT count(*) FROM knowledge_chunks) AS total_chunks,
              (SELECT count(*) FROM knowledge_chunks WHERE embedding IS NOT NULL) AS chunks_with_embedding
            """
        )
        stats = dict(cur.fetchone())
        total_chunks = int(stats["total_chunks"] or 0)
        chunks_with_embedding = int(stats["chunks_with_embedding"] or 0)
        stats["embedding_coverage"] = chunks_with_embedding / total_chunks if total_chunks else 0
        return stats
