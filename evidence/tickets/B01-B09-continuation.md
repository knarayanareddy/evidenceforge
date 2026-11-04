# Continuation evidence — 2026-11-04 (machine-complete; external review still pending)
## PostgreSQL 16 suite — DONE (real DB, no substitute)
pgserver wheel (PyPI) bundles PostgreSQL 16.2 binaries — used as disposable local PG.
tests/test_postgres_integration.py: 8 passed — migrations 001+002+003 applied, RLS
wrong-scope invisibility, pooled transaction-local context reset, same key across
distinct org/project scopes, 4-thread concurrent duplicate (exactly 1 success),
rollback-then-retry, FK enforcement, evf.reviews immutability trigger, fenced lease
(stale fence completes 0 rows). Run: EVF_TEST_PG_ADMIN_DSN='postgresql://postgres@/postgres?host=/tmp/evf-pgdata'
## Backup/restore — DONE: scripts/backup_restore_check.py → BACKUP_RESTORE_OK
(pg_dump -Fc / pg_restore round-trip, marker row verified, disposable DBs dropped).
## OIDC live integration — DONE (synthetic local IdP): src/core/security.py now verifies
RS256 via issuer JWKS (httpx, scheme allowlist, 1h cache, unknown-kid refresh, iss/aud/exp
required; claims org_id/org_role/project_roles = preprovisioned membership). tests/
test_oidc_integration.py 3 passed vs scripts/local_idp.py over real HTTP. Static test
tokens still rejected. Production IdP + browser login/callback/session/logout routes OPEN.
## Python 3.12 — DONE via source build: uv/GitHub-release assets blocked (TLS/egress),
Debian has no 3.12; built CPython 3.12.11 from codeload.github.com source + OpenSSL 3.3.2
+ zlib + libffi headers (crafted ffi.h; system libffi.so.8). Full suite run on 3.12.
## Node 24 — DONE: npm `node@24.22.2` package (registry.npmjs.org). apps/web builds.
## B09 Docling pilot — PARTIAL: full docling installed from PyPI but ML conversion fails
closed (HuggingFace model assets unreachable: LocalEntryNotFoundError). docling-parse
(the Docling PDF parser, no ML assets) WORKS: docling_local/1 enabled with real
textline geometry; tests/test_docling_pilot.py passed. Layout/OCR model quality: OPEN.
## Reviews — packets prepared, NOT self-approved: evidence/reviews/
security-self-assessment.md (pip-audit clean on ranges, bandit 0 after fixes),
finance-self-assessment.md (incl. finding: PDF lacks the fixture's "units 1000" text).
independent_security_review / operator_signoff / domain_holdout remain BLOCKING.
