from __future__ import annotations

import argparse
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agent.models.factory import build_model_adapter
from agent.runtime.observability import AgentTelemetry
from agent.runtime.queue import AgentRunQueue
from agent.runtime.recorder import AgentRunRecorder
from agent.runtime.workflow import build_agent_workflow
from apps.api.settings import AppSettings
from knowledge.service import KnowledgeService
from tools.database.postgres import PostgresClient
from tools.historical.postgres_repository import PostgresHistoricalEventRepository
from tools.historical.repository import HistoricalEventRepository
from tools.historical.service import HistoricalQueryService
from tools.historical.tool_registry import build_historical_tool_registry


ROOT_DIR = Path(__file__).resolve().parents[2]
SAMPLE_DATA_PATH = ROOT_DIR / "data" / "samples" / "events_600_900_sample.json"


@dataclass(frozen=True)
class WorkerResult:
    processed: bool
    run_id: str | None = None
    status: str = "idle"
    error: str = ""
    queue_action: str = ""
    attempts: int = 0
    dead_lettered: bool = False


class AgentWorker:
    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings
        self.recorder = AgentRunRecorder(settings.postgres)
        self.queue = AgentRunQueue(self.recorder, settings.queue)
        self.agent = build_agent_workflow(
            workflow_engine=settings.agent_runtime.workflow_engine,
            model_adapter=build_model_adapter(settings.model),
            tool_registry=build_historical_tool_registry(
                self._build_query_service(),
                knowledge_service=KnowledgeService(settings.postgres),
            ),
            recorder=self.recorder,
            telemetry=AgentTelemetry(settings.observability),
        )

    def process_one(self) -> WorkerResult:
        self.queue.recover_stale()
        claimed = self.queue.claim_next()
        if not claimed:
            return WorkerResult(processed=False)

        run_id = str(claimed["id"])
        try:
            self.agent.resume_existing(run_id)
        except Exception as exc:
            failure = self.queue.fail(run_id, str(exc))
            return WorkerResult(
                processed=True,
                run_id=run_id,
                status="failed",
                error=str(exc),
                queue_action=str(failure.get("action", "")),
                attempts=int(failure.get("attempts", 0)),
                dead_lettered=bool(failure.get("dead_lettered", False)),
            )
        self.queue.complete(run_id)
        return WorkerResult(processed=True, run_id=run_id, status="completed")

    def recover_stale(self) -> dict[str, Any]:
        return self.queue.recover_stale()

    def _build_query_service(self) -> HistoricalQueryService:
        postgres_client = PostgresClient(self.settings.postgres)
        if postgres_client.health_check().ok:
            repository = PostgresHistoricalEventRepository(self.settings.postgres)
        else:
            repository = HistoricalEventRepository.from_json(
                SAMPLE_DATA_PATH
            )
        return HistoricalQueryService(repository)


def main() -> None:
    parser = argparse.ArgumentParser(description="Historical Agent worker")
    parser.add_argument("--once", action="store_true", help="process one queued run and exit")
    parser.add_argument(
        "--recover-stale",
        action="store_true",
        help="recover stale processing runs and exit",
    )
    parser.add_argument("--sleep", type=float, default=1.0, help="idle sleep seconds")
    args = parser.parse_args()

    worker = AgentWorker(AppSettings.from_env())
    if args.recover_stale:
        print(worker.recover_stale(), flush=True)
        return

    while True:
        result = worker.process_one()
        print(_result_payload(result), flush=True)
        if args.once:
            return
        if not result.processed:
            time.sleep(args.sleep)


def _result_payload(result: WorkerResult) -> dict[str, Any]:
    return {
        "processed": result.processed,
        "run_id": result.run_id,
        "status": result.status,
        "error": result.error,
        "queue_action": result.queue_action,
        "attempts": result.attempts,
        "dead_lettered": result.dead_lettered,
    }


if __name__ == "__main__":
    main()
