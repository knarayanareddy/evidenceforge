"""Security, token parsing, and metadata redaction utilities."""
from typing import Dict, Any, Optional, Set
from pydantic import BaseModel, field_validator

FORBIDDEN_METADATA_KEYS = {
    'api_key', 'authorization', 'access_token', 'refresh_token',
    'password', 'client_secret', 'cookie', 'secret'
}

ALLOWED_METADATA_KEYS = {
    'operation_id', 'name', 'outcome', 'input_tokens', 'output_tokens',
    'redacted', 'reason'
}


class UserContext(BaseModel):
    user_id: str
    organization_id: str
    org_role: str = "member"  # "member" or "admin"
    project_roles: Dict[str, Set[str]] = {}  # project_id -> Set[role]

    @field_validator("project_roles", mode="before")
    @classmethod
    def normalize_project_roles(cls, v):
        if not isinstance(v, dict):
            return {}
        normalized = {}
        for proj_id, roles in v.items():
            if isinstance(roles, str):
                normalized[str(proj_id)] = {roles}
            elif isinstance(roles, (list, tuple, set)):
                normalized[str(proj_id)] = {str(r) for r in roles}
            else:
                normalized[str(proj_id)] = set()
        return normalized

    def has_project_capability(self, project_id: str, required_capability: str) -> bool:
        """Check if user holds the required capability for the specified project.
        Supports union of multiple granted roles (e.g., analyst + operator).
        Capability hierarchy:
          - viewer: granted by viewer, analyst, operator, maintainer
          - analyst: granted by analyst, maintainer
          - operator: granted by operator, maintainer
          - maintainer: granted by maintainer
        """
        roles = self.project_roles.get(str(project_id), set())
        CAPABILITY_EXPANSION = {
            "viewer": {"viewer"},
            "analyst": {"viewer", "analyst"},
            "operator": {"viewer", "operator"},
            "maintainer": {"viewer", "analyst", "operator", "maintainer"}
        }
        user_caps: Set[str] = set()
        for r in roles:
            user_caps.update(CAPABILITY_EXPANSION.get(r, {r}))
        return required_capability in user_caps


def redact_metadata(value: Dict[str, Any]) -> Dict[str, Any]:
    """Allowlisted metadata scrubbing; strips credentials and nested blobs."""
    if not isinstance(value, dict):
        raise ValueError("Metadata must be a dictionary")

    sanitized = {}
    for k, v in value.items():
        k_lower = k.lower()
        if k_lower in FORBIDDEN_METADATA_KEYS:
            continue
        if k not in ALLOWED_METADATA_KEYS:
            continue
        if k == 'reason':
            # Free text can contain freeform secrets; omit in strict metadata capture
            continue
        if isinstance(v, (dict, list)):
            raise ValueError("Nested metadata structures are forbidden")
        sanitized[k] = v
    return sanitized


_jwks_cache = {"at": 0.0, "keys": {}}

def _jwks(issuer: str):
    """Fetch+cache JWKS (max 1h); no jku/x5u from token headers is ever trusted."""
    import time
    now = time.time()
    if now - _jwks_cache["at"] < 3600 and _jwks_cache["keys"]:
        return _jwks_cache["keys"]
    url = issuer.rstrip("/") + "/.well-known/jwks.json"
    if not url.startswith(("https://", "http://127.0.0.1", "http://localhost")):
        raise ValueError("jwks_scheme_not_allowed")
    import httpx  # fixed path on the operator-configured issuer only
    keys = {k["kid"]: k for k in httpx.get(url, timeout=5).json()["keys"]}
    _jwks_cache.update(at=now, keys=keys)
    return keys


def verify_token(token: str) -> Optional[UserContext]:
    """Verify an OIDC RS256 bearer token against the configured issuer JWKS.

    Fail-closed: returns None unless OIDC_ISSUER is an http(s) issuer with a
    reachable JWKS and the token passes signature/iss/aud/exp validation.
    Membership comes from preprovisioned IdP claims (org_id, org_role,
    project_roles) — never from static test tokens or bearer UUIDs.
    The placeholder default issuer (auth.example.com) never verifies.
    """
    try:
        import jwt as _jwt
        from src.core.config import settings
        issuer = settings.OIDC_ISSUER
        if not issuer.startswith(("https://", "http://127.0.0.1", "http://localhost")) \
                or "auth.example.com" in issuer:
            return None
        raw = token[7:] if token.startswith("Bearer ") else token
        header = _jwt.get_unverified_header(raw)
        jwk = _jwks(issuer).get(header.get("kid", ""))
        if jwk is None:
            _jwks_cache["at"] = 0.0  # one refresh on unknown kid
            jwk = _jwks(issuer).get(header.get("kid", ""))
            if jwk is None:
                return None
        import base64
        from cryptography.hazmat.primitives.asymmetric import rsa as _rsa
        dec = lambda b: int.from_bytes(base64.urlsafe_b64decode(b + "=" * (-len(b) % 4)), "big")
        key = _rsa.RSAPublicNumbers(dec(jwk["e"]), dec(jwk["n"])).public_key()
        claims = _jwt.decode(raw, key, algorithms=["RS256"], audience=settings.OIDC_CLIENT_ID,
                             issuer=issuer, options={"require": ["exp", "iss", "sub"]})
        return UserContext(user_id=str(claims["sub"]),
                           organization_id=str(claims["org_id"]),
                           org_role=str(claims.get("org_role", "member")),
                           project_roles=claims.get("project_roles", {}))
    except Exception:
        return None
