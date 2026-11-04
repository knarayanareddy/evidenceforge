"""Application store: thread-safe repository used by API and worker.

Default backend is process-local (development/tests without PostgreSQL).
This does NOT claim PostgreSQL RLS/concurrency guarantees; those are covered
by database/migrations (incl. 003_scoped_idempotency.sql) and remain a
qualification gate until run against real PostgreSQL 16.
"""
import hashlib, json, threading, uuid
from copy import deepcopy
from datetime import datetime, timezone, timedelta

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def new_id():
    return str(uuid.uuid4())

def request_hash(body) -> str:
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()

class Store:
    def __init__(self):
        self.lock = threading.RLock()
        self.projects = {}; self.grants = {}  # (user_id, project_id) -> set(roles)
        self.uploads = {}; self.artifacts = {}; self.artifact_bytes = {}
        self.jobs = {}; self.documents = {}; self.parses = {}; self.extractions = {}
        self.reviews = {}; self.exports = {}; self.deletions = []
        self.idem_project = {}; self.idem_org = {}  # scoped idempotency records

    def reset(self):
        with self.lock:
            self.__init__()

    # --- scoped idempotency: auth must already have happened in the route ---
    def idem_lookup(self, scope_kind, scope_id, actor_id, operation, key):
        table = self.idem_project if scope_kind == "project" else self.idem_org
        rec = table.get((scope_id, actor_id, operation, key))
        if rec and datetime.fromisoformat(rec["expires_at"]) > datetime.now(timezone.utc):
            return rec
        return None

    def idem_save(self, scope_kind, scope_id, actor_id, operation, key, req_hash, status, body):
        table = self.idem_project if scope_kind == "project" else self.idem_org
        table[(scope_id, actor_id, operation, key)] = {
            "request_sha256": req_hash, "status": status, "body": deepcopy(body),
            "expires_at": (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()}

    def grant(self, user_id, project_id, role):
        self.grants.setdefault((user_id, project_id), set()).add(role)

    def user_roles(self, user_id, project_id):
        return set(self.grants.get((user_id, project_id), set()))

store = Store()
