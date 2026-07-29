from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from apps.api.settings import PostgresSettings
from knowledge.embedding import HashEmbeddingGenerator, vector_literal


@dataclass(frozen=True)
class ChunkingConfig:
    max_chars: int = 500
    overlap_chars: int = 80


class KnowledgeService:
    def __init__(
        self,
        settings: PostgresSettings,
        embedding_generator: HashEmbeddingGenerator | None = None,
        chunking: ChunkingConfig | None = None,
    ) -> None:
        self.settings = settings
        self.embedding_generator = embedding_generator or HashEmbeddingGenerator()
        self.chunking = chunking or ChunkingConfig()

    def ingest_document(
        self,
        title: str,
        content: str,
        source_type: str = "note",
        source_uri: str = "",
        citation: str = "",
        created_by: str = "",
    ) -> dict[str, Any]:
        chunks = self._chunk_text(content)
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()

        with psycopg.connect(self.settings.dsn, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO knowledge_documents (
                      title,
                      source_type,
                      source_uri,
                      citation,
                      content_hash,
                      created_by
                    )
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (content_hash) DO UPDATE SET
                      title = EXCLUDED.title,
                      source_type = EXCLUDED.source_type,
                      source_uri = EXCLUDED.source_uri,
                      citation = EXCLUDED.citation
                    RETURNING id::text
                    """,
                    [title, source_type, source_uri, citation, content_hash, created_by],
                )
                document_id = cur.fetchone()["id"]
                cur.execute("DELETE FROM knowledge_chunks WHERE document_id = %s", [document_id])

                for index, chunk in enumerate(chunks):
                    embedding = self.embedding_generator.embed(chunk)
                    cur.execute(
                        """
                        INSERT INTO knowledge_chunks (
                          document_id,
                          chunk_index,
                          content,
                          token_estimate,
                          embedding,
                          metadata
                        )
                        VALUES (%s, %s, %s, %s, %s::vector, %s)
                        """,
                        [
                            document_id,
                            index,
                            chunk,
                            self._estimate_tokens(chunk),
                            vector_literal(embedding),
                            Jsonb({"embedding_provider": "local_hash"}),
                        ],
                    )
            conn.commit()

        return {
            "document_id": document_id,
            "title": title,
            "chunk_count": len(chunks),
            "content_hash": content_hash,
        }

    def search(self, query: str, limit: int = 5) -> dict[str, Any]:
        embedding = vector_literal(self.embedding_generator.embed(query))
        with psycopg.connect(self.settings.dsn, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                      c.id::text AS chunk_id,
                      c.document_id::text,
                      c.chunk_index,
                      c.content,
                      c.token_estimate,
                      d.title,
                      d.source_type,
                      d.source_uri,
                      d.citation,
                      1 - (c.embedding <=> %s::vector) AS score
                    FROM knowledge_chunks c
                    JOIN knowledge_documents d ON d.id = c.document_id
                    WHERE d.status = 'active'
                      AND c.embedding IS NOT NULL
                    ORDER BY c.embedding <=> %s::vector
                    LIMIT %s
                    """,
                    [embedding, embedding, limit],
                )
                rows = [dict(row) for row in cur.fetchall()]

        return {
            "query": query,
            "count": len(rows),
            "results": rows,
        }

    def list_documents(
        self,
        status: str | None = None,
        query: str = "",
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        where: list[str] = []
        params: list[Any] = []
        if status:
            where.append("d.status = %s")
            params.append(status)
        if query:
            where.append("(d.title ILIKE %s OR d.citation ILIKE %s OR d.source_uri ILIKE %s)")
            like = f"%{query}%"
            params.extend([like, like, like])
        where_sql = f"WHERE {' AND '.join(where)}" if where else ""
        limit = max(1, min(limit, 200))
        offset = max(0, offset)

        with psycopg.connect(self.settings.dsn, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT count(*) AS total
                    FROM knowledge_documents d
                    {where_sql}
                    """,
                    params,
                )
                total = int(cur.fetchone()["total"])
                cur.execute(
                    f"""
                    SELECT
                      d.id::text,
                      d.title,
                      d.source_type,
                      d.source_uri,
                      d.citation,
                      d.content_hash,
                      d.status,
                      d.created_by,
                      d.created_at,
                      count(c.id) AS chunk_count,
                      count(c.id) FILTER (WHERE c.embedding IS NOT NULL) AS embedded_chunk_count,
                      coalesce(sum(c.token_estimate), 0) AS token_estimate
                    FROM knowledge_documents d
                    LEFT JOIN knowledge_chunks c ON c.document_id = d.id
                    {where_sql}
                    GROUP BY d.id
                    ORDER BY d.created_at DESC
                    LIMIT %s OFFSET %s
                    """,
                    [*params, limit, offset],
                )
                rows = [dict(row) for row in cur.fetchall()]

        return {"count": len(rows), "total": total, "limit": limit, "offset": offset, "documents": rows}

    def get_document_chunks(
        self,
        document_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        limit = max(1, min(limit, 500))
        offset = max(0, offset)
        with psycopg.connect(self.settings.dsn, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                      id::text,
                      title,
                      source_type,
                      source_uri,
                      citation,
                      status,
                      created_by,
                      created_at
                    FROM knowledge_documents
                    WHERE id = %s
                    """,
                    [document_id],
                )
                document = cur.fetchone()
                if not document:
                    return {"found": False, "document_id": document_id, "chunks": []}
                cur.execute(
                    """
                    SELECT count(*) AS total
                    FROM knowledge_chunks
                    WHERE document_id = %s
                    """,
                    [document_id],
                )
                total = int(cur.fetchone()["total"])
                cur.execute(
                    """
                    SELECT
                      id::text AS chunk_id,
                      document_id::text,
                      chunk_index,
                      content,
                      token_estimate,
                      embedding IS NOT NULL AS has_embedding,
                      metadata,
                      created_at
                    FROM knowledge_chunks
                    WHERE document_id = %s
                    ORDER BY chunk_index
                    LIMIT %s OFFSET %s
                    """,
                    [document_id, limit, offset],
                )
                chunks = [dict(row) for row in cur.fetchall()]
        return {
            "found": True,
            "document": dict(document),
            "count": len(chunks),
            "total": total,
            "limit": limit,
            "offset": offset,
            "chunks": chunks,
        }

    def update_document(self, document_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        allowed_fields = {"title", "source_type", "source_uri", "citation", "status"}
        if not updates:
            return {"success": False, "error": "updates must be a non-empty object"}
        unknown_fields = sorted(set(updates) - allowed_fields)
        if unknown_fields:
            return {"success": False, "error": f"unsupported update fields: {', '.join(unknown_fields)}"}
        if "status" in updates and updates["status"] not in {"active", "inactive", "archived"}:
            return {"success": False, "error": "invalid status"}

        set_parts = [f"{field} = %s" for field in updates]
        values = list(updates.values())
        values.append(document_id)
        with psycopg.connect(self.settings.dsn, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    UPDATE knowledge_documents
                    SET {', '.join(set_parts)}
                    WHERE id = %s
                    RETURNING
                      id::text,
                      title,
                      source_type,
                      source_uri,
                      citation,
                      content_hash,
                      status,
                      created_by,
                      created_at
                    """,
                    values,
                )
                row = cur.fetchone()
                if not row:
                    return {"success": False, "error": "document not found", "document_id": document_id}
            conn.commit()
        return {"success": True, "document": dict(row)}

    def reembed_document(self, document_id: str) -> dict[str, Any]:
        with psycopg.connect(self.settings.dsn, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id::text, chunk_index, content
                    FROM knowledge_chunks
                    WHERE document_id = %s
                    ORDER BY chunk_index
                    """,
                    [document_id],
                )
                chunks = [dict(row) for row in cur.fetchall()]
                if not chunks:
                    return {"success": False, "error": "document not found or has no chunks", "document_id": document_id}
                for chunk in chunks:
                    embedding = self.embedding_generator.embed(chunk["content"])
                    cur.execute(
                        """
                        UPDATE knowledge_chunks
                        SET embedding = %s::vector,
                            metadata = metadata || %s
                        WHERE id = %s
                        """,
                        [
                            vector_literal(embedding),
                            Jsonb({"embedding_provider": "local_hash", "reembedded": True}),
                            chunk["id"],
                        ],
                    )
            conn.commit()
        return {"success": True, "document_id": document_id, "reembedded_chunks": len(chunks)}

    def vector_status(self) -> dict[str, Any]:
        with psycopg.connect(self.settings.dsn, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                event_vector_available = self._column_exists(cur, "historical_events", "embedding")
                if event_vector_available:
                    cur.execute(
                        """
                        SELECT
                          count(*) AS total_events,
                          count(*) FILTER (WHERE embedding IS NOT NULL) AS events_with_embedding
                        FROM historical_events
                        """
                    )
                    event_stats = dict(cur.fetchone())
                else:
                    event_stats = {"total_events": 0, "events_with_embedding": 0}

                cur.execute(
                    """
                    SELECT
                      count(*) AS total_chunks,
                      count(*) FILTER (WHERE embedding IS NOT NULL) AS chunks_with_embedding
                    FROM knowledge_chunks
                    """
                )
                chunk_stats = dict(cur.fetchone())
                cur.execute(
                    """
                    SELECT schemaname, tablename, indexname, indexdef
                    FROM pg_indexes
                    WHERE tablename IN ('historical_events', 'knowledge_chunks')
                      AND indexdef ILIKE '%vector%'
                    ORDER BY tablename, indexname
                    """
                )
                indexes = [dict(row) for row in cur.fetchall()]

        total_events = int(event_stats["total_events"] or 0)
        events_with_embedding = int(event_stats["events_with_embedding"] or 0)
        total_chunks = int(chunk_stats["total_chunks"] or 0)
        chunks_with_embedding = int(chunk_stats["chunks_with_embedding"] or 0)
        return {
            "embedding_provider": "local_hash",
            "dimension": self.embedding_generator.dimensions,
            "events": {
                **event_stats,
                "vector_column_available": event_vector_available,
                "embedding_coverage": events_with_embedding / total_events if total_events else 0,
            },
            "knowledge_chunks": {
                **chunk_stats,
                "embedding_coverage": chunks_with_embedding / total_chunks if total_chunks else 0,
            },
            "indexes": indexes,
        }

    def rebuild_vectors(self, target: str = "knowledge", limit: int = 100) -> dict[str, Any]:
        limit = max(1, min(limit, 1000))
        if target not in {"knowledge", "events", "all"}:
            return {"success": False, "error": "target must be knowledge, events, or all"}

        rebuilt: dict[str, int] = {"knowledge_chunks": 0, "events": 0}
        with psycopg.connect(self.settings.dsn, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                if target in {"knowledge", "all"}:
                    cur.execute(
                        """
                        SELECT id::text, content
                        FROM knowledge_chunks
                        ORDER BY created_at DESC
                        LIMIT %s
                        """,
                        [limit],
                    )
                    chunks = [dict(row) for row in cur.fetchall()]
                    for chunk in chunks:
                        embedding = self.embedding_generator.embed(chunk["content"])
                        cur.execute(
                            """
                            UPDATE knowledge_chunks
                            SET embedding = %s::vector,
                                metadata = metadata || %s
                            WHERE id = %s
                            """,
                            [
                                vector_literal(embedding),
                                Jsonb({"embedding_provider": "local_hash", "rebuilt": True}),
                                chunk["id"],
                            ],
                        )
                    rebuilt["knowledge_chunks"] = len(chunks)

                if target in {"events", "all"} and self._column_exists(cur, "historical_events", "embedding"):
                    cur.execute(
                        """
                        SELECT id::text, title, summary
                        FROM historical_events
                        ORDER BY updated_at DESC
                        LIMIT %s
                        """,
                        [limit],
                    )
                    events = [dict(row) for row in cur.fetchall()]
                    for event in events:
                        embedding = self.embedding_generator.embed(
                            f"{event['title']}\n{event['summary']}"
                        )
                        cur.execute(
                            """
                            UPDATE historical_events
                            SET embedding = %s::vector
                            WHERE id = %s
                            """,
                            [vector_literal(embedding), event["id"]],
                        )
                    rebuilt["events"] = len(events)
            conn.commit()

        return {"success": True, "target": target, "rebuilt": rebuilt}

    def create_vector_rebuild_job(
        self,
        target: str = "knowledge",
        limit: int = 100,
        created_by: str = "",
    ) -> dict[str, Any]:
        if target not in {"knowledge", "events", "all"}:
            return {"created": False, "error": "target must be knowledge, events, or all"}
        limit = max(1, min(limit, 1000))
        with psycopg.connect(self.settings.dsn, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                self._ensure_vector_jobs_table(cur)
                cur.execute(
                    """
                    INSERT INTO vector_rebuild_jobs (
                      target,
                      item_limit,
                      status,
                      created_by
                    )
                    VALUES (%s, %s, 'pending', %s)
                    RETURNING
                      id::text,
                      target,
                      item_limit,
                      status,
                      processed_events,
                      processed_chunks,
                      error_message,
                      created_by,
                      created_at,
                      started_at,
                      finished_at
                    """,
                    [target, limit, created_by],
                )
                job = dict(cur.fetchone())
            conn.commit()
        return {"created": True, "job": job}

    def get_vector_rebuild_job(self, job_id: str) -> dict[str, Any]:
        with psycopg.connect(self.settings.dsn, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                self._ensure_vector_jobs_table(cur)
                job = self._get_vector_job_row(cur, job_id)
        if not job:
            return {"found": False, "job_id": job_id}
        return {"found": True, "job": job}

    def process_vector_rebuild_job(self, job_id: str) -> dict[str, Any]:
        with psycopg.connect(self.settings.dsn, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                self._ensure_vector_jobs_table(cur)
                cur.execute(
                    """
                    UPDATE vector_rebuild_jobs
                    SET status = 'running',
                        started_at = now(),
                        error_message = ''
                    WHERE id = %s
                      AND status IN ('pending', 'failed')
                    RETURNING id::text, target, item_limit
                    """,
                    [job_id],
                )
                claimed = cur.fetchone()
                if not claimed:
                    return {
                        "processed": False,
                        "error": "job not found or not processable",
                        "job_id": job_id,
                    }
            conn.commit()

        try:
            result = self.rebuild_vectors(
                target=str(claimed["target"]),
                limit=int(claimed["item_limit"]),
            )
            if not result.get("success"):
                raise ValueError(str(result.get("error", "vector rebuild failed")))
            rebuilt = result["rebuilt"]
            with psycopg.connect(self.settings.dsn, row_factory=dict_row) as conn:
                with conn.cursor() as cur:
                    self._ensure_vector_jobs_table(cur)
                    cur.execute(
                        """
                        UPDATE vector_rebuild_jobs
                        SET status = 'completed',
                            processed_events = %s,
                            processed_chunks = %s,
                            finished_at = now()
                        WHERE id = %s
                        RETURNING
                          id::text,
                          target,
                          item_limit,
                          status,
                          processed_events,
                          processed_chunks,
                          error_message,
                          created_by,
                          created_at,
                          started_at,
                          finished_at
                        """,
                        [
                            rebuilt.get("events", 0),
                            rebuilt.get("knowledge_chunks", 0),
                            job_id,
                        ],
                    )
                    job = dict(cur.fetchone())
                conn.commit()
            return {"processed": True, "job": job}
        except Exception as exc:
            with psycopg.connect(self.settings.dsn, row_factory=dict_row) as conn:
                with conn.cursor() as cur:
                    self._ensure_vector_jobs_table(cur)
                    cur.execute(
                        """
                        UPDATE vector_rebuild_jobs
                        SET status = 'failed',
                            error_message = %s,
                            finished_at = now()
                        WHERE id = %s
                        RETURNING
                          id::text,
                          target,
                          item_limit,
                          status,
                          processed_events,
                          processed_chunks,
                          error_message,
                          created_by,
                          created_at,
                          started_at,
                          finished_at
                        """,
                        [str(exc), job_id],
                    )
                    job = dict(cur.fetchone())
                conn.commit()
            return {"processed": False, "job": job, "error": str(exc)}

    def _chunk_text(self, text: str) -> list[str]:
        normalized = text.strip()
        if not normalized:
            raise ValueError("document content cannot be empty")

        chunks: list[str] = []
        start = 0
        max_chars = self.chunking.max_chars
        overlap = min(self.chunking.overlap_chars, max_chars // 2)
        while start < len(normalized):
            end = min(start + max_chars, len(normalized))
            chunks.append(normalized[start:end])
            if end == len(normalized):
                break
            start = max(0, end - overlap)
        return chunks

    def _estimate_tokens(self, text: str) -> int:
        return max(1, len(text) // 2)

    def _column_exists(self, cur: psycopg.Cursor, table_name: str, column_name: str) -> bool:
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

    def _ensure_vector_jobs_table(self, cur: psycopg.Cursor) -> None:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS vector_rebuild_jobs (
              id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
              target text NOT NULL,
              item_limit integer NOT NULL DEFAULT 100,
              status text NOT NULL DEFAULT 'pending',
              processed_events integer NOT NULL DEFAULT 0,
              processed_chunks integer NOT NULL DEFAULT 0,
              error_message text NOT NULL DEFAULT '',
              created_by text NOT NULL DEFAULT '',
              created_at timestamptz NOT NULL DEFAULT now(),
              started_at timestamptz,
              finished_at timestamptz
            )
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_vector_rebuild_jobs_status
              ON vector_rebuild_jobs (status)
            """
        )

    def _get_vector_job_row(self, cur: psycopg.Cursor, job_id: str) -> dict[str, Any] | None:
        cur.execute(
            """
            SELECT
              id::text,
              target,
              item_limit,
              status,
              processed_events,
              processed_chunks,
              error_message,
              created_by,
              created_at,
              started_at,
              finished_at
            FROM vector_rebuild_jobs
            WHERE id = %s
            """,
            [job_id],
        )
        row = cur.fetchone()
        return dict(row) if row else None
