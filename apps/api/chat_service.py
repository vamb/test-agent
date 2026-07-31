from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from apps.api.settings import PostgresSettings


@dataclass(frozen=True)
class StoredUserMessage:
    conversation_id: str
    message_id: str


class ChatService:
    def __init__(self, settings: PostgresSettings, schema_path: Path | None = None) -> None:
        self.settings = settings
        self.schema_path = schema_path or (
            Path(__file__).resolve().parents[2]
            / "infrastructure"
            / "database"
            / "schema_auth_chat.sql"
        )
        self._schema_ready = False

    @contextmanager
    def _connect(self) -> Iterator[psycopg.Connection]:
        with psycopg.connect(self.settings.dsn, row_factory=dict_row) as conn:
            yield conn

    def ensure_schema(self) -> None:
        if self._schema_ready:
            return
        sql = self.schema_path.read_text(encoding="utf-8")
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql)
            conn.commit()
        self._schema_ready = True

    def create_group(
        self,
        user_id: str,
        title: str,
        description: str = "",
    ) -> dict[str, Any]:
        self.ensure_schema()
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO chat_groups (user_id, title, description)
                    VALUES (%s, %s, %s)
                    RETURNING
                      id::text,
                      user_id::text,
                      title,
                      description,
                      pinned,
                      archived,
                      created_at,
                      updated_at
                    """,
                    [user_id, title.strip() or "新分组", description.strip()],
                )
                row = dict(cur.fetchone())
            conn.commit()
        return row

    def list_groups(self, user_id: str, include_archived: bool = False) -> list[dict[str, Any]]:
        self.ensure_schema()
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                      id::text,
                      user_id::text,
                      title,
                      description,
                      pinned,
                      archived,
                      created_at,
                      updated_at
                    FROM chat_groups
                    WHERE user_id = %s
                      AND (%s OR archived = false)
                    ORDER BY pinned DESC, updated_at DESC, created_at DESC
                    """,
                    [user_id, include_archived],
                )
                rows = [dict(row) for row in cur.fetchall()]
        return rows

    def update_group(
        self,
        user_id: str,
        group_id: str,
        updates: dict[str, Any],
    ) -> dict[str, Any] | None:
        self.ensure_schema()
        allowed = {
            "title": str,
            "description": str,
            "pinned": bool,
            "archived": bool,
        }
        assignments = []
        values: list[Any] = []
        for key, expected_type in allowed.items():
            if key not in updates:
                continue
            value = updates[key]
            if expected_type is bool:
                value = bool(value)
            else:
                value = str(value)
            assignments.append(f"{key} = %s")
            values.append(value)
        if not assignments:
            return self.get_group(user_id, group_id)
        values.extend([group_id, user_id])
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    UPDATE chat_groups
                    SET {", ".join(assignments)},
                        updated_at = now()
                    WHERE id = %s
                      AND user_id = %s
                    RETURNING
                      id::text,
                      user_id::text,
                      title,
                      description,
                      pinned,
                      archived,
                      created_at,
                      updated_at
                    """,
                    values,
                )
                row = cur.fetchone()
            conn.commit()
        return dict(row) if row else None

    def get_group(self, user_id: str, group_id: str) -> dict[str, Any] | None:
        self.ensure_schema()
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                      id::text,
                      user_id::text,
                      title,
                      description,
                      pinned,
                      archived,
                      created_at,
                      updated_at
                    FROM chat_groups
                    WHERE id = %s
                      AND user_id = %s
                    """,
                    [group_id, user_id],
                )
                row = cur.fetchone()
        return dict(row) if row else None

    def create_conversation(
        self,
        user_id: str,
        title: str = "新会话",
        group_id: str | None = None,
    ) -> dict[str, Any]:
        self.ensure_schema()
        if group_id and not self.get_group(user_id, group_id):
            raise ValueError("chat group not found")
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO chat_conversations (user_id, group_id, title)
                    VALUES (%s, %s, %s)
                    RETURNING
                      id::text,
                      user_id::text,
                      group_id::text,
                      title,
                      summary,
                      status,
                      last_message_at,
                      created_at,
                      updated_at
                    """,
                    [user_id, group_id, title.strip() or "新会话"],
                )
                row = dict(cur.fetchone())
            conn.commit()
        return row

    def list_conversations(
        self,
        user_id: str,
        group_id: str | None = None,
        status: str = "active",
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        self.ensure_schema()
        limit = max(1, min(limit, 100))
        offset = max(0, offset)
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                      id::text,
                      user_id::text,
                      group_id::text,
                      title,
                      summary,
                      status,
                      last_message_at,
                      created_at,
                      updated_at
                    FROM chat_conversations
                    WHERE user_id = %s
                      AND (%s = '' OR group_id = %s)
                      AND (%s = '' OR status = %s)
                    ORDER BY COALESCE(last_message_at, updated_at, created_at) DESC
                    LIMIT %s OFFSET %s
                    """,
                    [user_id, group_id or "", group_id, status, status, limit, offset],
                )
                rows = [dict(row) for row in cur.fetchall()]
        return rows

    def get_conversation(self, user_id: str, conversation_id: str) -> dict[str, Any] | None:
        self.ensure_schema()
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                      id::text,
                      user_id::text,
                      group_id::text,
                      title,
                      summary,
                      status,
                      last_message_at,
                      created_at,
                      updated_at
                    FROM chat_conversations
                    WHERE id = %s
                      AND user_id = %s
                    """,
                    [conversation_id, user_id],
                )
                row = cur.fetchone()
        return dict(row) if row else None

    def update_conversation(
        self,
        user_id: str,
        conversation_id: str,
        updates: dict[str, Any],
    ) -> dict[str, Any] | None:
        self.ensure_schema()
        allowed = {"title": str, "summary": str, "status": str, "group_id": str}
        assignments = []
        values: list[Any] = []
        for key, expected_type in allowed.items():
            if key not in updates:
                continue
            value = updates[key]
            if key == "group_id" and value in {"", None}:
                value = None
            elif expected_type is str:
                value = str(value)
            assignments.append(f"{key} = %s")
            values.append(value)
        if not assignments:
            return self.get_conversation(user_id, conversation_id)
        values.extend([conversation_id, user_id])
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    UPDATE chat_conversations
                    SET {", ".join(assignments)},
                        updated_at = now()
                    WHERE id = %s
                      AND user_id = %s
                    RETURNING
                      id::text,
                      user_id::text,
                      group_id::text,
                      title,
                      summary,
                      status,
                      last_message_at,
                      created_at,
                      updated_at
                    """,
                    values,
                )
                row = cur.fetchone()
            conn.commit()
        return dict(row) if row else None

    def store_user_message(
        self,
        user_id: str,
        content: str,
        conversation_id: str | None = None,
        title_hint: str = "",
    ) -> StoredUserMessage:
        self.ensure_schema()
        if conversation_id:
            conversation = self.get_conversation(user_id, conversation_id)
            if not conversation:
                raise ValueError("conversation not found")
        else:
            conversation = self.create_conversation(
                user_id,
                title=self._title_from_content(title_hint or content),
            )
            conversation_id = conversation["id"]
        message_id = self.create_message(
            user_id=user_id,
            conversation_id=conversation_id,
            role="user",
            content=content,
            content_format="text",
            status="done",
        )["id"]
        return StoredUserMessage(conversation_id=conversation_id, message_id=message_id)

    def create_message(
        self,
        user_id: str,
        conversation_id: str,
        role: str,
        content: str,
        content_format: str = "markdown",
        status: str = "done",
        agent_run_id: str | None = None,
        parent_message_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.ensure_schema()
        if not self.get_conversation(user_id, conversation_id):
            raise ValueError("conversation not found")
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO chat_messages (
                      conversation_id,
                      user_id,
                      role,
                      content,
                      content_format,
                      status,
                      agent_run_id,
                      parent_message_id,
                      metadata_json
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING
                      id::text,
                      conversation_id::text,
                      user_id::text,
                      role,
                      content,
                      content_format,
                      status,
                      agent_run_id::text,
                      parent_message_id::text,
                      metadata_json,
                      created_at
                    """,
                    [
                        conversation_id,
                        user_id,
                        role,
                        content,
                        content_format,
                        status,
                        agent_run_id,
                        parent_message_id,
                        Jsonb(metadata or {}),
                    ],
                )
                message = dict(cur.fetchone())
                cur.execute(
                    """
                    UPDATE chat_conversations
                    SET last_message_at = now(),
                        updated_at = now()
                    WHERE id = %s
                    """,
                    [conversation_id],
                )
            conn.commit()
        return message

    def add_artifacts(self, message_id: str, artifacts: dict[str, list[dict[str, Any]]]) -> None:
        self.ensure_schema()
        rows: list[tuple[str, str, Jsonb]] = []
        for artifact_type, items in artifacts.items():
            if artifact_type not in {"event", "reference", "link", "trace", "table", "metadata"}:
                continue
            for item in items:
                rows.append((message_id, artifact_type, Jsonb(item)))
        if not rows:
            return
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.executemany(
                    """
                    INSERT INTO chat_message_artifacts (
                      message_id,
                      artifact_type,
                      payload_json
                    )
                    VALUES (%s, %s, %s)
                    """,
                    rows,
                )
            conn.commit()

    def list_messages(
        self,
        user_id: str,
        conversation_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        self.ensure_schema()
        if not self.get_conversation(user_id, conversation_id):
            raise ValueError("conversation not found")
        limit = max(1, min(limit, 200))
        offset = max(0, offset)
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                      id::text,
                      conversation_id::text,
                      user_id::text,
                      role,
                      content,
                      content_format,
                      status,
                      agent_run_id::text,
                      parent_message_id::text,
                      metadata_json,
                      created_at
                    FROM chat_messages
                    WHERE conversation_id = %s
                      AND user_id = %s
                    ORDER BY created_at, id
                    LIMIT %s OFFSET %s
                    """,
                    [conversation_id, user_id, limit, offset],
                )
                messages = [dict(row) for row in cur.fetchall()]
                ids = [message["id"] for message in messages]
                artifacts_by_message: dict[str, dict[str, list[dict[str, Any]]]] = {
                    message_id: {} for message_id in ids
                }
                if ids:
                    cur.execute(
                        """
                        SELECT
                          message_id::text,
                          artifact_type,
                          payload_json
                        FROM chat_message_artifacts
                        WHERE message_id = ANY(%s::uuid[])
                        ORDER BY created_at, id
                        """,
                        [ids],
                    )
                    for row in cur.fetchall():
                        artifact_groups = artifacts_by_message.setdefault(row["message_id"], {})
                        artifact_groups.setdefault(row["artifact_type"], []).append(
                            dict(row["payload_json"])
                        )
        for message in messages:
            message["artifacts"] = artifacts_by_message.get(message["id"], {})
        return messages

    def bind_agent_run(
        self,
        run_id: str,
        user_id: str,
        conversation_id: str,
        input_message_id: str | None = None,
        output_message_id: str | None = None,
    ) -> None:
        self.ensure_schema()
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE agent_runs
                    SET user_id = %s,
                        conversation_id = %s,
                        input_message_id = COALESCE(%s, input_message_id),
                        output_message_id = COALESCE(%s, output_message_id)
                    WHERE id = %s
                    """,
                    [user_id, conversation_id, input_message_id, output_message_id, run_id],
                )
            conn.commit()

    def _title_from_content(self, content: str) -> str:
        title = " ".join(content.strip().split())
        return title[:32] or "新会话"
