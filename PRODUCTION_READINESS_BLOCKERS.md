# EvidenceForge — Production Readiness: Blockers & Remaining Work

**Status: NOT production ready. `production_ready=false`; `python scripts/release_gate.py` exits 1.**
This file is the authoritative checklist of what still stands between the current
fixture-first build and a production-grade release. It is a note of record, not a
waiver: no item here may be marked complete without the evidence named for it, and
independent-review items may not be self-approved by the implementing agent.

State as of 2026-11-04 (main @ merge of PR #1, commit `63c4da1`). Suite: 155 tests
pass on Python 3.11 and source-built Python 3.12.11, including the real
PostgreSQL 16 and live synthetic-IdP suites when their env vars are set.

---

## 1. What is already done (do not re-litigate)

- B08 vertical slice: upload → document → worker parse → 8-field typed extraction →
  evidence-linked review → JSON/CSV export → deletion with read revocation.
- Scoped idempotency (migration `003_scoped_idempotency.sql` + runtime parity):
  project table PK `(project, actor, operation, key)`, organization table for
  project creation, auth-before-replay, 24h window, 409 on divergent request.
- Real PostgreSQL 16.2 verification of migrations/RLS/FK/immutability/fenced
  leases/concurrent idempotency (`tests/test_postgres_integration.py`) and a
  `pg_dump`/`pg_restore` round-trip (`scripts/backup_restore_check.py`).
- OIDC RS256/JWKS bearer verification (`src/core/security.py`), live-tested against
  a local synthetic IdP. Frontend builds on Node 24.
- `docling_local/1` pilot via `docling-parse` with real PDF geometry.
- Security/finance **self-assessment packets** exist in `evidence/reviews/` —
  prepared for review, explicitly not approvals.

## 2. Blocking release gates (from `evidence/release-status.json`)

Each of these currently reads `not_run` and keeps the release gate at exit 1.

| # | Gate | What is missing | Evidence required to close | Owner |
|---|------|-----------------|----------------------------|-------|
| 1 | `docling_integration` | Full Docling ML pipeline never ran: HuggingFace layout/OCR model assets are unreachable from the sandbox egress allowlist, so conversion fails closed (`LocalEntryNotFoundError`). Only the no-ML `docling-parse` path is proven. | Pinned Docling version + model asset hashes/licences, contained no-egress run, successful parse of synthetic **and** rights-cleared pilot PDFs, timeout/malformed/encrypted-input tests, evidence-mapping checks against rendered pages. Keep `docling_local/1` limited until then. | Engineering + operator (asset provisioning) |
| 2 | `executor_boundary` | No Docker/`runsc` in the authoring environment; worker containment (non-root `10001:10001`, read-only FS, `cap_drop: ALL`, no egress, CPU/mem limits) is configuration, not observed behaviour. | Built images run under the hardened compose/`infra/runtime-policy.yaml` settings; escape/limit tests; worker crash-recovery and cancellation-semantics runs. | Engineering |
| 3 | `load_chaos` | No load, soak, or fault-injection results at any scale. | Load profile vs. agreed targets (upload/parse throughput, p95 latencies), worker-kill/DB-restart chaos runs, results recorded in `evidence/`. | Engineering |
| 4 | `accessibility_manual` | UI has never had a manual/screen-reader/keyboard pass; evidence highlighting accuracy and the text fallback are unverified by a human. | Manual a11y audit of the 4 screens (`evf_library`, `evf_source`, `evf_review`, `evf_export`) incl. keyboard order, focus, non-colour status, text alternatives; findings fixed and re-checked. | Independent reviewer |
| 5 | `domain_holdout` | No real annual-report corpus: zero rights-cleared real documents, no dual annotation, no measured extraction accuracy. Synthetic fixtures cannot close this. | Licensed/synthetic-labelled corpus + holdout split, dual-annotated gold fields, accuracy report per field (incl. wrong-period/scale error rates). | Domain + operator (data rights) |
| 6 | `statistical_review` | No statistical treatment of extraction quality; the finance self-assessment is unreviewed. Known finding to disposition: the bundled PDF's real text lacks the fixture JSON's "units 1000" statement, so fixture scale metadata must never be cited as parser accuracy. | Independent statistical review of holdout results, confidence intervals, error taxonomy; written disposition of the fixture-scale finding. | Independent statistician / finance reviewer |
| 7 | `independent_security_review` | Only self-assessment exists (pip-audit clean on range pins, Bandit 0 after fixes). No external review, no penetration test, threat model unsigned. | Independent security review report: authn/z, RLS tenancy, idempotency replay-after-revocation, upload/parser attack surface, export injection, secrets handling; criticals fixed and re-tested. | Independent security reviewer |
| 8 | `clean_room_agent_trial` | No independent agent/developer has built and run the product from the repo alone. | Clean-room trial report: fresh checkout → documented commands → working journey, with all ambiguities logged as doc bugs. | Independent trialist |
| 9 | `release_images_sbom` | No deployable images built, no SBOM, dependencies are range pins (`requirements.txt`), not hash-locked; the 3.12/Node 24 runtimes in evidence
...[truncated 2119 chars]