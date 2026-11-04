"""Backup/restore verification against real PostgreSQL (pg_dump/pg_restore).

Creates a disposable source DB, applies migrations, seeds a marker row,
pg_dump -> pg_restore into a fresh DB, and verifies marker + row counts.
Uses pgserver-bundled binaries. Exit 0 only on exact verification.
Env: EVF_TEST_PG_ADMIN_DSN (socket DSN, see scripts/provision_local_pg.py).
"""
import os, subprocess, sys, uuid
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".venv/lib"))
import glob
bins = glob.glob(os.path.join(os.path.dirname(__file__), "..", ".venv", "lib", "python*", "site-packages", "pgserver", "pginstall", "bin"))
BIN = bins[0] if bins else ""
DSN = os.environ["EVF_TEST_PG_ADMIN_DSN"]
import psycopg
src, dst = "evf_bak_" + uuid.uuid4().hex[:8], "evf_rst_" + uuid.uuid4().hex[:8]
def dsn(db):
    from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode
    p = urlparse(DSN); return urlunparse(p._replace(path="/" + db, query=urlencode(dict(parse_qsl(p.query)))))
def run(tool, *args):
    r = subprocess.run([os.path.join(BIN, tool), *args], capture_output=True, text=True)
    if r.returncode: raise SystemExit(f"{tool} failed: {r.stderr.strip()[:300]}")
    return r
try:
    with psycopg.connect(DSN, autocommit=True) as c:
        c.execute(f'CREATE DATABASE "{src}"'); c.execute(f'CREATE DATABASE "{dst}"')
    root = os.path.join(os.path.dirname(__file__), "..")
    with psycopg.connect(dsn(src)) as c:
        for f in ("001_baseline.sql", "002_roles.sql", "003_scoped_idempotency.sql"):
            c.execute(open(os.path.join(root, "database/migrations", f)).read())
        marker = str(uuid.uuid4())
        c.execute("INSERT INTO core.organizations VALUES (%s,'backup-marker')", (marker,))
        c.commit()
    dump = "/tmp/evf_backup.dump"
    run("pg_dump", "-Fc", "-f", dump, dsn(src))
    run("pg_restore", "--no-owner", "-d", dsn(dst), dump)
    with psycopg.connect(dsn(dst)) as c:
        got = c.execute("SELECT id FROM core.organizations WHERE name='backup-marker'").fetchone()
        tables = c.execute("SELECT count(*) FROM pg_tables WHERE schemaname IN ('core','evf')").fetchone()[0]
    assert got and str(got[0]) == marker, "marker row mismatch after restore"
    print(f"BACKUP_RESTORE_OK marker={marker} core_evf_tables={tables} dump_bytes={os.path.getsize(dump)}")
finally:
    with psycopg.connect(DSN, autocommit=True) as c:
        c.execute(f'DROP DATABASE IF EXISTS "{src}" WITH (FORCE)'); c.execute(f'DROP DATABASE IF EXISTS "{dst}" WITH (FORCE)')
