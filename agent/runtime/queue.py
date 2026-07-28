from __future__ import annotations

import socket
import time
from dataclasses import dataclass
from urllib.parse import urlparse
from typing import Any

from apps.api.settings import QueueSettings
from agent.runtime.recorder import AgentRunRecorder


@dataclass(frozen=True)
class QueuedAgentRun:
    run_id: str
    status: str
    queue_backend: str = "postgres"


class AgentRunQueue:
    def __init__(
        self,
        recorder: AgentRunRecorder,
        settings: QueueSettings | None = None,
    ) -> None:
        self.recorder = recorder
        self.settings = settings or QueueSettings()
        self.redis = SimpleRedisClient.from_url(self.settings.redis_url)
        self.processing_queue_name = f"{self.settings.queue_name}:processing"
        self.dead_queue_name = f"{self.settings.queue_name}:dead"
        self.attempts_hash_name = f"{self.settings.queue_name}:attempts"
        self.claimed_at_hash_name = f"{self.settings.queue_name}:claimed_at"

    def enqueue(
        self,
        user_input: str,
        user_id: str = "",
        model_name: str = "deterministic-router",
    ) -> QueuedAgentRun:
        recorded = self.recorder.create_pending_run(
            user_input=user_input,
            user_id=user_id,
            model_name=model_name,
            prompt_version="historical-agent-loop-v1",
        )
        backend = self._effective_backend()
        if backend == "redis":
            self.redis.lpush(self.settings.queue_name, recorded.run_id)
        return QueuedAgentRun(
            run_id=recorded.run_id,
            status="pending",
            queue_backend=backend,
        )

    def claim_next(self) -> dict[str, Any] | None:
        if self._effective_backend() == "redis":
            return self._claim_next_from_redis()
        return self.recorder.claim_next_pending_run()

    def complete(self, run_id: str) -> None:
        if self._effective_backend() != "redis":
            return
        self.redis.lrem(self.processing_queue_name, 0, run_id)
        self.redis.hdel(self.claimed_at_hash_name, run_id)
        self.redis.hdel(self.attempts_hash_name, run_id)

    def fail(self, run_id: str, error_message: str) -> dict[str, Any]:
        if self._effective_backend() != "redis":
            return {"action": "failed", "attempts": 0, "dead_lettered": False}

        attempts = self.redis.hincrby(self.attempts_hash_name, run_id, 1)
        self.redis.lrem(self.processing_queue_name, 0, run_id)
        self.redis.hdel(self.claimed_at_hash_name, run_id)
        if attempts <= self.settings.max_retries:
            marked = self.recorder.mark_run_pending_for_retry(run_id, error_message)
            if marked:
                self.redis.lpush(self.settings.queue_name, run_id)
                return {"action": "requeued", "attempts": attempts, "dead_lettered": False}

        self.redis.lpush(self.dead_queue_name, run_id)
        return {"action": "dead_lettered", "attempts": attempts, "dead_lettered": True}

    def recover_stale(self, now: int | None = None) -> dict[str, Any]:
        if self._effective_backend() != "redis":
            return {
                "recovered": 0,
                "dead_lettered": 0,
                "checked": 0,
                "backend": "postgres",
            }

        current_time = now or int(time.time())
        cutoff = current_time - self.settings.visibility_timeout_seconds
        recovered = 0
        dead_lettered = 0
        checked = 0
        for run_id in self.redis.lrange(self.processing_queue_name, 0, -1):
            checked += 1
            claimed_at_raw = self.redis.hget(self.claimed_at_hash_name, run_id)
            claimed_at = int(claimed_at_raw or "0")
            if claimed_at > cutoff:
                continue

            self.redis.lrem(self.processing_queue_name, 0, run_id)
            self.redis.hdel(self.claimed_at_hash_name, run_id)
            attempts = self.redis.hincrby(self.attempts_hash_name, run_id, 1)
            error_message = (
                "Agent run visibility timeout exceeded; recovered from processing queue."
            )
            if attempts <= self.settings.max_retries:
                marked = self.recorder.mark_running_run_pending_after_timeout(
                    run_id,
                    error_message,
                )
                if marked:
                    self.redis.lpush(self.settings.queue_name, run_id)
                    recovered += 1
                    continue

            self.recorder.fail_run(run_id, error_message)
            self.redis.lpush(self.dead_queue_name, run_id)
            dead_lettered += 1

        return {
            "recovered": recovered,
            "dead_lettered": dead_lettered,
            "checked": checked,
            "backend": "redis",
        }

    def health(self) -> dict[str, Any]:
        redis_ok = self.redis.ping()
        return {
            "configured_backend": self.settings.backend,
            "effective_backend": self._effective_backend(),
            "queue_name": self.settings.queue_name,
            "processing_queue_name": self.processing_queue_name,
            "dead_queue_name": self.dead_queue_name,
            "redis_url": self._safe_redis_url(),
            "redis_ok": redis_ok,
            "pending_count": self.redis.llen(self.settings.queue_name) if redis_ok else None,
            "processing_count": self.redis.llen(self.processing_queue_name) if redis_ok else None,
            "dead_count": self.redis.llen(self.dead_queue_name) if redis_ok else None,
            "max_retries": self.settings.max_retries,
            "visibility_timeout_seconds": self.settings.visibility_timeout_seconds,
        }

    def _claim_next_from_redis(self) -> dict[str, Any] | None:
        while True:
            run_id = self.redis.rpoplpush(
                self.settings.queue_name,
                self.processing_queue_name,
            )
            if run_id is None:
                return None
            claimed = self.recorder.claim_pending_run(run_id)
            if claimed:
                self.redis.hset(self.claimed_at_hash_name, run_id, str(int(time.time())))
                return claimed
            self.complete(run_id)

    def _effective_backend(self) -> str:
        if self.settings.backend == "redis" and self.redis.ping():
            return "redis"
        return "postgres"

    def _safe_redis_url(self) -> str:
        parsed = urlparse(self.settings.redis_url)
        if parsed.password:
            return self.settings.redis_url.replace(parsed.password, "***")
        return self.settings.redis_url


class SimpleRedisClient:
    def __init__(
        self,
        host: str = "localhost",
        port: int = 6379,
        password: str = "",
        db: int = 0,
        timeout: float = 1.0,
    ) -> None:
        self.host = host
        self.port = port
        self.password = password
        self.db = db
        self.timeout = timeout

    @classmethod
    def from_url(cls, url: str) -> "SimpleRedisClient":
        parsed = urlparse(url)
        return cls(
            host=parsed.hostname or "localhost",
            port=parsed.port or 6379,
            password=parsed.password or "",
            db=int((parsed.path or "/0").lstrip("/") or "0"),
        )

    def ping(self) -> bool:
        try:
            return self._command("PING") == "PONG"
        except OSError:
            return False

    def lpush(self, key: str, value: str) -> int:
        result = self._command("LPUSH", key, value)
        return int(result)

    def rpop(self, key: str) -> str | None:
        result = self._command("RPOP", key)
        return str(result) if result is not None else None

    def rpoplpush(self, source: str, destination: str) -> str | None:
        result = self._command("RPOPLPUSH", source, destination)
        return str(result) if result is not None else None

    def lrem(self, key: str, count: int, value: str) -> int:
        result = self._command("LREM", key, str(count), value)
        return int(result)

    def llen(self, key: str) -> int:
        result = self._command("LLEN", key)
        return int(result)

    def lrange(self, key: str, start: int, stop: int) -> list[str]:
        result = self._command("LRANGE", key, str(start), str(stop))
        return [str(item) for item in result]

    def hincrby(self, key: str, field: str, increment: int = 1) -> int:
        result = self._command("HINCRBY", key, field, str(increment))
        return int(result)

    def hset(self, key: str, field: str, value: str) -> int:
        result = self._command("HSET", key, field, value)
        return int(result)

    def hdel(self, key: str, field: str) -> int:
        result = self._command("HDEL", key, field)
        return int(result)

    def hget(self, key: str, field: str) -> str | None:
        result = self._command("HGET", key, field)
        return str(result) if result is not None else None

    def _command(self, *parts: str) -> Any:
        with socket.create_connection((self.host, self.port), timeout=self.timeout) as conn:
            if self.password:
                conn.sendall(self._encode("AUTH", self.password))
                self._read_response(conn)
            if self.db:
                conn.sendall(self._encode("SELECT", str(self.db)))
                self._read_response(conn)
            conn.sendall(self._encode(*parts))
            return self._read_response(conn)

    def _encode(self, *parts: str) -> bytes:
        payload = [f"*{len(parts)}\r\n".encode("utf-8")]
        for part in parts:
            encoded = str(part).encode("utf-8")
            payload.append(f"${len(encoded)}\r\n".encode("utf-8"))
            payload.append(encoded + b"\r\n")
        return b"".join(payload)

    def _read_response(self, conn: socket.socket) -> Any:
        prefix = conn.recv(1)
        if prefix == b"+":
            return self._read_line(conn)
        if prefix == b":":
            return int(self._read_line(conn))
        if prefix == b"$":
            length = int(self._read_line(conn))
            if length == -1:
                return None
            data = self._read_exact(conn, length)
            self._read_exact(conn, 2)
            return data.decode("utf-8")
        if prefix == b"*":
            length = int(self._read_line(conn))
            if length == -1:
                return []
            return [self._read_response(conn) for _ in range(length)]
        if prefix == b"-":
            raise OSError(self._read_line(conn))
        raise OSError("unexpected redis response")

    def _read_line(self, conn: socket.socket) -> str:
        data = bytearray()
        while not data.endswith(b"\r\n"):
            chunk = conn.recv(1)
            if not chunk:
                raise OSError("redis connection closed")
            data.extend(chunk)
        return data[:-2].decode("utf-8")

    def _read_exact(self, conn: socket.socket, length: int) -> bytes:
        data = bytearray()
        while len(data) < length:
            chunk = conn.recv(length - len(data))
            if not chunk:
                raise OSError("redis connection closed")
            data.extend(chunk)
        return bytes(data)
