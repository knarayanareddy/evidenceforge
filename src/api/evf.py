"""API routes for EvidenceForge (EVF) - Fail-Closed Baseline."""
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, status, Path as PathParam, HTTPException
from pydantic import BaseModel
from src.api.deps import require_project_role, verify_idempotency_key
from src.core.security import UserContext

router = APIRouter()

class DocumentCreate(BaseModel):
    artifact_id: str
    title: str

class Document(BaseModel):
    id: str
    project_id: str
    version: int = 1
    source_sha256: str
    source_artifact_id: str
    title: str
    state: str
    page_count: Optional[int] = None
    created_at: str

class ParseCreate(BaseModel):
    profile: str = "fixture/1"
    source_sha256: str

class ExtractionCreate(BaseModel):
    schema_version: str = "annual-report-8/1"
    method: str = "fixture"
    parse_id: str

class ReviewCreate(BaseModel):
    base_revision: int
    patches: List[Dict[str, Any]]

class ExportCreate(BaseModel):
    review_revision: int
    format: str = "json"
    allow_incomplete: bool = True

@router.post("/projects/{project_id}/evf/documents", response_model=Document, status_code=status.HTTP_201_CREATED)
async def evf_create_document(
    project_id: str = PathParam(...),
    body: DocumentCreate = ...,
    user: UserContext = Depends(require_project_role("analyst")),
    idemp: str = Depends(verify_idempotency_key)
):
    raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="Document storage unconfigured in B00 baseline.")

@router.get("/projects/{project_id}/evf/documents", response_model=List[Document], status_code=status.HTTP_200_OK)
async def evf_list_documents(
    project_id: str = PathParam(...),
    user: UserContext = Depends(require_project_role("viewer"))
):
    return []

@router.get("/evf/documents/{document_id}", response_model=Document, status_code=status.HTTP_200_OK)
async def evf_get_document(
    document_id: str = PathParam(...),
    user: UserContext = Depends(require_project_role("analyst"))
):
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

@router.delete("/evf/documents/{document_id}", status_code=status.HTTP_202_ACCEPTED)
async def evf_delete_document(
    document_id: str = PathParam(...),
    user: UserContext = Depends(require_project_role("maintainer")),
    idemp: str = Depends(verify_idempotency_key)
):
    raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="Deletion lifecycle unconfigured in B00 baseline.")

@router.post("/evf/documents/{document_id}/parses", status_code=status.HTTP_202_ACCEPTED)
async def evf_create_parse(
    document_id: str = PathParam(...),
    body: ParseCreate = ...,
    user: UserContext = Depends(require_project_role("operator")),
    idemp: str = Depends(verify_idempotency_key)
):
    raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="Parser engine unconfigured in B00 baseline.")

@router.get("/evf/parses/{parse_id}", status_code=status.HTTP_200_OK)
async def evf_get_parse(
    parse_id: str = PathParam(...),
    user: UserContext = Depends(require_project_role("analyst"))
):
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Parse not found")

@router.post("/projects/{project_id}/evf/extractions", status_code=status.HTTP_201_CREATED)
async def evf_create_extraction(
    project_id: str = PathParam(...),
    body: ExtractionCreate = ...,
    user: UserContext = Depends(require_project_role("analyst")),
    idemp: str = Depends(verify_idempotency_key)
):
    raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="Extraction engine unconfigured in B00 baseline.")

@router.get("/evf/extractions/{extraction_id}", status_code=status.HTTP_200_OK)
async def evf_get_extraction(
    extraction_id: str = PathParam(...),
    user: UserContext = Depends(require_project_role("analyst"))
):
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Extraction not found")

@router.post("/evf/extractions/{extraction_id}/reviews", status_code=status.HTTP_201_CREATED)
async def evf_create_review(
    extraction_id: str = PathParam(...),
    body: ReviewCreate = ...,
    user: UserContext = Depends(require_project_role("analyst")),
    idemp: str = Depends(verify_idempotency_key)
):
    raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="Review store unconfigured in B00 baseline.")

@router.get("/evf/extractions/{extraction_id}/reviews", status_code=status.HTTP_200_OK)
async def evf_list_reviews(
    extraction_id: str = PathParam(...),
    user: UserContext = Depends(require_project_role("analyst"))
):
    return []

@router.post("/evf/extractions/{extraction_id}/exports", status_code=status.HTTP_201_CREATED)
async def evf_create_export(
    extraction_id: str = PathParam(...),
    body: ExportCreate = ...,
    user: UserContext = Depends(require_project_role("analyst")),
    idemp: str = Depends(verify_idempotency_key)
):
    raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="Export generator unconfigured in B00 baseline.")

@router.get("/evf/exports/{export_id}", status_code=status.HTTP_200_OK)
async def evf_get_export(
    export_id: str = PathParam(...),
    user: UserContext = Depends(require_project_role("analyst"))
):
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Export not found")
