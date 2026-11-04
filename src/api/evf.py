"""EVF routes: documents, parses, extractions, reviews, exports, deletion."""
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, status, Path as PathParam, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel
from src.api.deps import require_project_capability, require_object_capability, verify_idempotency_key, user_has_capability
from src.core.security import UserContext
from src.services.store import store, new_id, now_iso, request_hash
from src.services import evf as svc

router = APIRouter()

class DocumentCreate(BaseModel):
    artifact_id: str; title: str
class Document(BaseModel):
    id: str; project_id: str; version: int = 1; source_sha256: str
    source_artifact_id: str; title: str; state: str
    page_count: Optional[int] = None; created_at: str
class ParseCreate(BaseModel):
    profile: str = "fixture/1"; source_sha256: str
class ParseOut(BaseModel):
    id: str; document_id: str; source_sha256: str; profile: str; profile_sha256: str
    state: str; job_id: str; page_count: int; created_at: str
    elements: Dict[str, Any] = {}
    synthetic_fixture: bool = True
class ExtractionCreate(BaseModel):
    schema_version: str = "annual-report-8/1"; method: str = "fixture"; parse_id: str
class ReviewCreate(BaseModel):
    base_revision: int; patches: List[Dict[str, Any]]
class ExportCreate(BaseModel):
    review_revision: int; format: str = "json"; allow_incomplete: bool = True

def _check_actual(user, obj_project, hint):
    if hint and hint != obj_project: raise HTTPException(404, "Not found")
    return obj_project

def _doc(document_id, user, request, capability="analyst"):
    doc = store.documents.get(document_id)
    hint = request.headers.get("X-Project-Id")
    if not doc or doc["state"] == "deleting":
        raise HTTPException(404, "Document not found")
    _check_actual(user, doc["project_id"], hint)
    if not user_has_capability(user, doc["project_id"], capability):
        raise HTTPException(403, "Insufficient project privileges")
    return doc

def _doc_out(d): return {k: d[k] for k in Document.model_fields}
def _parse_out(p):
    out = {k: p[k] for k in ("id", "document_id", "source_sha256", "profile", "profile_sha256", "state", "job_id", "page_count", "created_at")}
    out["elements"] = p.get("elements", {}); out["synthetic_fixture"] = p["profile"] == "fixture/1"
    return out

@router.post("/projects/{project_id}/evf/documents", response_model=Document, status_code=201)
async def evf_create_document(project_id: str = PathParam(...), body: DocumentCreate = ...,
                              user: UserContext = Depends(require_project_capability("analyst")),
                              idemp: str = Depends(verify_idempotency_key)):
    art = store.artifacts.get(body.artifact_id)
    if not art or art["project_id"] != project_id or art["status"] != "ready":
        raise HTTPException(404, "Artifact not found in this project")
    with store.lock:
        rec = store.idem_lookup("project", project_id, user.user_id, "evf_create_document", idemp)
        if rec:
            if rec["request_sha256"] != request_hash(body.model_dump()): raise HTTPException(409, "Idempotency-Key reused with different request")
            return rec["body"]
        doc = {"id": new_id(), "project_id": project_id, "version": 1, "source_sha256": art["sha256"],
               "source_artifact_id": art["id"], "title": body.title, "state": "accepted",
               "page_count": None, "created_at": now_iso()}
        store.documents[doc["id"]] = doc
        store.idem_save("project", project_id, user.user_id, "evf_create_document", idemp,
                        request_hash(body.model_dump()), 201, _doc_out(doc))
        return _doc_out(doc)

@router.get("/projects/{project_id}/evf/documents", response_model=List[Document])
async def evf_list_documents(project_id: str = PathParam(...),
                             user: UserContext = Depends(require_project_capability("viewer"))):
    return [_doc_out(d) for d in store.documents.values()
            if d["project_id"] == project_id and d["state"] != "deleting"]

@router.get("/evf/documents/{document_id}", response_model=Document)
async def evf_get_document(request: Request, document_id: str = PathParam(...),
                           user: UserContext = Depends(require_object_capability("analyst"))):
    return _doc_out(_doc(document_id, user, request))

@router.delete("/evf/documents/{document_id}", status_code=202)
async def evf_delete_document(request: Request, document_id: str = PathParam(...),
                              user: UserContext = Depends(require_object_capability("maintainer")),
                              idemp: str = Depends(verify_idempotency_key)):
    doc = _doc(document_id, user, request, "maintainer")
    with store.lock:
        doc["state"] = "deleting"  # immediate read revocation; purge via lifecycle job
        affected = 0
        art = store.artifacts.get(doc["source_artifact_id"])
        if art: art["status"] = "deleting"; affected = 1
        deletion = {"id": new_id(), "state": "revoked", "revoked_at": now_iso(),
                    "purge_deadline": now_iso(), "affected_artifacts": affected,
                    "project_id": doc["project_id"], "target_id": doc["id"]}
        store.deletions.append(deletion)
        job = {"id": new_id(), "project_id": doc["project_id"], "kind": "purge_document",
               "state": "queued", "payload": {"document_id": doc["id"]}, "attempt": 0,
               "revision": 1, "created_at": now_iso(), "result_id": None, "error_code": None}
        store.jobs[job["id"]] = job
        return {"id": deletion["id"], "state": deletion["state"], "revoked_at": deletion["revoked_at"],
                "purge_deadline": deletion["purge_deadline"], "affected_artifacts": affected}

@router.post("/evf/documents/{document_id}/parses", status_code=202)
async def evf_create_parse(request: Request, document_id: str = PathParam(...), body: ParseCreate = ...,
                           user: UserContext = Depends(require_object_capability("operator")),
                           idemp: str = Depends(verify_idempotency_key)):
    doc = _doc(document_id, user, request, "operator")
    if body.profile == "docling_local/1":
        try:
            import docling_parse  # noqa: F401
        except ImportError:
            raise HTTPException(501, "docling_local/1 disabled: docling-parse not installed/verified")
    if body.source_sha256 != doc["source_sha256"]:
        raise HTTPException(422, "source_sha256 does not match document source")
    with store.lock:
        parse = {"id": new_id(), "document_id": doc["id"], "source_sha256": doc["source_sha256"],
                 "profile": body.profile, "profile_sha256": svc.hashlib.sha256(body.profile.encode()).hexdigest(),
                 "state": "queued", "job_id": "", "page_count": 0, "created_at": now_iso(),
                 "project_id": doc["project_id"], "elements": {}}
        job = {"id": new_id(), "project_id": doc["project_id"], "kind": "evf_parse",
               "state": "queued", "payload": {"parse_id": parse["id"]}, "attempt": 0,
               "revision": 1, "created_at": now_iso(), "result_id": parse["id"], "error_code": None}
        parse["job_id"] = job["id"]; doc["state"] = "parsing"
        store.parses[parse["id"]] = parse; store.jobs[job["id"]] = job
        return _parse_out(parse)

@router.get("/evf/parses/{parse_id}")
async def evf_get_parse(request: Request, parse_id: str = PathParam(...),
                        user: UserContext = Depends(require_object_capability("analyst"))):
    parse = store.parses.get(parse_id)
    if not parse: raise HTTPException(404, "Parse not found")
    _doc(parse["document_id"], user, request)
    return _parse_out(parse)

@router.post("/projects/{project_id}/evf/extractions", status_code=201)
async def evf_create_extraction(project_id: str = PathParam(...), body: ExtractionCreate = ...,
                                user: UserContext = Depends(require_project_capability("analyst")),
                                idemp: str = Depends(verify_idempotency_key)):
    parse = store.parses.get(body.parse_id)
    if not parse: raise HTTPException(404, "Parse not found")
    doc = store.documents.get(parse["document_id"])
    if not doc or doc["project_id"] != project_id or doc["state"] == "deleting":
        raise HTTPException(404, "Parse not found in this project")
    if parse["state"] != "parsed": raise HTTPException(409, "Parse is not complete")
    with store.lock:
        ext = {"id": new_id(), "project_id": project_id, "parse_id": parse["id"],
               "schema_version": "annual-report-8/1", "revision": 1,
               "fields": svc.build_fields(doc, parse), "created_at": now_iso()}
        store.extractions[ext["id"]] = ext
        return ext

def _ext(extraction_id, user, request):
    ext = store.extractions.get(extraction_id)
    if not ext: raise HTTPException(404, "Extraction not found")
    hint = request.headers.get("X-Project-Id")
    _check_actual(user, ext["project_id"], hint)
    doc_parse = store.parses.get(ext["parse_id"])
    if doc_parse and store.documents.get(doc_parse["document_id"], {}).get("state") == "deleting":
        raise HTTPException(404, "Extraction not found")
    if not user_has_capability(user, ext["project_id"], "analyst"):
        raise HTTPException(403, "Insufficient project privileges")
    return ext

@router.get("/evf/extractions/{extraction_id}")
async def evf_get_extraction(request: Request, extraction_id: str = PathParam(...),
                             user: UserContext = Depends(require_object_capability("analyst"))):
    ext = _ext(extraction_id, user, request)
    out = dict(ext); out["fields"] = svc.effective_fields(ext); return out

@router.post("/evf/extractions/{extraction_id}/reviews", status_code=201)
async def evf_create_review(request: Request, extraction_id: str = PathParam(...), body: ReviewCreate = ...,
                            user: UserContext = Depends(require_object_capability("analyst")),
                            idemp: str = Depends(verify_idempotency_key)):
    ext = _ext(extraction_id, user, request)
    if_match = request.headers.get("If-Match")
    if if_match is None: raise HTTPException(428, "If-Match header required")
    try: expected = int(if_match.strip('"'))
    except ValueError: raise HTTPException(400, "If-Match must be a quoted integer revision")
    if body.base_revision != expected: raise HTTPException(409, "Body base_revision must equal If-Match")
    if expected != ext["revision"]: raise HTTPException(412, "Stale revision; fetch current extraction")
    parse = store.parses[ext["parse_id"]]; doc = store.documents[parse["document_id"]]
    for p in body.patches:
        if p.get("key") not in svc.FIELD_KEYS: raise HTTPException(422, f"Unknown field key: {p.get('key')}")
        if p.get("action") not in ("accept", "correct", "reject"): raise HTTPException(422, "Invalid review action")
        if not p.get("reason") or len(p["reason"]) < 5: raise HTTPException(422, "Patch reason (min 5 chars) required")
        for ev in p.get("evidence", []) or []:
            if ev.get("parse_id") != parse["id"] or ev.get("document_id") != doc["id"] \
               or ev.get("source_sha256") != doc["source_sha256"] \
               or svc.verify_quote(doc, parse, ev.get("element_id", ""), ev.get("quote", "")) != "supported_exact":
                raise HTTPException(422, "Evidence failed verification (hash/parse/element/quote)")
    with store.lock:
        if expected != ext["revision"]: raise HTTPException(412, "Stale revision")
        rev = {"id": new_id(), "extraction_id": ext["id"], "revision": ext["revision"] + 1,
               "base_revision": body.base_revision, "actor_id": user.user_id,
               "created_at": now_iso(), "patches": body.patches}
        store.reviews[rev["id"]] = rev; ext["revision"] += 1
        return rev

@router.get("/evf/extractions/{extraction_id}/reviews")
async def evf_list_reviews(request: Request, extraction_id: str = PathParam(...),
                           user: UserContext = Depends(require_object_capability("analyst"))):
    ext = _ext(extraction_id, user, request)
    return sorted((r for r in store.reviews.values() if r["extraction_id"] == ext["id"]),
                  key=lambda r: r["revision"])

@router.post("/evf/extractions/{extraction_id}/exports", status_code=201)
async def evf_create_export(request: Request, extraction_id: str = PathParam(...), body: ExportCreate = ...,
                            user: UserContext = Depends(require_object_capability("analyst")),
                            idemp: str = Depends(verify_idempotency_key)):
    ext = _ext(extraction_id, user, request)
    if body.format not in ("json", "csv"): raise HTTPException(422, "format must be json or csv")
    if body.review_revision > ext["revision"]: raise HTTPException(422, "Unknown review_revision")
    fields = svc.effective_fields(ext)
    payload, incomplete, warnings, digest = svc.render_export(fields, body.format)
    if incomplete and not body.allow_incomplete:
        raise HTTPException(422, "Extraction incomplete and allow_incomplete=false")
    with store.lock:
        art = {"id": new_id(), "project_id": ext["project_id"], "sha256": digest,
               "byte_size": len(payload), "media_type": "text/csv" if body.format == "csv" else "application/json",
               "status": "ready", "classification": "synthetic", "created_at": now_iso()}
        store.artifacts[art["id"]] = art; store.artifact_bytes[art["id"]] = payload
        exp = {"id": new_id(), "project_id": ext["project_id"], "extraction_id": ext["id"],
               "review_revision": body.review_revision, "artifact_id": art["id"],
               "manifest_sha256": digest, "incomplete": incomplete, "warnings": warnings,
               "created_at": now_iso(), "format": body.format}
        store.exports[exp["id"]] = exp
        return {k: exp[k] for k in ("id", "project_id", "extraction_id", "review_revision",
                                     "artifact_id", "manifest_sha256", "incomplete", "warnings", "created_at")}

@router.get("/evf/exports/{export_id}")
async def evf_get_export(request: Request, export_id: str = PathParam(...),
                         user: UserContext = Depends(require_object_capability("analyst"))):
    exp = store.exports.get(export_id)
    if not exp: raise HTTPException(404, "Export not found")
    _check_actual(user, exp["project_id"], request.headers.get("X-Project-Id"))
    return {k: exp[k] for k in ("id", "project_id", "extraction_id", "review_revision",
                                 "artifact_id", "manifest_sha256", "incomplete", "warnings", "created_at")}
