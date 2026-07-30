from __future__ import annotations

import argparse
import time
from dataclasses import dataclass
from typing import Any

from apps.api.settings import AppSettings
from knowledge.service import KnowledgeService


@dataclass(frozen=True)
class VectorWorkerResult:
    processed: bool
    job_id: str | None = None
    status: str = "idle"
    error: str = ""


class VectorWorker:
    def __init__(self, settings: AppSettings) -> None:
        self.knowledge = KnowledgeService(settings.postgres)

    def process_one(self) -> VectorWorkerResult:
        result = self.knowledge.process_next_vector_rebuild_job()
        job = result.get("job") if isinstance(result.get("job"), dict) else None
        if not result.get("processed"):
            return VectorWorkerResult(
                processed=False,
                job_id=str(job.get("id")) if job else None,
                status=str(result.get("status", "idle")),
                error=str(result.get("error", "")),
            )
        return VectorWorkerResult(
            processed=True,
            job_id=str(job.get("id")) if job else None,
            status=str(job.get("status", "completed")) if job else "completed",
            error=str(result.get("error", "")),
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Historical vector rebuild worker")
    parser.add_argument("--once", action="store_true", help="process one pending vector job and exit")
    parser.add_argument("--sleep", type=float, default=1.0, help="idle sleep seconds")
    args = parser.parse_args()

    worker = VectorWorker(AppSettings.from_env())
    while True:
        result = worker.process_one()
        print(_result_payload(result), flush=True)
        if args.once:
            return
        if not result.processed:
            time.sleep(args.sleep)


def _result_payload(result: VectorWorkerResult) -> dict[str, Any]:
    return {
        "processed": result.processed,
        "job_id": result.job_id,
        "status": result.status,
        "error": result.error,
    }


if __name__ == "__main__":
    main()
