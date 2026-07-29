from __future__ import annotations

from fastapi import APIRouter

from apps.api.dependencies import knowledge_service


router = APIRouter()


@router.post("/knowledge/documents")
def ingest_knowledge_document(payload: dict) -> dict:
    return knowledge_service.ingest_document(
        title=str(payload.get("title", "Untitled document")),
        content=str(payload.get("content", "")),
        source_type=str(payload.get("source_type", "note")),
        source_uri=str(payload.get("source_uri", "")),
        citation=str(payload.get("citation", "")),
        created_by=str(payload.get("created_by", "")),
    )


@router.get("/knowledge/documents")
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


@router.get("/knowledge/documents/{document_id}/chunks")
def get_knowledge_document_chunks(
    document_id: str,
    limit: int = 100,
    offset: int = 0,
) -> dict:
    return knowledge_service.get_document_chunks(document_id, limit=limit, offset=offset)


@router.patch("/knowledge/documents/{document_id}")
def update_knowledge_document(document_id: str, payload: dict) -> dict:
    updates = payload.get("updates", payload)
    if not isinstance(updates, dict):
        return {"success": False, "error": "updates must be an object"}
    return knowledge_service.update_document(document_id, updates)


@router.post("/knowledge/documents/{document_id}/reembed")
def reembed_knowledge_document(document_id: str) -> dict:
    return knowledge_service.reembed_document(document_id)


@router.get("/knowledge/search")
def search_knowledge(query: str, limit: int = 5) -> dict:
    return knowledge_service.search(query=query, limit=limit)


@router.get("/vectors/status")
def get_vector_status() -> dict:
    return knowledge_service.vector_status()


@router.post("/vectors/rebuild")
def rebuild_vectors(payload: dict | None = None) -> dict:
    target = "knowledge"
    limit = 100
    if payload:
        target = str(payload.get("target", target))
        limit = int(payload.get("limit", limit))
    return knowledge_service.rebuild_vectors(target=target, limit=limit)


@router.post("/vectors/rebuild-jobs")
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


@router.get("/vectors/rebuild-jobs/{job_id}")
def get_vector_rebuild_job(job_id: str) -> dict:
    return knowledge_service.get_vector_rebuild_job(job_id)


@router.post("/vectors/rebuild-jobs/{job_id}/process")
def process_vector_rebuild_job(job_id: str) -> dict:
    return knowledge_service.process_vector_rebuild_job(job_id)
