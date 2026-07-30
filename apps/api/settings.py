from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class PostgresSettings:
    host: str = "localhost"
    port: int = 5432
    database: str = "historical_agent"
    user: str = "postgres"
    password: str = "admin"

    @classmethod
    def from_env(cls) -> "PostgresSettings":
        return cls(
            host=os.getenv("POSTGRES_HOST", "localhost"),
            port=int(os.getenv("POSTGRES_PORT", "5432")),
            database=os.getenv("POSTGRES_DB", "historical_agent"),
            user=os.getenv("POSTGRES_USER", "postgres"),
            password=os.getenv("POSTGRES_PASSWORD", "admin"),
        )

    @property
    def dsn(self) -> str:
        return (
            f"host={self.host} port={self.port} dbname={self.database} "
            f"user={self.user} password={self.password}"
        )

    @property
    def safe_dsn(self) -> str:
        return (
            f"host={self.host} port={self.port} dbname={self.database} "
            f"user={self.user} password=***"
        )


@dataclass(frozen=True)
class ModelSettings:
    provider: str = "rule_based"
    model: str = "gpt-4.1-mini"
    api_key: str = ""
    base_url: str = ""
    temperature: float = 0.0

    @classmethod
    def from_env(cls) -> "ModelSettings":
        return cls(
            provider=os.getenv("MODEL_PROVIDER", "rule_based"),
            model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
            api_key=os.getenv("OPENAI_API_KEY", ""),
            base_url=os.getenv("OPENAI_BASE_URL", ""),
            temperature=float(os.getenv("MODEL_TEMPERATURE", "0")),
        )


@dataclass(frozen=True)
class SecuritySettings:
    admin_api_token: str = "admin"

    @classmethod
    def from_env(cls) -> "SecuritySettings":
        return cls(admin_api_token=os.getenv("ADMIN_API_TOKEN", "admin"))


@dataclass(frozen=True)
class QueueSettings:
    backend: str = "redis"
    redis_url: str = "redis://localhost:6379/0"
    queue_name: str = "historical-agent-runs"
    max_retries: int = 3
    visibility_timeout_seconds: int = 300

    @classmethod
    def from_env(cls) -> "QueueSettings":
        return cls(
            backend=os.getenv("QUEUE_BACKEND", "redis"),
            redis_url=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
            queue_name=os.getenv("AGENT_QUEUE_NAME", "historical-agent-runs"),
            max_retries=int(os.getenv("AGENT_QUEUE_MAX_RETRIES", "3")),
            visibility_timeout_seconds=int(
                os.getenv("AGENT_QUEUE_VISIBILITY_TIMEOUT_SECONDS", "300")
            ),
        )


@dataclass(frozen=True)
class ObservabilitySettings:
    langfuse_enabled: bool = False
    langfuse_host: str = ""
    langfuse_base_url: str = ""
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_trace_url_template: str = ""

    @classmethod
    def from_env(cls) -> "ObservabilitySettings":
        enabled = os.getenv("LANGFUSE_ENABLED", "false").lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        base_url = os.getenv("LANGFUSE_BASE_URL", "").rstrip("/")
        host = os.getenv("LANGFUSE_HOST", "").rstrip("/")
        return cls(
            langfuse_enabled=enabled,
            langfuse_host=host,
            langfuse_base_url=base_url or host,
            langfuse_public_key=os.getenv("LANGFUSE_PUBLIC_KEY", ""),
            langfuse_secret_key=os.getenv("LANGFUSE_SECRET_KEY", ""),
            langfuse_trace_url_template=os.getenv("LANGFUSE_TRACE_URL_TEMPLATE", ""),
        )


@dataclass(frozen=True)
class AgentRuntimeSettings:
    workflow_engine: str = "loop"

    @classmethod
    def from_env(cls) -> "AgentRuntimeSettings":
        return cls(workflow_engine=os.getenv("AGENT_WORKFLOW_ENGINE", "loop"))


@dataclass(frozen=True)
class AppSettings:
    postgres: PostgresSettings
    model: ModelSettings
    security: SecuritySettings
    queue: QueueSettings
    observability: ObservabilitySettings
    agent_runtime: AgentRuntimeSettings

    @classmethod
    def from_env(cls) -> "AppSettings":
        return cls(
            postgres=PostgresSettings.from_env(),
            model=ModelSettings.from_env(),
            security=SecuritySettings.from_env(),
            queue=QueueSettings.from_env(),
            observability=ObservabilitySettings.from_env(),
            agent_runtime=AgentRuntimeSettings.from_env(),
        )
