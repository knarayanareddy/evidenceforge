"""Live OIDC integration against the local synthetic IdP over real HTTP.

Skipped when the IdP is not running (start: .venv/bin/python scripts/local_idp.py 8799).
This is a synthetic local IdP — production IdP integration remains operator-gated.
"""
import os, uuid
import httpx, pytest
from src.core.config import settings
from src.core import security

ISSUER = os.environ.get("EVF_TEST_OIDC_ISSUER")
pytestmark = pytest.mark.skipif(not ISSUER, reason="EVF_TEST_OIDC_ISSUER not set: local IdP not running")
ORG = str(uuid.uuid4()); PROJ = str(uuid.uuid4()); SUB = str(uuid.uuid4())

@pytest.fixture(autouse=True)
def cfg():
    old = (settings.OIDC_ISSUER, settings.OIDC_CLIENT_ID)
    settings.OIDC_ISSUER, settings.OIDC_CLIENT_ID = ISSUER, "evf-client"
    security._jwks_cache.update(at=0.0, keys={})
    yield
    settings.OIDC_ISSUER, settings.OIDC_CLIENT_ID = old
    security._jwks_cache.update(at=0.0, keys={})

def mint(**kw):
    body = {"sub": SUB, "org_id": ORG, "org_role": "admin", "project_roles": {PROJ: ["analyst"]}, **kw}
    return httpx.post(f"{ISSUER}/token", json=body, timeout=5).json()["access_token"]

def test_valid_token_verifies_with_membership_claims():
    ctx = security.verify_token("Bearer " + mint())
    assert ctx and ctx.user_id == SUB and ctx.organization_id == ORG
    assert ctx.has_project_capability(PROJ, "analyst")

def test_tampered_and_expired_rejected():
    tok = mint()
    assert security.verify_token("Bearer " + tok[:-3] + "xxx") is None
    assert security.verify_token("Bearer " + mint(ttl=-10)) is None

def test_static_test_tokens_still_rejected():
    assert security.verify_token("Bearer test-token-admin") is None
