from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import asdict, dataclass
from typing import Any

from apps.api.settings import PostgresSettings


@dataclass(frozen=True)
class PostgresHealth:
    ok: bool
    method: str
    database: str
    user: str
    host: str
    port: int
    message: str
    server_version: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class PostgresClient:
    """Small connection helper used before the final ORM/table design is settled."""

    def __init__(self, settings: PostgresSettings) -> None:
        self.settings = settings

    def health_check(self) -> PostgresHealth:
        psycopg_result = self._health_check_with_psycopg()
        if psycopg_result is not None:
            return psycopg_result
        return self._health_check_with_psql()

    def _health_check_with_psycopg(self) -> PostgresHealth | None:
        try:
            import psycopg  # type: ignore[import-not-found]
        except ImportError:
            return None

        try:
            with psycopg.connect(self.settings.dsn, connect_timeout=5) as conn:
                with conn.cursor() as cursor:
                    cursor.execute("select current_database(), current_user, version()")
                    database, user, version = cursor.fetchone()
        except Exception as exc:
            return self._failed("psycopg", str(exc))

        return PostgresHealth(
            ok=True,
            method="psycopg",
            database=database,
            user=user,
            host=self.settings.host,
            port=self.settings.port,
            message="connected",
            server_version=version,
        )

    def _health_check_with_psql(self) -> PostgresHealth:
        psql_path = shutil.which("psql")
        if not psql_path:
            return self._failed(
                "psql",
                "psycopg is not installed and psql was not found on PATH",
            )

        env = os.environ.copy()
        env["PGPASSWORD"] = self.settings.password
        command = [
            psql_path,
            "-h",
            self.settings.host,
            "-p",
            str(self.settings.port),
            "-U",
            self.settings.user,
            "-d",
            self.settings.database,
            "-t",
            "-A",
            "-c",
            "select current_database() || '|' || current_user || '|' || version();",
        ]
        try:
            result = subprocess.run(
                command,
                env=env,
                check=False,
                capture_output=True,
                text=True,
                timeout=10,
            )
        except Exception as exc:
            return self._failed("psql", str(exc))

        if result.returncode != 0:
            return self._failed("psql", result.stderr.strip() or result.stdout.strip())

        database, user, version = result.stdout.strip().split("|", maxsplit=2)
        return PostgresHealth(
            ok=True,
            method="psql",
            database=database,
            user=user,
            host=self.settings.host,
            port=self.settings.port,
            message="connected",
            server_version=version,
        )

    def _failed(self, method: str, message: str) -> PostgresHealth:
        return PostgresHealth(
            ok=False,
            method=method,
            database=self.settings.database,
            user=self.settings.user,
            host=self.settings.host,
            port=self.settings.port,
            message=message,
        )

