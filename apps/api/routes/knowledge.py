from __future__ import annotations

from fastapi import APIRouter, Depends

from apps.api.dependencies import knowledge_service
from apps.api.payloads import payload_to_dict
from apps.api.routes.auth import require_admin_user
from apps.api.schemas.knowledge import (
    KnowledgeDocumentIngestRequest,
    KnowledgeDocumentRechunkRequest,
    KnowledgeDocumentUpdateRequest,
    KnowledgeMutationResponse,
    VectorProcessPendingRequest,
    VectorRebuildRequest,
)


router = APIRouter()


@router.post("/knowledge/documents", response_model=KnowledgeMutationResponse)
def ingest_knowledge_document(
    payload: KnowledgeDocumentIngestRequest,
    user: dict = Depends(require_admin_user),
) -> dict:
    payload = payload_to_dict(payload)
    operator = _operator_name(user)
    return knowledge_service.ingest_document(
        title=str(payload.get("title", "Untitled document")),
        content=str(payload.get("content", "")),
        source_type=str(payload.get("source_type", "note")),
        source_uri=str(payload.get("source_uri", "")),
        citation=str(payload.get("citation", "")),
        created_by=str(payload.get("created_by") or operator),
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


@router.get("/knowledge/documents/{document_id}/versions")
def list_knowledge_document_versions(document_id: str) -> dict:
    return knowledge_service.list_document_versions(document_id)


@router.patch("/knowledge/documents/{document_id}", response_model=KnowledgeMutationResponse)
def update_knowledge_document(
    document_id: str,
    payload: KnowledgeDocumentUpdateRequest,
    user: dict = Depends(require_admin_user),
) -> dict:
    payload = payload_to_dict(payload)
    updates = payload.get("updates", payload)
    if not isinstance(updates, dict):
        return {"success": False, "error": "updates must be an object"}
    return knowledge_service.update_document(document_id, updates)


@router.post("/knowledge/documents/{document_id}/rechunk", response_model=KnowledgeMutationResponse)
def rechunk_knowledge_document(
    document_id: str,
    payload: KnowledgeDocumentRechunkRequest,
    user: dict = Depends(require_admin_user),
) -> dict:
    payload = payload_to_dict(payload)
    operator = _operator_name(user)
    return knowledge_service.rechunk_document(
        document_id=document_id,
        content=payload.get("content"),
        max_chars=payload.get("max_chars"),
        overlap_chars=payload.get("overlap_chars"),
        changed_by=str(payload.get("changed_by") or operator),
        reason=str(payload.get("reason", "")),
    )


@router.post("/knowledge/documents/{document_id}/reembed", response_model=KnowledgeMutationResponse)
def reembed_knowledge_document(
    document_id: str,
    user: dict = Depends(require_admin_user),
) -> dict:
    return knowledge_service.reembed_document(document_id)


@router.get("/knowledge/search")
def search_knowledge(query: str, limit: int = 5) -> dict:
    return knowledge_service.search(query=query, limit=limit)


@router.get("/vectors/status")
def get_vector_status() -> dict:
    return knowledge_service.vector_status()


@router.post("/vectors/rebuild", response_model=KnowledgeMutationResponse)
def rebuild_vectors(
    payload: VectorRebuildRequest | None = None,
    user: dict = Depends(require_admin_user),
) -> dict:
    payload = payload_to_dict(payload)
    target = "knowledge"
    limit = 100
    if payload:
        target = str(payload.get("target", target))
        limit = int(payload.get("limit", limit))
    return knowledge_service.rebuild_vectors(target=target, limit=limit)


@router.post("/vectors/rebuild-jobs", response_model=KnowledgeMutationResponse)
def create_vector_rebuild_job(
    payload: VectorRebuildRequest | None = None,
    user: dict = Depends(require_admin_user),
) -> dict:
    payload = payload_to_dict(payload)
    target = "knowledge"
    limit = 100
    created_by = _operator_name(user)
    if payload:
        target = str(payload.get("target", target))
        limit = int(payload.get("limit", limit))
        created_by = str(payload.get("created_by") or created_by)
    created = knowledge_service.create_vector_rebuild_job(
        target=target,
        limit=limit,
        created_by=created_by,
    )
    if payload.get("auto_process") is True and created.get("created") and created.get("job"):
        processed = knowledge_service.process_vector_rebuild_job(str(created["job"]["id"]))
        created["processed"] = processed
    return created


@router.get("/vectors/rebuild-jobs/{job_id}")
def get_vector_rebuild_job(job_id: str) -> dict:
    return knowledge_service.get_vector_rebuild_job(job_id)


@router.post("/vectors/rebuild-jobs/{job_id}/process", response_model=KnowledgeMutationResponse)
def process_vector_rebuild_job(
    job_id: str,
    user: dict = Depends(require_admin_user),
) -> dict:
    return knowledge_service.process_vector_rebuild_job(job_id)


@router.post("/vectors/rebuild-jobs/process-pending", response_model=KnowledgeMutationResponse)
def process_pending_vector_rebuild_jobs(
    payload: VectorProcessPendingRequest,
    user: dict = Depends(require_admin_user),
) -> dict:
    payload = payload_to_dict(payload)
    limit = int(payload.get("limit", 1))
    return knowledge_service.process_pending_vector_rebuild_jobs(limit=limit)


def _operator_name(user: dict | object | None) -> str:
    if not isinstance(user, dict):
        return ""
    return str(user.get("username") or user.get("id") or "")
