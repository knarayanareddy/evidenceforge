# Repository Map (reviewed mapping)

| Inherited reference | This repository |
|---|---|
| `apps/api/*` | `src/` (FastAPI: `src/api/foundation.py`, `src/api/evf.py`, `src/services/`, `src/core/`, `src/models/`) |
| `apps/dispatcher/*` | `src/worker/` (`python -m src.worker`) |
| Web UI | `apps/web/` (React + Vite + strict TypeScript) |
| Authority plan | `implementation/implementation-plan.json` (local; fixed stale `../05_Shared_Baseline/` path in `product-focus.json`) |

`reference/` and the ZIPs are provenance only, never application roots and are
never edited to make verification pass. Manifest note: `verify_manifest.py`
covers 314 protected contract/reference files; it does NOT cover root
`src/` or `tests/`, so a passing manifest is not whole-repository certification.

Runtime status: local store backend is process-local for development/tests.
PostgreSQL 16 guarantees (RLS, fenced leases, scoped-idempotency tables in
`database/migrations/003_scoped_idempotency.sql`) require a real PostgreSQL
run and remain an open qualification gate; SQLite is not substituted for them.
