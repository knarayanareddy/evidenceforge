"""Worker: leases queued jobs from the store/outbox, runs fixture parses.

PostgreSQL fenced-lease semantics are specified in database/lease_queries.sql;
this local worker implements the same state machine (queued->running->
succeeded/failed, cancel_requested->cancelled) without claiming PG guarantees.
"""
import time
from src.services.store import store
from src.services import evf as evf_service

def process_one(worker_id="worker-1"):
    with store.lock:
        for j in store.jobs.values():
            if j["state"] == "cancel_requested": j["state"] = "cancelled"
        job = next((j for j in sorted(store.jobs.values(), key=lambda j: j["created_at"])
                    if j["state"] == "queued"), None)
        if not job: return None
        job["state"] = "running"; job["attempt"] += 1; job["worker_id"] = worker_id
        parse = store.parses.get(job.get("result_id") or job["payload"].get("parse_id", ""))
    if job["state"] == "cancel_requested":
        job["state"] = "cancelled"; return job
    result, err = (None, "unknown_job_kind")
    if job["kind"] == "evf_parse":
        if not parse: result, err = None, "parse_not_found"
        elif parse.get("profile") == "docling_local/1": result, err = evf_service.run_docling_parse(parse)
        else: result, err = evf_service.run_fixture_parse(parse)
    with store.lock:
        if job["state"] == "cancel_requested":
            job["state"] = "cancelled"
        elif err:
            job["state"] = "failed"; job["error_code"] = err
            if parse: parse["state"] = "failed"
        else:
            job["state"] = "succeeded"
    return job

def run_loop(poll=0.25, max_jobs=None):
    done = 0
    while max_jobs is None or done < max_jobs:
        if process_one() is None: time.sleep(poll)
        else: done += 1

if __name__ == "__main__":
    run_loop()
