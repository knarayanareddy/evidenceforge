"""Provision a disposable local PostgreSQL 16 (bundled pgserver wheel) and print env.

Usage: .venv/bin/python scripts/provision_local_pg.py  # leaves server running in this process is NOT
possible for a one-shot script; use tests/conftest env instead: start the keeper:
  .venv/bin/python -c "import pgserver,time; pgserver.get_server('/tmp/evf-pgdata'); time.sleep(86400)" &
Then: EVF_TEST_PG_ADMIN_DSN='postgresql://postgres@/postgres?host=/tmp/evf-pgdata'
"""
import pgserver
srv = pgserver.get_server("/tmp/evf-pgdata")
print("EVF_TEST_PG_ADMIN_DSN=" + srv.get_uri())
print("Server stays up while this process lives; run with `&` / a process manager.")
import time; time.sleep(86400)
