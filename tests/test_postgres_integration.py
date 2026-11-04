"""Real PostgreSQL 16 integration tests — NO SQLite/mock substitution.

Requires EVF_TEST_PG_ADMIN_DSN (e.g. postgresql://postgres@/postgres?host=/tmp/evf-pgdata).
Provision locally with:  .venv/bin/python scripts/provision_local_pg.py
Skipped (not passed) when the DSN is absent.
"""
import os, threading, uuid
import pytest

psycopg = pytest.importorskip("psycopg")
ADMIN = os.environ.get("EVF_TEST_PG_ADMIN_DSN")
pytestmark = pytest.mark.skipif(not ADMIN, reason="EVF_TEST_PG_ADMIN_DSN not set: real PostgreSQL unavailable")

ROOT = os.path.join(os.path.dirname(__file__), "..")
DB = "evf_test_" + uuid.uuid4().hex[:8]
ORG_A, ORG_B = str(uuid.uuid4()), str(uuid.uuid4())
PROJ_A, PROJ_B = str(uuid.uuid4()), str(uuid.uuid4())
USER = str(uuid.uuid4())

def dsn(db):
    from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode
    p = urlparse(ADMIN); q = dict(parse_qsl(p.query))
    return urlunparse(p._replace(path="/" + db, query=urlencode(q)))

@pytest.fixture(scope="module")
def pg():
    with psycopg.connect(ADMIN, autocommit=True) as c:
        c.execute(f'CREATE DATABASE "{DB}"')
    with psycopg.connect(dsn(DB)) as c:
        for f in ("001_baseline.sql", "002_roles.sql", "003_scoped_idempotency.sql"):
            c.execute(open(os.path.join(ROOT, "database/migrations", f)).read())
        c.execute("INSERT INTO core.organizations VALUES (%s,'A'),(%s,'B')", (ORG_A, ORG_B))
        c.execute("INSERT INTO core.users VALUES (%s,'https://idp.test','sub-1')", (USER,))
        c.execute("INSERT INTO core.projects(id,organization_id,name) VALUES (%s,%s,'PA'),(%s,%s,'PB')",
                  (PROJ_A, ORG_A, PROJ_B, ORG_B))
        c.execute("DO $$ BEGIN IF NOT EXISTS(SELECT FROM pg_roles WHERE rolname='evf_test_app') "
                  "THEN CREATE ROLE evf_test_app LOGIN; END IF; END $$")
        c.execute("GRANT baseline_app TO evf_test_app")
    yield dsn(DB)
    with psycopg.connect(ADMIN, autocommit=True) as c:
        c.execute(f'DROP DATABASE "{DB}" WITH (FORCE)')

def app_conn(db, project=None, org=None):
    conn = psycopg.connect(db.replace("postgresql://postgres@", "postgresql://evf_test_app@"), autocommit=False)
    if project: conn.execute("SELECT set_config('baseline.project_id',%s,true)", (project,))
    if org: conn.execute("SELECT set_config('baseline.organization_id',%s,true)", (org,))
    return conn

def test_pg_version_16(pg):
    with psycopg.connect(pg) as c:
        assert c.execute("SHOW server_version").fetchone()[0].startswith("16.")

def test_scoped_idempotency_tables_and_rls(pg):
    with psycopg.connect(pg) as c:
        rows = {r[0] for r in c.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname='core' AND tablename LIKE 'idempotency%'")}
        assert rows == {"idempotency_project", "idempotency_organization"}
        assert c.execute("SELECT relrowsecurity AND relforcerowsecurity FROM pg_class "
                         "WHERE relname='idempotency_project'").fetchone()[0] is True

def test_same_key_distinct_scopes_allowed(pg):
    key = str(uuid.uuid4())
    with app_conn(pg, project=PROJ_A) as c:
        c.execute("INSERT INTO core.idempotency_project(project_id,actor_id,operation,key,request_sha256,response_status,response_body,expires_at) VALUES (%s,%s,'op',%s,'h',201,'{}',now()+interval '24h')",
                  (PROJ_A, USER, key)); c.commit()
    with app_conn(pg, project=PROJ_B) as c:  # same key, different project: allowed
        c.execute("INSERT INTO core.idempotency_project(project_id,actor_id,operation,key,request_sha256,response_status,response_body,expires_at) VALUES (%s,%s,'op',%s,'h',201,'{}',now()+interval '24h')",
                  (PROJ_B, USER, key)); c.commit()
    with app_conn(pg, org=ORG_B) as c:  # same key, org scope: allowed
        c.execute("INSERT INTO core.idempotency_organization(organization_id,actor_id,operation,key,request_sha256,response_status,response_body,expires_at) VALUES (%s,%s,'foundation_create_project',%s,'h',201,'{}',now()+interval '24h')",
                  (ORG_B, USER, key)); c.commit()

def test_concurrent_duplicate_creates_one(pg):
    key = str(uuid.uuid4()); results = []
    def worker():
        try:
            with app_conn(pg, org=ORG_A) as c:
                c.execute("INSERT INTO core.idempotency_organization(organization_id,actor_id,operation,key,request_sha256,response_status,response_body,expires_at) VALUES (%s,%s,'foundation_create_project',%s,'h',201,'{}',now()+interval '24h')",
                          (ORG_A, USER, key)); c.commit(); results.append("ok")
        except psycopg.errors.UniqueViolation:
            results.append("conflict")
    ts = [threading.Thread(target=worker) for _ in range(4)]
    [t.start() for t in ts]; [t.join() for t in ts]
    assert results.count("ok") == 1 and results.count("conflict") == 3

def test_rollback_does_not_strand_success(pg):
    key = str(uuid.uuid4())
    conn = app_conn(pg, org=ORG_A)
    conn.execute("INSERT INTO core.idempotency_organization(organization_id,actor_id,operation,key,request_sha256,response_status,response_body,expires_at) VALUES (%s,%s,'foundation_create_project',%s,'h',201,'{}',now()+interval '24h')",
                 (ORG_A, USER, key))
    conn.rollback(); conn.close()
    with app_conn(pg, org=ORG_A) as c:  # retry after rollback must succeed
        c.execute("INSERT INTO core.idempotency_organization(organization_id,actor_id,operation,key,request_sha256,response_status,response_body,expires_at) VALUES (%s,%s,'foundation_create_project',%s,'h',201,'{}',now()+interval '24h')",
                  (ORG_A, USER, key)); c.commit()

def test_rls_wrong_scope_invisible_and_context_reset(pg):
    with app_conn(pg, project=PROJ_A, org=ORG_A) as c:
        assert c.execute("SELECT id FROM core.projects").fetchall() == [(uuid.UUID(PROJ_A),)]
    # Pooled-connection reuse: new transaction without context sees nothing.
    conn = app_conn(pg, project=PROJ_A, org=ORG_A); conn.commit()
    # set_config(...,true) is transaction-local: after commit the pooled
    # connection carries no project/org context, so RLS must hide everything.
    assert conn.execute("SELECT id FROM core.projects").fetchall() == []
    conn.close()

def test_fk_and_review_immutability(pg):
    with psycopg.connect(pg) as c:
        with pytest.raises(psycopg.errors.ForeignKeyViolation):
            c.execute("INSERT INTO core.projects(id,organization_id,name) VALUES (%s,%s,'X')",
                      (str(uuid.uuid4()), str(uuid.uuid4())))
        c.rollback()
        # seed document->parse->extraction->review then attempt UPDATE
        art = str(uuid.uuid4()); doc = str(uuid.uuid4()); job = str(uuid.uuid4())
        par = str(uuid.uuid4()); ext = str(uuid.uuid4()); rev = str(uuid.uuid4())
        c.execute("INSERT INTO core.artifacts VALUES (%s,%s,%s,10,'application/pdf','synthetic','ready','k1',now())",
                  (art, PROJ_A, "a" * 64))
        c.execute("INSERT INTO evf.documents VALUES (%s,%s,1,%s,%s,'T','accepted',1,now())", (doc, PROJ_A, art, "b" * 64))
        c.execute("INSERT INTO core.jobs(id,project_id,kind,state,payload) VALUES (%s,%s,'evf_parse','queued','{}')", (job, PROJ_A))
        c.execute("INSERT INTO evf.parses VALUES (%s,%s,%s,%s,'fixture/1',%s,'parsed',%s,NULL,1,now())",
                  (par, PROJ_A, doc, "b" * 64, "c" * 64, job))
        c.execute("INSERT INTO evf.extractions VALUES (%s,%s,%s,'annual-report-8/1',1,'[1,2,3,4,5,6,7,8]',now())", (ext, PROJ_A, par))
        c.execute("INSERT INTO evf.reviews VALUES (%s,%s,%s,2,1,%s,'[]',now())", (rev, PROJ_A, ext, USER))
        c.commit()
        with pytest.raises(psycopg.Error):
            c.execute("UPDATE evf.reviews SET patches='[]' WHERE id=%s", (rev,))
        c.rollback()

def test_fenced_lease_stale_completion_rejected(pg):
    job = str(uuid.uuid4())
    with psycopg.connect(pg) as c:
        c.execute("INSERT INTO core.jobs(id,project_id,kind,state,payload) VALUES (%s,%s,'evf_parse','queued','{}')", (job, PROJ_A))
        leased = c.execute("""WITH candidate AS (SELECT id FROM core.jobs WHERE id=%s AND project_id=%s AND state='queued'
            ORDER BY created_at,id FOR UPDATE SKIP LOCKED LIMIT 1)
            UPDATE core.jobs j SET state='leased', attempt=j.attempt+1, fence=j.fence+1,
            lease_until=now()+interval '30 seconds', revision=j.revision+1, updated_at=now()
            FROM candidate c WHERE j.id=c.id RETURNING j.fence""", (job, PROJ_A)).fetchone()
        c.commit()
        stale = c.execute("""UPDATE core.jobs SET state='succeeded', lease_until=NULL WHERE id=%s AND project_id=%s
            AND fence=%s AND state IN ('leased','running') AND lease_until>now()""",
            (job, PROJ_A, leased[0] + 99)).rowcount
        good = c.execute("""UPDATE core.jobs SET state='succeeded', lease_until=NULL WHERE id=%s AND project_id=%s
            AND fence=%s AND state IN ('leased','running') AND lease_until>now()""",
            (job, PROJ_A, leased[0])).rowcount
        c.commit()
        assert stale == 0 and good == 1
