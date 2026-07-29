import json
from pathlib import Path
import json
from typing import Annotated, Iterable, Iterator

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from apps.api.settings import AppSettings
from agent.models.factory import build_model_adapter
from agent.runtime.loop import AgentLoop
from agent.runtime.queue import AgentRunQueue
from agent.runtime.recorder import AgentRunRecorder
from apps.worker.agent_worker import AgentWorker
from knowledge.service import KnowledgeService
from tools.historical.event_management import EventManagementService
from tools.historical.postgres_repository import PostgresHistoricalEventRepository
from tools.historical.import_review import ImportReviewService
from tools.historical.repository import HistoricalEventRepository
from tools.historical.service import HistoricalQueryService
from tools.historical.tool_registry import build_historical_tool_registry
from tools.database.postgres import PostgresClient


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
agent_queue = AgentRunQueue(recorder, settings.queue)
import_review_service = ImportReviewService(settings.postgres)
event_management_service = EventManagementService(settings.postgres, settings.security)
knowledge_service = KnowledgeService(settings.postgres)
tool_registry = build_historical_tool_registry(service)

app = FastAPI(
    title="Historical Timeline Agent API",
    description="Query and compare historical events across regions and time periods.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5174",
        "http://127.0.0.1:5175",
        "http://localhost:5173",
        "http://localhost:5174",
        "http://localhost:5175",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str | int]:
    payload: dict[str, str | int] = {"status": "ok", "data_source": data_source}
    if isinstance(repository, HistoricalEventRepository):
        payload["events"] = len(repository.events)
    return payload


@app.get("/health/db")
def database_health() -> dict:
    return postgres_client.health_check().to_dict()


@app.get("/events/year/{year}")
def search_events_by_year(
    year: int,
    regions: Annotated[list[str] | None, Query()] = None,
    polities: Annotated[list[str] | None, Query()] = None,
    categories: Annotated[list[str] | None, Query()] = None,
    limit: int = 50,
    nearby_window: int = 0,
) -> dict:
    return service.search_events_by_year(
        year=year,
        regions=regions,
        polities=polities,
        categories=categories,
        limit=limit,
        nearby_window=nearby_window,
    )


@app.get("/events/range")
def search_events_by_range(
    start_year: int,
    end_year: int,
    regions: Annotated[list[str] | None, Query()] = None,
    polities: Annotated[list[str] | None, Query()] = None,
    categories: Annotated[list[str] | None, Query()] = None,
    limit: int = 100,
) -> dict:
    return service.search_events_by_range(
        start_year=start_year,
        end_year=end_year,
        regions=regions,
        polities=polities,
        categories=categories,
        limit=limit,
    )


@app.get("/events/{event_id}")
def get_event_detail(event_id: str) -> dict:
    return service.get_event_detail(event_id)


@app.get("/events/{event_id}/contemporary")
def find_contemporary_events(
    event_id: str,
    window_years: int = 10,
    regions: Annotated[list[str] | None, Query()] = None,
    limit: int = 50,
) -> dict:
    return service.find_contemporary_events(
        event_id=event_id,
        window_years=window_years,
        regions=regions,
        limit=limit,
    )


@app.get("/events/{event_id}/relations")
def find_related_events(
    event_id: str,
    relation_types: Annotated[list[str] | None, Query()] = None,
    limit: int = 20,
) -> dict:
    return service.find_related_events(
        event_id=event_id,
        relation_types=relation_types,
        limit=limit,
    )


@app.get("/compare/regions")
def compare_regions(
    start_year: int,
    end_year: int,
    regions: Annotated[list[str], Query()],
    categories: Annotated[list[str] | None, Query()] = None,
) -> dict:
    return service.compare_regions(
        start_year=start_year,
        end_year=end_year,
        regions=regions,
        categories=categories,
    )


@app.post("/agent/query")
def query_agent(payload: dict) -> dict:
    user_input = str(payload.get("input", ""))
    agent = AgentLoop(
        model_adapter=build_model_adapter(settings.model),
        tool_registry=tool_registry,
        recorder=recorder,
    )
    response = agent.run(user_input)
    return {
        "run_id": response.run_id,
        "answer": response.answer,
        "steps": [
            {
                "tool_name": step.tool_name,
                "tool_arguments": step.tool_arguments,
                "observation": step.observation,
            }
            for step in response.steps
        ],
    }


@app.post("/agent/query/async")
def enqueue_agent_query(payload: dict) -> dict:
    user_input = str(payload.get("input", ""))
    user_id = str(payload.get("user_id", ""))
    queued = agent_queue.enqueue(
        user_input=user_input,
        user_id=user_id,
        model_name=build_model_adapter(settings.model).model_name,
    )
    return {
        "run_id": queued.run_id,
        "status": queued.status,
        "queue_backend": queued.queue_backend,
        "queued": True,
    }


@app.post("/agent/query/stream")
def query_agent_stream(payload: dict) -> StreamingResponse:
    user_input = str(payload.get("input", ""))
    agent = AgentLoop(
        model_adapter=build_model_adapter(settings.model),
        tool_registry=tool_registry,
        recorder=recorder,
    )
    return StreamingResponse(
        _sse_events(agent.stream(user_input)),
        media_type="text/event-stream",
    )


@app.get("/agent/runs/{run_id}")
def get_agent_run(run_id: str) -> dict:
    run = recorder.get_run(run_id)
    if not run:
        return {"found": False, "run_id": run_id}
    run["found"] = True
    return run


@app.get("/agent/queue/health")
def agent_queue_health() -> dict:
    return agent_queue.health()


@app.post("/agent/runs/{run_id}/cancel")
def cancel_agent_run(run_id: str, payload: dict | None = None) -> dict:
    reason = "Cancelled by user"
    if payload:
        reason = str(payload.get("reason", reason))
    cancelled = recorder.cancel_run(run_id, reason)
    return {
        "run_id": run_id,
        "cancelled": cancelled,
        "status": "cancelled" if cancelled else "unchanged",
    }


@app.post("/agent/queue/process-one")
def process_one_queued_agent_run() -> dict:
    result = AgentWorker(settings).process_one()
    return {
        "processed": result.processed,
        "run_id": result.run_id,
        "status": result.status,
        "error": result.error,
        "queue_action": result.queue_action,
        "attempts": result.attempts,
        "dead_lettered": result.dead_lettered,
    }


@app.post("/agent/queue/recover-stale")
def recover_stale_agent_runs() -> dict:
    return agent_queue.recover_stale()


@app.post("/imports/batches")
def create_import_batch(payload: dict) -> dict:
    events = payload.get("events", [])
    if not isinstance(events, list):
        return {"created": False, "error": "events must be a list"}
    batch = import_review_service.create_batch(
        filename=str(payload.get("filename", "manual-import.json")),
        source_note=str(payload.get("source_note", "")),
        created_by=str(payload.get("created_by", "")),
        events=events,
    )
    batch["created"] = True
    return batch


@app.post("/imports/parse")
def parse_import_events(payload: dict) -> dict:
    content = payload.get("content", "")
    if not isinstance(content, str):
        content = json.dumps(content, ensure_ascii=False)
    return import_review_service.parse_events(
        content=content,
        input_format=str(payload.get("input_format", "json")),
    )


@app.get("/imports/batches")
def list_import_batches(
    status: str | None = None,
    created_by: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    return import_review_service.list_batches(
        status=status,
        created_by=created_by,
        limit=limit,
        offset=offset,
    )


@app.get("/imports/batches/{batch_id}")
def get_import_batch(batch_id: str) -> dict:
    batch = import_review_service.get_batch(batch_id)
    if not batch:
        return {"found": False, "batch_id": batch_id}
    batch["found"] = True
    return batch


@app.get("/imports/batches/{batch_id}/staging")
def get_import_staging_rows(batch_id: str) -> dict:
    return import_review_service.list_staging_rows(batch_id)


@app.get("/imports/batches/{batch_id}/preview")
def preview_import_batch(batch_id: str) -> dict:
    return import_review_service.preview_batch(batch_id)


@app.patch("/imports/staging/{row_id}")
def update_import_staging_row(row_id: str, payload: dict) -> dict:
    raw_payload = payload.get("raw_payload", payload.get("event"))
    if not isinstance(raw_payload, dict):
        return {"updated": False, "error": "raw_payload must be an object"}
    return import_review_service.update_staging_row(row_id, raw_payload)


@app.post("/imports/staging/{row_id}/merge")
def merge_import_staging_row(row_id: str, payload: dict) -> dict:
    return import_review_service.merge_staging_row(
        row_id=row_id,
        strategy=str(payload.get("strategy", "")),
        target_event_id=str(payload.get("target_event_id", "")),
    )


@app.post("/imports/staging/bulk-revalidate")
def bulk_revalidate_import_staging(payload: dict) -> dict:
    row_ids = payload.get("row_ids")
    batch_id = payload.get("batch_id")
    if row_ids is not None and not isinstance(row_ids, list):
        return {"success": False, "error": "row_ids must be a list"}
    return import_review_service.bulk_revalidate_staging(
        row_ids=row_ids,
        batch_id=str(batch_id) if batch_id else None,
    )


@app.post("/imports/batches/{batch_id}/revalidate")
def revalidate_import_batch(batch_id: str) -> dict:
    return import_review_service.revalidate_batch(batch_id)


@app.post("/imports/batches/{batch_id}/confirm")
def confirm_import_batch(batch_id: str, payload: dict | None = None) -> dict:
    confirmed_by = ""
    if payload:
        confirmed_by = str(payload.get("confirmed_by", ""))
    return import_review_service.confirm_import(batch_id, confirmed_by=confirmed_by)


@app.post("/imports/batches/{batch_id}/reject")
def reject_import_batch(batch_id: str, payload: dict | None = None) -> dict:
    reason = ""
    if payload:
        reason = str(payload.get("reason", ""))
    return import_review_service.reject_batch(batch_id, reason=reason)


@app.post("/knowledge/documents")
def ingest_knowledge_document(payload: dict) -> dict:
    return knowledge_service.ingest_document(
        title=str(payload.get("title", "Untitled document")),
        content=str(payload.get("content", "")),
        source_type=str(payload.get("source_type", "note")),
        source_uri=str(payload.get("source_uri", "")),
        citation=str(payload.get("citation", "")),
        created_by=str(payload.get("created_by", "")),
    )


@app.get("/knowledge/documents")
def list_knowledge_documents(
    status: str | None = None,
    query: str = "",
    limit: int = 50,
    offset: int = 0,
) -> dict:
    return knowledge_service.list_documents(
        status=status,
        query=query,
        limit=limit,
        offset=offset,
    )


@app.get("/knowledge/documents/{document_id}/chunks")
def get_knowledge_document_chunks(
    document_id: str,
    limit: int = 100,
    offset: int = 0,
) -> dict:
    return knowledge_service.get_document_chunks(document_id, limit=limit, offset=offset)


@app.patch("/knowledge/documents/{document_id}")
def update_knowledge_document(document_id: str, payload: dict) -> dict:
    updates = payload.get("updates", payload)
    if not isinstance(updates, dict):
        return {"success": False, "error": "updates must be an object"}
    return knowledge_service.update_document(document_id, updates)


@app.post("/knowledge/documents/{document_id}/reembed")
def reembed_knowledge_document(document_id: str) -> dict:
    return knowledge_service.reembed_document(document_id)


@app.get("/knowledge/search")
def search_knowledge(query: str, limit: int = 5) -> dict:
    return knowledge_service.search(query=query, limit=limit)


@app.get("/vectors/status")
def get_vector_status() -> dict:
    return knowledge_service.vector_status()


@app.post("/vectors/rebuild")
def rebuild_vectors(payload: dict | None = None) -> dict:
    target = "knowledge"
    limit = 100
    if payload:
        target = str(payload.get("target", target))
        limit = int(payload.get("limit", limit))
    return knowledge_service.rebuild_vectors(target=target, limit=limit)


@app.post("/vectors/rebuild-jobs")
def create_vector_rebuild_job(payload: dict | None = None) -> dict:
    target = "knowledge"
    limit = 100
    created_by = ""
    if payload:
        target = str(payload.get("target", target))
        limit = int(payload.get("limit", limit))
        created_by = str(payload.get("created_by", ""))
    return knowledge_service.create_vector_rebuild_job(
        target=target,
        limit=limit,
        created_by=created_by,
    )


@app.get("/vectors/rebuild-jobs/{job_id}")
def get_vector_rebuild_job(job_id: str) -> dict:
    return knowledge_service.get_vector_rebuild_job(job_id)


@app.post("/vectors/rebuild-jobs/{job_id}/process")
def process_vector_rebuild_job(job_id: str) -> dict:
    return knowledge_service.process_vector_rebuild_job(job_id)


@app.get("/admin/overview")
def admin_overview() -> dict:
    return event_management_service.overview()


@app.get("/admin/data-quality/summary")
def admin_data_quality_summary() -> dict:
    return event_management_service.data_quality_summary()


@app.get("/admin/data-quality/issues")
def admin_list_data_quality_issues(
    issue_type: str | None = None,
    severity: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    return event_management_service.list_data_quality_issues(
        issue_type=issue_type,
        severity=severity,
        limit=limit,
        offset=offset,
    )


@app.get("/admin/dictionaries")
def admin_dictionaries() -> dict:
    return event_management_service.dictionaries()


@app.get("/admin/events")
def admin_list_events(
    query: str = "",
    start_year: int | None = None,
    end_year: int | None = None,
    regions: Annotated[list[str] | None, Query()] = None,
    statuses: Annotated[list[str] | None, Query()] = None,
    min_confidence: float | None = None,
    has_sources: bool | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    return event_management_service.list_events(
        query=query,
        start_year=start_year,
        end_year=end_year,
        regions=regions,
        statuses=statuses,
        min_confidence=min_confidence,
        has_sources=has_sources,
        limit=limit,
        offset=offset,
    )


@app.post("/admin/events")
def admin_create_event(payload: dict) -> dict:
    return event_management_service.create_event(payload)


@app.post("/admin/events/bulk-update")
def admin_bulk_update_events(payload: dict) -> dict:
    return event_management_service.bulk_update_events(payload)


@app.get("/admin/events/{event_id}/changes")
def admin_get_event_changes(
    event_id: str,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    return event_management_service.get_event_changes(event_id, limit=limit, offset=offset)


@app.get("/admin/events/{event_id}")
def admin_get_event_detail(event_id: str) -> dict:
    return event_management_service.get_admin_event_detail(event_id)


@app.patch("/admin/events/{event_id}")
def admin_update_event(event_id: str, payload: dict) -> dict:
    return event_management_service.update_event(event_id, payload)


@app.post("/admin/events/{event_id}/archive")
def admin_archive_event(event_id: str, payload: dict) -> dict:
    return event_management_service.archive_event(event_id, payload)


@app.post("/admin/events/{event_id}/dispute")
def admin_dispute_event(event_id: str, payload: dict) -> dict:
    return event_management_service.mark_event_disputed(event_id, payload)


@app.post("/admin/sources/{source_id}/verify")
def admin_verify_source(source_id: str, payload: dict) -> dict:
    return event_management_service.verify_source(source_id, payload)


@app.post("/admin/sources/bulk-verify")
def admin_bulk_verify_sources(payload: dict) -> dict:
    return event_management_service.bulk_verify_sources(payload)


@app.post("/admin/events/{event_id}/sources")
def admin_add_source(event_id: str, payload: dict) -> dict:
    return event_management_service.add_source(event_id, payload)


@app.patch("/admin/sources/{source_id}")
def admin_update_source(source_id: str, payload: dict) -> dict:
    return event_management_service.update_source(source_id, payload)


@app.delete("/admin/sources/{source_id}")
def admin_delete_source(source_id: str, payload: dict) -> dict:
    return event_management_service.delete_source(source_id, payload)


@app.get("/admin/relations")
def admin_list_relations(
    event_id: str | None = None,
    relation_types: Annotated[list[str] | None, Query()] = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    return event_management_service.list_relations(
        event_id=event_id,
        relation_types=relation_types,
        limit=limit,
        offset=offset,
    )


@app.post("/admin/relations")
def admin_create_relation(payload: dict) -> dict:
    return event_management_service.create_relation(payload)


@app.patch("/admin/relations/{relation_id}")
def admin_update_relation(relation_id: str, payload: dict) -> dict:
    return event_management_service.update_relation(relation_id, payload)


@app.delete("/admin/relations/{relation_id}")
def admin_delete_relation(relation_id: str, payload: dict) -> dict:
    return event_management_service.delete_relation(relation_id, payload)


def _sse_events(events: Iterable[dict]) -> Iterator[str]:
    for payload in events:
        event_name = str(payload.get("event", "message"))
        data = json.dumps(payload, ensure_ascii=False, default=str)
        yield f"event: {event_name}\ndata: {data}\n\n"
