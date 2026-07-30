from __future__ import annotations

from pathlib import Path

from agent.runtime.queue import AgentRunQueue
from agent.runtime.recorder import AgentRunRecorder
from agent.runtime.observability import AgentTelemetry
from apps.api.settings import AppSettings
from knowledge.service import KnowledgeService
from tools.database.postgres import PostgresClient
from tools.historical.event_management import EventManagementService
from tools.historical.import_review import ImportReviewService
from tools.historical.postgres_repository import PostgresHistoricalEventRepository
from tools.historical.repository import HistoricalEventRepository
from tools.historical.service import HistoricalQueryService
from tools.historical.tool_registry import build_historical_tool_registry


ROOT_DIR = Path(__file__).resolve().parents[2]
SAMPLE_DATA_PATH = ROOT_DIR / "data" / "samples" / "events_600_900_sample.json"

settings = AppSettings.from_env()
postgres_client = PostgresClient(settings.postgres)

if postgres_client.health_check().ok:
    repository = PostgresHistoricalEventRepository(settings.postgres)
    data_source = "postgres"
else:
    repository = HistoricalEventRepository.from_json(SAMPLE_DATA_PATH)
    data_source = "json"

service = HistoricalQueryService(repository)
recorder = AgentRunRecorder(settings.postgres)
telemetry = AgentTelemetry(settings.observability)
agent_queue = AgentRunQueue(recorder, settings.queue)
import_review_service = ImportReviewService(settings.postgres)
event_management_service = EventManagementService(settings.postgres, settings.security)
knowledge_service = KnowledgeService(settings.postgres)
tool_registry = build_historical_tool_registry(
    service,
    knowledge_service=knowledge_service,
    enable_confirmation_probe=settings.agent_runtime.enable_confirmation_probe,
)
