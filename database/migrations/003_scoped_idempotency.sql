-- 003_scoped_idempotency.sql — reviewed correction to 001/002.
-- The legacy core.idempotency used PRIMARY KEY(actor_id,route,key) with nullable
-- org/project scope and project-only RLS, allowing cross-scope key collisions.
-- This migration (apply once; do not edit 001/002 if already applied anywhere)
-- replaces it with two properly scoped tables. Runtime roles keep NOBYPASSRLS.
BEGIN;
DROP TABLE IF EXISTS core.idempotency;
-- Ordinary project mutations
CREATE TABLE core.idempotency_project(
  project_id uuid NOT NULL REFERENCES core.projects(id),
  actor_id uuid NOT NULL, operation text NOT NULL, key uuid NOT NULL,
  request_sha256 text NOT NULL, response_status integer NOT NULL,
  response_body jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
  expires_at timestamptz NOT NULL,
  PRIMARY KEY(project_id, actor_id, operation, key));
ALTER TABLE core.idempotency_project ENABLE ROW LEVEL SECURITY;
ALTER TABLE core.idempotency_project FORCE ROW LEVEL SECURITY;
CREATE POLICY project_scope ON core.idempotency_project
  USING (project_id = nullif(current_setting('baseline.project_id', true), '')::uuid)
  WITH CHECK (project_id = nullif(current_setting('baseline.project_id', true), '')::uuid);
-- Project creation (organization-scoped; org+actor derive from verified identity)
CREATE TABLE core.idempotency_organization(
  organization_id uuid NOT NULL REFERENCES core.organizations(id),
  actor_id uuid NOT NULL, operation text NOT NULL, key uuid NOT NULL,
  request_sha256 text NOT NULL, response_status integer NOT NULL,
  response_body jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
  expires_at timestamptz NOT NULL,
  PRIMARY KEY(organization_id, actor_id, operation, key));
ALTER TABLE core.idempotency_organization ENABLE ROW LEVEL SECURITY;
ALTER TABLE core.idempotency_organization FORCE ROW LEVEL SECURITY;
CREATE POLICY org_scope ON core.idempotency_organization
  USING (organization_id = nullif(current_setting('baseline.organization_id', true), '')::uuid)
  WITH CHECK (organization_id = nullif(current_setting('baseline.organization_id', true), '')::uuid);
GRANT SELECT,INSERT,UPDATE ON core.idempotency_project, core.idempotency_organization TO baseline_app;
-- Semantics: authenticate+authorize BEFORE replay lookup; same scoped key +
-- different request_sha256 => 409; replay window 24h; after expiry or after
-- membership revocation the stored response is never replayed (auth runs first).
COMMIT;
