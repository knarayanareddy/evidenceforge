"""FastAPI dependency injection utilities with fail-closed authorization."""
from typing import Optional, Callable
import uuid
from fastapi import Header, HTTPException, status, Depends, Path, Request
from src.core.security import verify_token, UserContext


async def get_current_user(authorization: Optional[str] = Header(None)) -> UserContext:
    """Authenticate caller via Bearer token.
    Fail-closed: Rejects unauthenticated requests with 401. Never returns mock users.
    """
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication credentials required",
            headers={"WWW-Authenticate": "Bearer"}
        )
    ctx = verify_token(authorization)
    if not ctx:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication token",
            headers={"WWW-Authenticate": "Bearer"}
        )
    return ctx


async def require_org_admin(user: UserContext = Depends(get_current_user)) -> UserContext:
    """Enforce Organization Admin privilege (separate from project roles)."""
    if user.org_role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Operation requires Organization Admin privilege"
        )
    return user


def require_project_capability(required_capability: str) -> Callable:
    """Enforce capability-based project authorization for routes containing {project_id} in path.
    Requires an explicit Path parameter with no default value.
    """
    async def project_capability_checker(
        project_id: str = Path(..., description="Target project identifier"),
        user: UserContext = Depends(get_current_user)
    ) -> UserContext:
        if not user.has_project_capability(project_id, required_capability):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient project privileges: requires '{required_capability}' capability"
            )
        return user
    return project_capability_checker


def user_has_capability(user: UserContext, project_id: str, capability: str) -> bool:
    """Capability check: verified token roles UNION runtime store grants
    (e.g. project creator grant recorded at creation time)."""
    if user.has_project_capability(project_id, capability):
        return True
    from src.services.store import store
    granted = store.user_roles(user.user_id, str(project_id))
    if not granted:
        return False
    probe = UserContext(user_id=user.user_id, organization_id=user.organization_id,
                        org_role=user.org_role, project_roles={str(project_id): granted})
    return probe.has_project_capability(project_id, capability)


def resolve_object_project(kind: str, object_id: str):
    """Return the object's ACTUAL project_id from persistence, or None.
    X-Project-Id is only a hint and is never used as ownership proof."""
    from src.services.store import store
    table = {"document": store.documents, "parse": store.parses,
             "extraction": store.extractions, "export": store.exports,
             "artifact": store.artifacts, "job": store.jobs,
             "upload": store.uploads}.get(kind, {})
    obj = table.get(str(object_id))
    if obj is None:
        return None
    if kind == "parse":
        doc = store.documents.get(obj["document_id"])
        return doc["project_id"] if doc else None
    if kind == "upload":
        return obj.get("project_id")
    return obj.get("project_id")


# Backward-compatibility alias for project-path routes
require_project_role = require_project_capability


def require_object_capability(required_capability: str) -> Callable:
    """Enforce capability-based authorization for object routes lacking {project_id} in path
    (e.g., /artifacts/{artifact_id}, /jobs/{job_id}, /uploads/{upload_id}, /evf/documents/{document_id}).

    Fail-closed: In B00 baseline before runtime object-to-project DB resolution (B02/B04),
    verifies project scope via the X-Project-Id header. If absent or caller lacks the required
    capability on that project, fails closed with 403 Forbidden.
    """
    async def object_capability_checker(
        request: Request,
        x_project_id: Optional[str] = Header(None, alias="X-Project-Id"),
        user: UserContext = Depends(get_current_user)
    ) -> UserContext:
        if not x_project_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Access denied: Object-to-project scope cannot be verified without project context. "
                    f"Requires '{required_capability}' capability."
                )
            )
        if not user.has_project_capability(x_project_id, required_capability):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient project privileges: requires '{required_capability}' capability on scoped project"
            )
        return user
    return object_capability_checker


async def verify_idempotency_key(idempotency_key: Optional[str] = Header(None)) -> str:
    """Validate Idempotency-Key header is a valid UUIDv4 for mutating requests."""
    if not idempotency_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing required 'Idempotency-Key' header"
        )
    try:
        uuid_obj = uuid.UUID(idempotency_key)
        return str(uuid_obj)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="'Idempotency-Key' must be a valid UUIDv4 string"
        )
