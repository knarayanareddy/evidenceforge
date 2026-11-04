# Security self-assessment (PREPARED FOR independent review — NOT an approval)
Date: 2026-11-04. Reviewer independence: none claimed; signoff gate stays open.
Tooling (this environment): pip-audit on requirements.txt → "No known vulnerabilities
found" (range pins, not hash-locked — lockfile hardening still B01-open);
bandit -r src/ → 0 issues after fixes (B101 assert→explicit raise, B310 urllib→httpx
with scheme allowlist on operator-configured issuer, B108 default tmp path removed).
Verified behaviors: fail-closed auth (401 unauthenticated/invalid, static test tokens
rejected by production verifier), capability unions, object actual-project resolution
(header mismatch 404), scoped idempotency (auth-before-replay, 409 divergence),
evidence forgery rejection, CSV injection neutralization, deletion revocation,
owner NOBYPASSRLS roles, RLS wrong-scope invisibility on PostgreSQL 16.2.
Open for independent reviewer: threat model signoff, OIDC production IdP, session/CSRF
routes from auth-flow.yaml (login/callback/session/logout not yet implemented),
penetration test, SBOM/release images. Status: PENDING INDEPENDENT REVIEW.
