from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Iterator

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from apps.api.settings import PostgresSettings


@dataclass(frozen=True)
class RecordedRun:
    run_id: str


class AgentRunRecorder:
    def __init__(self, settings: PostgresSettings) -> None:
        self.settings = settings

    @contextmanager
    def _connect(self) -> Iterator[psycopg.Connection]:
        with psycopg.connect(self.settings.dsn, row_factory=dict_row) as conn:
            yield conn

    def start_run(
        self,
        user_input: str,
        user_id: str = "",
        model_name: str = "deterministic-router",
        prompt_version: str = "historical-agent-v0",
        status: str = "running",
    ) -> RecordedRun:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO agent_runs (
                      user_id,
                      user_input,
                      status,
                      model_name,
                      prompt_version
                    )
                    VALUES (%s, %s, %s, %s, %s)
                    RETURNING id::text
                    """,
                    [user_id, user_input, status, model_name, prompt_version],
                )
                run_id = cur.fetchone()["id"]
            conn.commit()
        return RecordedRun(run_id=run_id)

    def create_pending_run(
        self,
        user_input: str,
        user_id: str = "",
        model_name: str = "deterministic-router",
        prompt_version: str = "historical-agent-loop-v1",
    ) -> RecordedRun:
        return self.start_run(
            user_input=user_input,
            user_id=user_id,
            model_name=model_name,
            prompt_version=prompt_version,
            status="pending",
        )

    def claim_next_pending_run(self) -> dict[str, Any] | None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id::text, user_input, user_id, model_name, prompt_version
                    FROM agent_runs
                    WHERE status = 'pending'
                    ORDER BY started_at, id
                    FOR UPDATE SKIP LOCKED
                    LIMIT 1
                    """
                )
                row = cur.fetchone()
                if not row:
                    return None

                cur.execute(
                    """
                    UPDATE agent_runs
                    SET status = 'running',
                        error_message = NULL
                    WHERE id = %s
                    """,
                    [row["id"]],
                )
            conn.commit()
        return dict(row)

    def claim_pending_run(self, run_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE agent_runs
                    SET status = 'running',
                        error_message = NULL
                    WHERE id = %s
                      AND status = 'pending'
                    RETURNING
                      id::text,
                      user_input,
                      user_id,
                      model_name,
                      prompt_version
                    """,
                    [run_id],
                )
                row = cur.fetchone()
            conn.commit()
        return dict(row) if row else None

    def record_tool_step(
        self,
        run_id: str,
        step_index: int,
        tool_name: str,
        tool_arguments: dict[str, Any],
        tool_result: dict[str, Any],
        status: str = "completed",
        error_message: str | None = None,
        model_input_summary: str = "",
        model_output_summary: str = "",
        token_input: int = 0,
        token_output: int = 0,
    ) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO agent_steps (
                      run_id,
                      step_index,
                      step_type,
                      status,
                      tool_name,
                      tool_arguments,
                      tool_result,
                      model_input_summary,
                      model_output_summary,
                      error_message,
                      token_input,
                      token_output,
                      finished_at
                    )
                    VALUES (%s, %s, 'tool_call', %s, %s, %s, %s, %s, %s, %s, %s, %s, now())
                    ON CONFLICT (run_id, step_index) DO UPDATE SET
                      status = EXCLUDED.status,
                      tool_name = EXCLUDED.tool_name,
                      tool_arguments = EXCLUDED.tool_arguments,
                      tool_result = EXCLUDED.tool_result,
                      model_input_summary = EXCLUDED.model_input_summary,
                      model_output_summary = EXCLUDED.model_output_summary,
                      error_message = EXCLUDED.error_message,
                      token_input = EXCLUDED.token_input,
                      token_output = EXCLUDED.token_output,
                      finished_at = EXCLUDED.finished_at
                    """,
                    [
                        run_id,
                        step_index,
                        status,
                        tool_name,
                        Jsonb(self._json_safe(tool_arguments)),
                        Jsonb(self._json_safe(tool_result)),
                        model_input_summary,
                        model_output_summary,
                        error_message,
                        token_input,
                        token_output,
                    ],
                )
            conn.commit()

    def finish_run(self, run_id: str, final_answer: str) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE agent_runs
                    SET status = 'completed',
                        final_answer = %s,
                        finished_at = now()
                    WHERE id = %s
                      AND status = 'running'
                    """,
                    [final_answer, run_id],
                )
            conn.commit()

    def fail_run(self, run_id: str, error_message: str) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE agent_runs
                    SET status = 'failed',
                        error_message = %s,
                        finished_at = now()
                    WHERE id = %s
                    """,
                    [error_message, run_id],
                )
            conn.commit()

    def wait_for_user(self, run_id: str, message: str) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE agent_runs
                    SET status = 'waiting_for_user',
                        error_message = %s
                    WHERE id = %s
                      AND status = 'running'
                    """,
                    [message, run_id],
                )
            conn.commit()

    def mark_run_pending_for_retry(self, run_id: str, error_message: str) -> bool:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE agent_runs
                    SET status = 'pending',
                        error_message = %s,
                        finished_at = NULL
                    WHERE id = %s
                      AND status = 'failed'
                    RETURNING id::text
                    """,
                    [error_message, run_id],
                )
                marked = cur.fetchone() is not None
            conn.commit()
        return marked

    def mark_running_run_pending_after_timeout(
        self,
        run_id: str,
        error_message: str,
    ) -> bool:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE agent_runs
                    SET status = 'pending',
                        error_message = %s,
                        finished_at = NULL
                    WHERE id = %s
                      AND status = 'running'
                    RETURNING id::text
                    """,
                    [error_message, run_id],
                )
                marked = cur.fetchone() is not None
            conn.commit()
        return marked

    def cancel_run(self, run_id: str, reason: str = "Cancelled by user") -> bool:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE agent_runs
                    SET status = 'cancelled',
                        error_message = %s,
                        finished_at = now()
                    WHERE id = %s
                      AND status IN ('pending', 'running', 'waiting_for_user')
                    RETURNING id::text
                    """,
                    [reason, run_id],
                )
                cancelled = cur.fetchone() is not None
            conn.commit()
        return cancelled

    def is_cancelled(self, run_id: str) -> bool:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT status::text
                    FROM agent_runs
                    WHERE id = %s
                    """,
                    [run_id],
                )
                row = cur.fetchone()
        return bool(row and row["status"] == "cancelled")

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                      id::text,
                      user_id,
                      user_input,
                      status::text,
                      final_answer,
                      error_message,
                      model_name,
                      prompt_version,
                      started_at,
                      finished_at
                    FROM agent_runs
                    WHERE id = %s
                    """,
                    [run_id],
                )
                run = cur.fetchone()
                if not run:
                    return None

                cur.execute(
                    """
                    SELECT
                      id::text,
                      step_index,
                      step_type,
                      status::text,
                      tool_name,
                      tool_arguments,
                      tool_result,
                      model_input_summary,
                      model_output_summary,
                      error_message,
                      token_input,
                      token_output,
                      started_at,
                      finished_at
                    FROM agent_steps
                    WHERE run_id = %s
                    ORDER BY step_index
                    """,
                    [run_id],
                )
                steps = list(cur.fetchall())

        result = dict(run)
        result["steps"] = [dict(step) for step in steps]
        return result

    def _json_safe(self, value: Any) -> Any:
        if isinstance(value, Decimal):
            return float(value)
        if isinstance(value, (datetime, date)):
            return value.isoformat()
        if isinstance(value, dict):
            return {key: self._json_safe(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self._json_safe(item) for item in value]
        if isinstance(value, tuple):
            return [self._json_safe(item) for item in value]
        return value
