from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

import psycopg
from psycopg import errors
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
                self._ensure_knowledge_versioning(cur)
                cur.execute(
                    """
                    INSERT INTO knowledge_documents (
                      title,
                      source_type,
                      source_uri,
                      citation,
                      content_hash,
                      current_version,
                      created_by
                    )
                    VALUES (%s, %s, %s, %s, %s, 1, %s)
                    ON CONFLICT (content_hash) DO UPDATE SET
                      title = EXCLUDED.title,
                      source_type = EXCLUDED.source_type,
                      source_uri = EXCLUDED.source_uri,
                      citation = EXCLUDED.citation,
                      updated_at = now()
                    RETURNING id::text, current_version
                    """,
                    [title, source_type, source_uri, citation, content_hash, created_by],
                )
                document = cur.fetchone()
                document_id = document["id"]
                version_number = int(document["current_version"])
                cur.execute("DELETE FROM knowledge_chunks WHERE document_id = %s", [document_id])
                self._insert_document_version(
                    cur=cur,
                    document_id=document_id,
                    version_number=version_number,
                    title=title,
                    content_hash=content_hash,
                    content=content,
                    chunk_count=len(chunks),
                    changed_by=created_by,
                    change_reason="initial ingest",
                    on_conflict="nothing",
                )

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
                            Jsonb({
                                "embedding_provider": "local_hash",
                                "document_version": version_number,
                            }),
                        ],
                    )
            conn.commit()

        return {
            "document_id": document_id,
            "title": title,
            "chunk_count": len(chunks),
            "content_hash": content_hash,
            "version_number": version_number,
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
                self._ensure_knowledge_versioning(cur)
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
                      d.current_version,
                      d.status,
                      d.created_by,
                      d.created_at,
                      d.updated_at,
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
                self._ensure_knowledge_versioning(cur)
                cur.execute(
                    """
                    SELECT
                      id::text,
                      title,
                      source_type,
                      source_uri,
                      citation,
                      content_hash,
                      current_version,
                      status,
                      created_by,
                      created_at,
                      updated_at
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
                self._ensure_knowledge_versioning(cur)
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
                      current_version,
                      status,
                      created_by,
                      created_at,
                      updated_at
                    """,
                    values,
                )
                row = cur.fetchone()
                if not row:
                    return {"success": False, "error": "document not found", "document_id": document_id}
            conn.commit()
        return {"success": True, "document": dict(row)}

    def list_document_versions(self, document_id: str) -> dict[str, Any]:
        with psycopg.connect(self.settings.dsn, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                self._ensure_knowledge_versioning(cur)
                cur.execute("SELECT id::text FROM knowledge_documents WHERE id = %s", [document_id])
                if not cur.fetchone():
                    return {"found": False, "document_id": document_id, "versions": []}
                cur.execute(
                    """
                    SELECT
                      id::text,
                      document_id::text,
                      version_number,
                      title,
                      content_hash,
                      chunk_count,
                      chunking_config,
                      changed_by,
                      change_reason,
                      created_at
                    FROM knowledge_document_versions
                    WHERE document_id = %s
                    ORDER BY version_number DESC
                    """,
                    [document_id],
                )
                versions = [dict(row) for row in cur.fetchall()]
        return {
            "found": True,
            "document_id": document_id,
            "count": len(versions),
            "versions": versions,
        }

    def rechunk_document(
        self,
        document_id: str,
        content: str | None = None,
        max_chars: int | None = None,
        overlap_chars: int | None = None,
        changed_by: str = "",
        reason: str = "",
    ) -> dict[str, Any]:
        chunking = ChunkingConfig(
            max_chars=max(100, min(int(max_chars or self.chunking.max_chars), 5000)),
            overlap_chars=max(0, min(int(overlap_chars or self.chunking.overlap_chars), 1000)),
        )
        with psycopg.connect(self.settings.dsn, row_factory=dict_row) as conn:
            try:
                with conn.cursor() as cur:
                    self._ensure_knowledge_versioning(cur)
                    cur.execute(
                        """
                        SELECT
                          id::text,
                          title,
                          current_version
                        FROM knowledge_documents
                        WHERE id = %s
                        """,
                        [document_id],
                    )
                    document = cur.fetchone()
                    if not document:
                        return {"success": False, "error": "document not found", "document_id": document_id}
                    source_content = content if content is not None else self._latest_document_content(cur, document_id)
                    chunks = self._chunk_text(source_content, chunking)
                    content_hash = hashlib.sha256(source_content.encode("utf-8")).hexdigest()
                    version_number = int(document["current_version"]) + 1
                    cur.execute(
                        """
                        UPDATE knowledge_documents
                        SET content_hash = %s,
                            current_version = %s,
                            updated_at = now()
                        WHERE id = %s
                        RETURNING
                          id::text,
                          title,
                          source_type,
                          source_uri,
                          citation,
                          content_hash,
                          current_version,
                          status,
                          created_by,
                          created_at,
                          updated_at
                        """,
                        [content_hash, version_number, document_id],
                    )
                    updated_document = dict(cur.fetchone())
                    self._insert_document_version(
                        cur=cur,
                        document_id=document_id,
                        version_number=version_number,
                        title=str(document["title"]),
                        content_hash=content_hash,
                        content=source_content,
                        chunk_count=len(chunks),
                        changed_by=changed_by,
                        change_reason=reason or "manual rechunk",
                        chunking=chunking,
                    )
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
                                Jsonb({
                                    "embedding_provider": "local_hash",
                                    "document_version": version_number,
                                    "rechunked": True,
                                }),
                            ],
                        )
                conn.commit()
            except errors.UniqueViolation:
                conn.rollback()
                return {
                    "success": False,
                    "error": "another document already has the same content hash",
                    "document_id": document_id,
                }
        return {
            "success": True,
            "document": updated_document,
            "version_number": version_number,
            "chunk_count": len(chunks),
            "content_hash": content_hash,
        }

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
                claimed = self._claim_vector_job(cur, job_id=job_id)
                if not claimed:
                    return {
                        "processed": False,
                        "error": "job not found or not processable",
                        "job_id": job_id,
                    }
            conn.commit()

        return self._process_claimed_vector_job(dict(claimed))

    def process_next_vector_rebuild_job(self) -> dict[str, Any]:
        with psycopg.connect(self.settings.dsn, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                self._ensure_vector_jobs_table(cur)
                claimed = self._claim_vector_job(cur)
                if not claimed:
                    return {"processed": False, "status": "idle"}
            conn.commit()
        return self._process_claimed_vector_job(dict(claimed))

    def process_pending_vector_rebuild_jobs(self, limit: int = 1) -> dict[str, Any]:
        limit = max(1, min(limit, 50))
        results: list[dict[str, Any]] = []
        for _ in range(limit):
            result = self.process_next_vector_rebuild_job()
            if not result.get("processed"):
                break
            results.append(result)
        return {
            "success": True,
            "processed": len(results) > 0,
            "processed_count": len(results),
            "limit": limit,
            "results": results,
        }

    def _process_claimed_vector_job(self, claimed: dict[str, Any]) -> dict[str, Any]:
        job_id = str(claimed["id"])
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

    def _chunk_text(self, text: str, chunking: ChunkingConfig | None = None) -> list[str]:
        normalized = text.strip()
        if not normalized:
            raise ValueError("document content cannot be empty")

        chunks: list[str] = []
        start = 0
        config = chunking or self.chunking
        max_chars = config.max_chars
        overlap = min(config.overlap_chars, max_chars // 2)
        while start < len(normalized):
            end = min(start + max_chars, len(normalized))
            chunks.append(normalized[start:end])
            if end == len(normalized):
                break
            start = max(0, end - overlap)
        return chunks

    def _latest_document_content(self, cur: psycopg.Cursor, document_id: str) -> str:
        cur.execute(
            """
            SELECT content_snapshot
            FROM knowledge_document_versions
            WHERE document_id = %s
            ORDER BY version_number DESC
            LIMIT 1
            """,
            [document_id],
        )
        version = cur.fetchone()
        if version:
            return str(version["content_snapshot"])
        cur.execute(
            """
            SELECT content
            FROM knowledge_chunks
            WHERE document_id = %s
            ORDER BY chunk_index
            """,
            [document_id],
        )
        chunks = [str(row["content"]) for row in cur.fetchall()]
        return "\n\n".join(chunks)

    def _insert_document_version(
        self,
        cur: psycopg.Cursor,
        document_id: str,
        version_number: int,
        title: str,
        content_hash: str,
        content: str,
        chunk_count: int,
        changed_by: str,
        change_reason: str,
        chunking: ChunkingConfig | None = None,
        on_conflict: str = "error",
    ) -> None:
        config = chunking or self.chunking
        conflict_sql = "ON CONFLICT (document_id, version_number) DO NOTHING" if on_conflict == "nothing" else ""
        cur.execute(
            f"""
            INSERT INTO knowledge_document_versions (
              document_id,
              version_number,
              title,
              content_hash,
              content_snapshot,
              chunk_count,
              chunking_config,
              changed_by,
              change_reason
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            {conflict_sql}
            """,
            [
                document_id,
                version_number,
                title,
                content_hash,
                content,
                chunk_count,
                Jsonb({
                    "max_chars": config.max_chars,
                    "overlap_chars": config.overlap_chars,
                }),
                changed_by,
                change_reason,
            ],
        )

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
              finished_at timestamptz,
              CONSTRAINT vector_rebuild_jobs_target CHECK (target IN ('knowledge', 'events', 'all')),
              CONSTRAINT vector_rebuild_jobs_status CHECK (status IN ('pending', 'running', 'completed', 'failed')),
              CONSTRAINT vector_rebuild_jobs_item_limit CHECK (item_limit > 0)
            )
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_vector_rebuild_jobs_status
              ON vector_rebuild_jobs (status)
            """
        )

    def _claim_vector_job(
        self,
        cur: psycopg.Cursor,
        job_id: str | None = None,
    ) -> dict[str, Any] | None:
        if job_id:
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
        else:
            cur.execute(
                """
                WITH next_job AS (
                  SELECT id
                  FROM vector_rebuild_jobs
                  WHERE status = 'pending'
                  ORDER BY created_at ASC
                  LIMIT 1
                  FOR UPDATE SKIP LOCKED
                )
                UPDATE vector_rebuild_jobs job
                SET status = 'running',
                    started_at = now(),
                    error_message = ''
                FROM next_job
                WHERE job.id = next_job.id
                RETURNING job.id::text, job.target, job.item_limit
                """
            )
        row = cur.fetchone()
        return dict(row) if row else None

    def _ensure_knowledge_versioning(self, cur: psycopg.Cursor) -> None:
        cur.execute(
            """
            ALTER TABLE knowledge_documents
            ADD COLUMN IF NOT EXISTS current_version integer NOT NULL DEFAULT 1
            """
        )
        cur.execute(
            """
            ALTER TABLE knowledge_documents
            ADD COLUMN IF NOT EXISTS updated_at timestamptz NOT NULL DEFAULT now()
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS knowledge_document_versions (
              id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
              document_id uuid NOT NULL REFERENCES knowledge_documents(id) ON DELETE CASCADE,
              version_number integer NOT NULL,
              title text NOT NULL,
              content_hash text NOT NULL,
              content_snapshot text NOT NULL,
              chunk_count integer NOT NULL DEFAULT 0,
              chunking_config jsonb NOT NULL DEFAULT '{}'::jsonb,
              changed_by text NOT NULL DEFAULT '',
              change_reason text NOT NULL DEFAULT '',
              created_at timestamptz NOT NULL DEFAULT now(),
              UNIQUE (document_id, version_number)
            )
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_knowledge_document_versions_document_id
              ON knowledge_document_versions (document_id, version_number DESC)
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
