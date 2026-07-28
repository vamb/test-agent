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
