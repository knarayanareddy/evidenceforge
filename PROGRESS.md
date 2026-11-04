# Progress (machine-complete vs external-review-pending)
- B00 recorded: evidence/tickets/B00-start.md. 137 baseline tests re-verified.
- Scoped idempotency: migration 003_scoped_idempotency.sql (project table
  PK(project,actor,operation,key)+project RLS; org table for project creation
  PK(org,actor,operation,key)+org RLS; auth before replay; 24h window; 409 on
  different request). Runtime implements same semantics in the local store.
- Foundation implemented: projects (org-scoped idempotent creation, creator
  maintainer grant), PDF-only bounded uploads w/ SHA-256 finalize, artifacts
  (actual-project resolution, X-Project-Id mismatch → 404), jobs + cancel.
- EVF B08 fixture slice: bundled-PDF-only fixture/1 worker parse, exactly 8
  fields (Decimal base units, dash≠zero, explicit missing reasons), evidence
  quote verification, append-only reviews (If-Match 428/412, body-base 409,
  forged evidence 422), JSON/CSV export (incomplete warnings, CSV injection
  mitigation incl. leading whitespace), deletion revokes all derived reads.
- Worker: src/worker (`python -m src.worker`), queued→running→succeeded/failed,
  cancel_requested→cancelled. Frontend: apps/web (4 UI screens, in-memory token).
- Tests: 142 passed (137 baseline w/ 2 stub-expectation tests updated to the
  implemented behavior + 5 new journey/normalization/idempotency tests).
## Open gates / blockers (NOT claimed)
PostgreSQL 16 real-DB tests (incl. pooled context reset, concurrent duplicates),
Python 3.12 / Node 24 smoke, Docker images, OIDC live integration, B09 Docling
(disabled: 501), backup/restore, accessibility manual check, domain holdout,
independent security/finance reviews, operator signoff. release_gate still exit 1.

# Continuation 2026-11-04 — see evidence/tickets/B01-B09-continuation.md
- PostgreSQL 16.2 (pgserver wheel): 8 real-DB tests pass; backup/restore verified.
- OIDC RS256/JWKS verifier implemented; 3 live tests vs local synthetic IdP pass.
- Python 3.12.11 built from source (codeload) w/ OpenSSL 3.3.2; Node v24.22.2 via npm.
- B09: docling_local/1 real parser (docling-parse) pilot passes; full Docling ML
  pipeline blocked on HuggingFace egress — fails closed, no accuracy claims.
- Release gate now blocks on 10 items (was 15); production_ready stays false.
