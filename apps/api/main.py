from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from tools.historical.repository import HistoricalEventRepository
from apps.api.dependencies import (
    data_source,
    postgres_client,
    repository,
)
from apps.api.routes.agent import (
    _sse_events,
    agent_queue_health,
    cancel_agent_run,
    confirm_agent_run,
    enqueue_agent_query,
    get_agent_run,
    process_one_queued_agent_run,
    query_agent,
    query_agent_stream,
    recover_stale_agent_runs,
    router as agent_router,
)
from apps.api.routes.auth import (
    login,
    logout,
    me,
    register,
    router as auth_router,
)
from apps.api.routes.chat import (
    archive_chat_conversation,
    archive_chat_group,
    create_chat_conversation,
    create_chat_group,
    create_chat_message,
    get_chat_conversation,
    list_chat_conversations,
    list_chat_groups,
    list_chat_messages,
    router as chat_router,
    update_chat_conversation,
    update_chat_group,
)
from apps.api.routes.knowledge import (
    create_vector_rebuild_job,
    get_knowledge_document_chunks,
    list_knowledge_document_versions,
    get_vector_rebuild_job,
    get_vector_status,
    ingest_knowledge_document,
    list_knowledge_documents,
    process_vector_rebuild_job,
    process_pending_vector_rebuild_jobs,
    rechunk_knowledge_document,
    reembed_knowledge_document,
    rebuild_vectors,
    router as knowledge_router,
    search_knowledge,
    update_knowledge_document,
)
from apps.api.routes.imports import (
    bulk_revalidate_import_staging,
    confirm_import_batch,
    create_import_batch,
    get_import_batch,
    get_import_staging_rows,
    list_import_batches,
    merge_import_staging_row,
    parse_import_events,
    preview_import_batch,
    reject_import_batch,
    revalidate_import_batch,
    router as imports_router,
    update_import_staging_row,
)
from apps.api.routes.admin import (
    admin_add_source,
    admin_archive_event,
    admin_bulk_update_events,
    admin_bulk_verify_sources,
    admin_create_event,
    admin_create_relation,
    admin_data_quality_summary,
    admin_delete_relation,
    admin_delete_source,
    admin_dictionaries,
    admin_dispute_event,
    admin_get_event_changes,
    admin_get_event_detail,
    admin_import_batch_review,
    admin_import_batch_report,
    admin_list_data_quality_issues,
    admin_list_events,
    admin_list_relations,
    admin_overview,
    admin_set_data_quality_issue_action,
    admin_update_event,
    admin_update_relation,
    admin_update_source,
    admin_verify_source,
    router as admin_router,
)
from apps.api.routes.events import (
    compare_regions,
    find_contemporary_events,
    find_related_events,
    get_event_detail,
    router as events_router,
    search_events_by_range,
    search_events_by_year,
)

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

app.include_router(knowledge_router)
app.include_router(imports_router)
app.include_router(admin_router)
app.include_router(events_router)
app.include_router(agent_router)
app.include_router(auth_router)
app.include_router(chat_router)


@app.get("/health")
def health() -> dict[str, str | int]:
    payload: dict[str, str | int] = {"status": "ok", "data_source": data_source}
    if isinstance(repository, HistoricalEventRepository):
        payload["events"] = len(repository.events)
    return payload


@app.get("/health/db")
def database_health() -> dict:
    return postgres_client.health_check().to_dict()
