"""Foundation routes: projects, uploads/artifacts, jobs (scoped idempotency)."""
import hashlib
from typing import List, Optional
from fastapi import APIRouter, Depends, status, Path as PathParam, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel
from src.api.deps import (get_current_user, require_org_admin, require_project_capability,
                          require_object_capability, verify_idempotency_key, user_has_capability)
from src.core.security import UserContext
from src.services.store import store, new_id, now_iso, request_hash

router = APIRouter()

class ProjectCreate(BaseModel):
    name: str
    content_capture: str = "metadata_only"
    external_transfer: bool = False

class Project(BaseModel):
    id: str; name: str; content_capture: str; external_transfer: bool
    revision: int; created_at: str

class UploadCreate(BaseModel):
    filename: str; media_type: str; byte_size: int; sha256: str; classification: str = "synthetic"

class Upload(BaseModel):
    id: str; artifact_id: str; put_path: str; expires_at: str; maximum_bytes: int

class UploadFinalize(BaseModel):
    sha256: str; byte_size: int

class Artifact(BaseModel):
    id: str; project_id: str; sha256: str; byte_size: int; media_type: str
    status: str; classification: str; created_at: str

class Job(BaseModel):
    id: str; project_id: str; kind: str; state: str; attempt: int = 0
    revision: int = 1; created_at: str; result_id: Optional[str] = None; error_code: Optional[str] = None

def _idem_replay(scope_kind, scope_id, user, op, key, body):
    rec = store.idem_lookup(scope_kind, scope_id, user.user_id, op, key)
    if rec:
        if rec["request_sha256"] != request_hash(body):
            raise HTTPException(409, "Idempotency-Key reused with a different request")
        return rec
    return None

@router.post("/projects", response_model=Project, status_code=201)
async def foundation_create_project(body: ProjectCreate, user: UserContext = Depends(require_org_admin),
                                    idemp: str = Depends(verify_idempotency_key)):
    # Auth (+org-admin authorization) happens in dependencies BEFORE replay lookup.
    with store.lock:
        rec = _idem_replay("org", user.organization_id, user, "foundation_create_project", idemp, body.model_dump())
        if rec: return rec["body"]
        proj = {"id": new_id(), "name": body.name, "content_capture": body.content_capture,
                "external_transfer": body.external_transfer, "revision": 1, "created_at": now_iso(),
                "organization_id": user.organization_id}
        store.projects[proj["id"]] = proj
        store.grant(user.user_id, proj["id"], "maintainer")
        out = {k: proj[k] for k in Project.model_fields}
        store.idem_save("org", user.organization_id, user.user_id, "foundation_create_project", idemp,
                        request_hash(body.model_dump()), 201, out)
        return out

@router.get("/projects", response_model=List[Project])
async def foundation_list_projects(user: UserContext = Depends(get_current_user)):
    ids = set(user.project_roles) | {pid for (uid, pid) in store.grants if uid == user.user_id}
    return [{k: p[k] for k in Project.model_fields} for p in store.projects.values() if p["id"] in ids]

@router.post("/projects/{project_id}/uploads", response_model=Upload, status_code=201)
async def foundation_create_upload(project_id: str = PathParam(...), body: UploadCreate = ...,
                                   user: UserContext = Depends(require_project_capability("analyst")),
                                   idemp: str = Depends(verify_idempotency_key)):
    if body.media_type != "application/pdf":
        raise HTTPException(422, "EvidenceForge accepts application/pdf uploads only")
    if not (1 <= body.byte_size <= 104857600):
        raise HTTPException(422, "byte_size out of bounds")
    with store.lock:
        rec = _idem_replay("project", project_id, user, "foundation_create_upload", idemp, body.model_dump())
        if rec: return rec["body"]
        up = {"id": new_id(), "artifact_id": new_id(), "project_id": project_id,
              "put_path": "", "expires_at": now_iso(), "maximum_bytes": body.byte_size,
              "expected_sha256": body.sha256, "expected_size": body.byte_size,
              "media_type": body.media_type, "classification": body.classification, "received": None}
        up["put_path"] = f"/api/v1/uploads/{up['id']}/bytes"
        store.uploads[up["id"]] = up
        out = {k: up[k] for k in Upload.model_fields}
        store.idem_save("project", project_id, user.user_id, "foundation_create_upload", idemp,
                        request_hash(body.model_dump()), 201, out)
        return out

@router.put("/uploads/{upload_id}/bytes")
async def foundation_put_upload(request: Request, upload_id: str = PathParam(...),
                                user: UserContext = Depends(require_object_capability("analyst"))):
    up = store.uploads.get(upload_id)
    if not up: raise HTTPException(404, "Upload not found")
    data = await request.body()
    if len(data) > up["maximum_bytes"]: raise HTTPException(413, "Upload exceeds declared maximum_bytes")
    up["received"] = data
    return {}

@router.post("/uploads/{upload_id}:finalize", response_model=Artifact)
async def foundation_finalize_upload(body: UploadFinalize, upload_id: str = PathParam(...),
                                     user: UserContext = Depends(require_object_capability("analyst")),
                                     idemp: str = Depends(verify_idempotency_key)):
    up = store.uploads.get(upload_id)
    if not up: raise HTTPException(404, "Upload not found")
    data = up.get("received")
    if data is None: raise HTTPException(409, "No bytes received for upload")
    digest = hashlib.sha256(data).hexdigest()
    if digest != body.sha256 or digest != up["expected_sha256"] or len(data) != body.byte_size:
        raise HTTPException(422, "SHA-256/size verification failed; artifact quarantined")
    with store.lock:
        art = {"id": up["artifact_id"], "project_id": up["project_id"], "sha256": digest,
               "byte_size": len(data), "media_type": up["media_type"], "status": "ready",
               "classification": up["classification"], "created_at": now_iso()}
        store.artifacts[art["id"]] = art; store.artifact_bytes[art["id"]] = data
        return art

def _artifact_or_404(artifact_id, user, request):
    art = store.artifacts.get(artifact_id)
    if not art: raise HTTPException(404, "Artifact not found")
    hint = request.headers.get("X-Project-Id")
    if hint and hint != art["project_id"]: raise HTTPException(404, "Artifact not found")
    if not user_has_capability(user, art["project_id"], "analyst"):
        raise HTTPException(403, "Insufficient project privileges")
    if art["status"] in ("deleting", "deleted"): raise HTTPException(404, "Artifact not found")
    return art

@router.get("/artifacts/{artifact_id}", response_model=Artifact)
async def foundation_get_artifact(request: Request, artifact_id: str = PathParam(...),
                                  user: UserContext = Depends(require_object_capability("analyst"))):
    return _artifact_or_404(artifact_id, user, request)

@router.get("/artifacts/{artifact_id}/bytes")
async def foundation_download_artifact(request: Request, artifact_id: str = PathParam(...),
                                       user: UserContext = Depends(require_object_capability("analyst"))):
    art = _artifact_or_404(artifact_id, user, request)
    return Response(content=store.artifact_bytes.get(art["id"], b""), media_type=art["media_type"],
                    headers={"Content-Disposition": "attachment"})

def job_out(j): return {k: j.get(k) for k in Job.model_fields}

@router.get("/jobs/{job_id}", response_model=Job)
async def foundation_get_job(job_id: str = PathParam(...),
                             user: UserContext = Depends(require_object_capability("viewer"))):
    job = store.jobs.get(job_id)
    if not job: raise HTTPException(404, "Job not found")
    return job_out(job)

@router.post("/jobs/{job_id}:cancel", response_model=Job, status_code=202)
async def foundation_cancel_job(job_id: str = PathParam(...),
                                user: UserContext = Depends(require_object_capability("operator")),
                                idemp: str = Depends(verify_idempotency_key)):
    job = store.jobs.get(job_id)
    if not job: raise HTTPException(404, "Job not found")
    if job["state"] in ("queued", "running", "leased"):
        job["state"] = "cancel_requested"  # never rewritten as if it never happened
    return job_out(job)
