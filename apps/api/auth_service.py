from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Iterator

import psycopg
from psycopg.rows import dict_row

from apps.api.settings import PostgresSettings


SESSION_COOKIE_NAME = "historical_agent_session"


@dataclass(frozen=True)
class AuthenticatedSession:
    token: str
    expires_at: datetime
    user: dict[str, Any]


class AuthService:
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

    def register(
        self,
        username: str,
        password: str,
        email: str = "",
        display_name: str = "",
    ) -> dict[str, Any]:
        self.ensure_schema()
        username = username.strip()
        email = email.strip()
        display_name = display_name.strip() or username
        if len(username) < 3:
            raise ValueError("username must be at least 3 characters")
        if len(password) < 6:
            raise ValueError("password must be at least 6 characters")
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO users (username, email, display_name, password_hash)
                    VALUES (%s, %s, %s, %s)
                    RETURNING
                      id::text,
                      username,
                      email,
                      display_name,
                      status,
                      role,
                      created_at,
                      updated_at,
                      last_login_at
                    """,
                    [username, email, display_name, self._hash_password(password)],
                )
                user = dict(cur.fetchone())
            conn.commit()
        return user

    def login(
        self,
        username_or_email: str,
        password: str,
        user_agent: str = "",
        ip_address: str = "",
    ) -> AuthenticatedSession:
        self.ensure_schema()
        identity = username_or_email.strip()
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                      id::text,
                      username,
                      email,
                      display_name,
                      password_hash,
                      status,
                      role,
                      created_at,
                      updated_at,
                      last_login_at
                    FROM users
                    WHERE username = %s
                       OR lower(email) = lower(%s)
                    """,
                    [identity, identity],
                )
                row = cur.fetchone()
                if not row or row["status"] != "active":
                    raise ValueError("invalid username or password")
                if not self._verify_password(password, str(row["password_hash"])):
                    raise ValueError("invalid username or password")

                token = secrets.token_urlsafe(32)
                expires_at = datetime.now(UTC) + timedelta(days=14)
                cur.execute(
                    """
                    INSERT INTO user_sessions (
                      user_id,
                      session_token_hash,
                      expires_at,
                      user_agent,
                      ip_address,
                      last_seen_at
                    )
                    VALUES (%s, %s, %s, %s, %s, now())
                    """,
                    [
                        row["id"],
                        self._hash_token(token),
                        expires_at,
                        user_agent[:512],
                        ip_address[:128],
                    ],
                )
                cur.execute(
                    """
                    UPDATE users
                    SET last_login_at = now(),
                        updated_at = now()
                    WHERE id = %s
                    """,
                    [row["id"]],
                )
            conn.commit()
        user = self._public_user(dict(row))
        user["last_login_at"] = datetime.now(UTC)
        return AuthenticatedSession(token=token, expires_at=expires_at, user=user)

    def logout(self, token: str) -> bool:
        self.ensure_schema()
        if not token:
            return False
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE user_sessions
                    SET revoked_at = now()
                    WHERE session_token_hash = %s
                      AND revoked_at IS NULL
                    RETURNING id::text
                    """,
                    [self._hash_token(token)],
                )
                revoked = cur.fetchone() is not None
            conn.commit()
        return revoked

    def get_user_by_session(self, token: str) -> dict[str, Any] | None:
        self.ensure_schema()
        if not token:
            return None
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                      u.id::text,
                      u.username,
                      u.email,
                      u.display_name,
                      u.status,
                      u.role,
                      u.created_at,
                      u.updated_at,
                      u.last_login_at
                    FROM user_sessions s
                    JOIN users u ON u.id = s.user_id
                    WHERE s.session_token_hash = %s
                      AND s.revoked_at IS NULL
                      AND s.expires_at > now()
                      AND u.status = 'active'
                    """,
                    [self._hash_token(token)],
                )
                row = cur.fetchone()
                if row:
                    cur.execute(
                        """
                        UPDATE user_sessions
                        SET last_seen_at = now()
                        WHERE session_token_hash = %s
                        """,
                        [self._hash_token(token)],
                    )
            conn.commit()
        return self._public_user(dict(row)) if row else None

    def _hash_password(self, password: str) -> str:
        salt = secrets.token_bytes(16)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 210_000)
        return "pbkdf2_sha256$210000${}${}".format(
            base64.b64encode(salt).decode("ascii"),
            base64.b64encode(digest).decode("ascii"),
        )

    def _verify_password(self, password: str, encoded: str) -> bool:
        try:
            algorithm, iterations_text, salt_text, digest_text = encoded.split("$", maxsplit=3)
            if algorithm != "pbkdf2_sha256":
                return False
            salt = base64.b64decode(salt_text.encode("ascii"))
            expected = base64.b64decode(digest_text.encode("ascii"))
            actual = hashlib.pbkdf2_hmac(
                "sha256",
                password.encode("utf-8"),
                salt,
                int(iterations_text),
            )
            return hmac.compare_digest(actual, expected)
        except Exception:
            return False

    def _hash_token(self, token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def _public_user(self, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": row["id"],
            "username": row["username"],
            "email": row.get("email") or "",
            "display_name": row.get("display_name") or row["username"],
            "status": row["status"],
            "role": row["role"],
            "created_at": row.get("created_at"),
            "updated_at": row.get("updated_at"),
            "last_login_at": row.get("last_login_at"),
        }
