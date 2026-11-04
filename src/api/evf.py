"""API routes for EvidenceForge (EVF)."""
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, status, Path as PathParam
from pydantic import BaseModel
from src.api.deps import require_role, verify_idempotency_key

router = APIRouter()

class DocumentCreate(BaseModel):
    source_artifact_id: str
    title: str

class Document(BaseModel):
    id: str
    project_id: str
    version: int
    source_sha256: str
    source_artifact_id: str
    title: str
    state: str
    page_count: Optional[int] = None
    created_at: str

class ParseCreate(BaseModel):
    profile: str = "docling_local/1"

class ExtractionCreate(BaseModel):
    parse_id: str
    schema_version: str = "annual-report-8/1"

class ReviewCreate(BaseModel):
    base_revision: int
    patches: List[Dict[str, Any]]

class ExportCreate(BaseModel):
    review_revision: int

@router.post("/projects/{project_id}/evf/documents", response_model=Document, status_code=status.HTTP_201_CREATED)
async def evf_create_document(
    project_id: str = PathParam(...),
    body: DocumentCreate = ...,
    role: str = Depends(require_role("analyst")),
    idemp: str = Depends(verify_idempotency_key)
):
    """Register a new document from an uploaded artifact."""
    import uuid, datetime
    return Document(
        id=str(uuid.uuid4()),
        project_id=project_id,
        version=1,
        source_sha256="0"*64,
        source_artifact_id=body.source_artifact_id,
        title=body.title,
        state="accepted",
        page_count=10,
        created_at=datetime.datetime.utcnow().isoformat() + "Z"
    )

@router.get("/projects/{project_id}/evf/documents", response_model=List[Document], status_code=status.HTTP_200_OK)
async def evf_list_documents(project_id: str = PathParam(...), role: str = Depends(require_role("viewer"))):
    return []

@router.get("/evf/documents/{document_id}", response_model=Document, status_code=status.HTTP_200_OK)
async def evf_get_document(document_id: str = PathParam(...), role: str = Depends(require_role("analyst"))):
    import datetime
    return Document(
        id=document_id,
        project_id="00000000-0000-4000-8000-000000000001",
        version=1,
        source_sha256="0"*64,
        source_artifact_id="00000000-0000-4000-8000-000000000002",
        title="Sample Report",
        state="parsed",
        page_count=10,
        created_at=datetime.datetime.utcnow().isoformat() + "Z"
    )

@router.delete("/evf/documents/{document_id}", status_code=status.HTTP_200_OK)
async def evf_delete_document(
    document_id: str = PathParam(...),
    role: str = Depends(require_role("maintainer")),
    idemp: str = Depends(verify_idempotency_key)
):
    return {"document_id": document_id, "state": "deleting"}

@router.post("/evf/documents/{document_id}/parses", status_code=status.HTTP_201_CREATED)
async def evf_create_parse(
    document_id: str = PathParam(...),
    body: ParseCreate = ...,
    role: str = Depends(require_role("operator")),
    idemp: str = Depends(verify_idempotency_key)
):
    import uuid
    return {"parse_id": str(uuid.uuid4()), "document_id": document_id, "state": "queued"}

@router.get("/evf/parses/{parse_id}", status_code=status.HTTP_200_OK)
async def evf_get_parse(parse_id: str = PathParam(...), role: str = Depends(require_role("analyst"))):
    return {"parse_id": parse_id, "state": "parsed"}

@router.post("/projects/{project_id}/evf/extractions", status_code=status.HTTP_201_CREATED)
async def evf_create_extraction(
    project_id: str = PathParam(...),
    body: ExtractionCreate = ...,
    role: str = Depends(require_role("analyst")),
    idemp: str = Depends(verify_idempotency_key)
):
    import uuid
    return {"extraction_id": str(uuid.uuid4()), "schema_version": body.schema_version, "revision": 1}

@router.get("/evf/extractions/{extraction_id}", status_code=status.HTTP_200_OK)
async def evf_get_extraction(extraction_id: str = PathParam(...), role: str = Depends(require_role("analyst"))):
    return {"extraction_id": extraction_id, "revision": 1}

@router.post("/evf/extractions/{extraction_id}/reviews", status_code=status.HTTP_201_CREATED)
async def evf_create_review(
    extraction_id: str = PathParam(...),
    body: ReviewCreate = ...,
    role: str = Depends(require_role("analyst")),
    idemp: str = Depends(verify_idempotency_key)
):
    import uuid
    return {"review_id": str(uuid.uuid4()), "revision": body.base_revision + 1}

@router.get("/evf/extractions/{extraction_id}/reviews", status_code=status.HTTP_200_OK)
async def evf_list_reviews(extraction_id: str = PathParam(...), role: str = Depends(require_role("analyst"))):
    return []

@router.post("/evf/extractions/{extraction_id}/exports", status_code=status.HTTP_201_CREATED)
async def evf_create_export(
    extraction_id: str = PathParam(...),
    body: ExportCreate = ...,
    role: str = Depends(require_role("analyst")),
    idemp: str = Depends(verify_idempotency_key)
):
    import uuid
    return {"export_id": str(uuid.uuid4()), "status": "completed"}

@router.get("/evf/exports/{export_id}", status_code=status.HTTP_200_OK)
async def evf_get_export(export_id: str = PathParam(...), role: str = Depends(require_role("analyst"))):
    return {"export_id": export_id, "artifact_id": "00000000-0000-4000-8000-000000000001"}
