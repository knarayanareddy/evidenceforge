"""End-to-end fixture journey: upload->document->worker parse->extract->review->export->delete."""
import hashlib, uuid
import pytest
from httpx import AsyncClient, ASGITransport
from src.main import app
from src.services.store import store
from src.worker.main import process_one
from src.services.evf import parse_amount, csv_safe

PROJ = "00000000-0000-4000-8000-000000000001"
ADMIN = {"Authorization": "Bearer test-token-admin"}
ANALYST = {"Authorization": "Bearer test-token-analyst"}
MULTI = {"Authorization": "Bearer test-token-analyst-operator"}
VIEWER = {"Authorization": "Bearer test-token-viewer"}

def idem(): return {"Idempotency-Key": str(uuid.uuid4())}
def hdr(auth, proj=PROJ): return {**auth, "X-Project-Id": proj}

@pytest.fixture(autouse=True)
def clean():
    store.reset(); yield; store.reset()

def test_numeric_normalization_independent():
    assert str(parse_amount("1.234,56")) == "1234.56"
    assert str(parse_amount("1,234.56")) == "1234.56"
    assert str(parse_amount("1234")) == "1234"
    with pytest.raises(ValueError): parse_amount("-")

def test_csv_injection_leading_whitespace():
    assert csv_safe("  =2+5") == "'  =2+5"
    assert csv_safe("=SUM(A1)") == "'=SUM(A1)"
    assert csv_safe("plain") == "plain"

async def _journey(ac):
    pdf = open("fixtures/synthetic-report.pdf", "rb").read()
    sha = hashlib.sha256(pdf).hexdigest()
    r = await ac.post(f"/api/v1/projects/{PROJ}/uploads", headers={**ANALYST, **idem()},
                      json={"filename": "synthetic-report.pdf", "media_type": "application/pdf",
                            "byte_size": len(pdf), "sha256": sha, "classification": "synthetic"})
    assert r.status_code == 201, r.text
    up = r.json()
    r = await ac.put(up["put_path"], headers=hdr(ANALYST), content=pdf); assert r.status_code == 200
    r = await ac.post(f"/api/v1/uploads/{up['id']}:finalize", headers={**hdr(ANALYST), **idem()},
                      json={"sha256": sha, "byte_size": len(pdf)})
    assert r.status_code == 200, r.text
    art = r.json()
    r = await ac.post(f"/api/v1/projects/{PROJ}/evf/documents", headers={**ANALYST, **idem()},
                      json={"artifact_id": art["id"], "title": "Synthetic FY2025"})
    assert r.status_code == 201, r.text
    doc = r.json(); assert doc["source_sha256"] == sha
    r = await ac.post(f"/api/v1/evf/documents/{doc['id']}/parses", headers={**hdr(MULTI), **idem()},
                      json={"profile": "fixture/1", "source_sha256": sha})
    assert r.status_code == 202, r.text
    parse = r.json()
    job = process_one(); assert job["state"] == "succeeded"
    r = await ac.get(f"/api/v1/evf/parses/{parse['id']}", headers=hdr(ANALYST))
    assert r.json()["state"] == "parsed" and r.json()["synthetic_fixture"] is True
    r = await ac.post(f"/api/v1/projects/{PROJ}/evf/extractions", headers={**ANALYST, **idem()},
                      json={"schema_version": "annual-report-8/1", "method": "fixture", "parse_id": parse["id"]})
    assert r.status_code == 201, r.text
    ext = r.json()
    fields = {f["key"]: f for f in ext["fields"]}
    assert list(fields) == ["entity","period_end","currency","scale","revenue_current","revenue_prior","assets_current","assets_prior"]
    assert fields["revenue_current"]["value"] == "1234000"  # 1,234 x scale 1000, Decimal
    assert fields["assets_current"]["value"] == "5678000"
    assert fields["revenue_prior"]["missing_reason"] == "not_present"
    ev = fields["revenue_current"]["evidence"][0]
    assert ev["quote"] == "Revenue: 1,234" and ev["support"] == "supported_exact"
    return doc, parse, ext, ev

@pytest.mark.asyncio
async def test_full_journey_review_export_delete():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        doc, parse, ext, ev = await _journey(ac)
        # forged evidence rejected
        bad = dict(ev, quote="Revenue: 9,999")
        r = await ac.post(f"/api/v1/evf/extractions/{ext['id']}/reviews",
                          headers={**hdr(ANALYST), **idem(), "If-Match": '"1"'},
                          json={"base_revision": 1, "patches": [{"key": "revenue_prior", "action": "correct",
                                "value": "9999", "reason": "forged quote attempt", "evidence": [bad]}]})
        assert r.status_code == 422
        # stale conflict: second review on revision 1 after first succeeds -> 412
        body = {"base_revision": 1, "patches": [{"key": "period_end", "action": "correct",
                "value": None, "period_end": "2025-12-31", "reason": "fiscal year end confirmed", "evidence": []}]}
        r = await ac.post(f"/api/v1/evf/extractions/{ext['id']}/reviews",
                          headers={**hdr(ANALYST), **idem(), "If-Match": '"1"'}, json=body)
        assert r.status_code == 201 and r.json()["revision"] == 2
        r = await ac.post(f"/api/v1/evf/extractions/{ext['id']}/reviews",
                          headers={**hdr(ANALYST), **idem(), "If-Match": '"1"'}, json=body)
        assert r.status_code == 412
        # missing If-Match -> 428
        r = await ac.post(f"/api/v1/evf/extractions/{ext['id']}/reviews",
                          headers={**hdr(ANALYST), **idem()}, json=body)
        assert r.status_code == 428
        # exports
        for fmt in ("json", "csv"):
            r = await ac.post(f"/api/v1/evf/extractions/{ext['id']}/exports",
                              headers={**hdr(ANALYST), **idem()},
                              json={"review_revision": 2, "format": fmt, "allow_incomplete": True})
            assert r.status_code == 201, r.text
            assert r.json()["incomplete"] is True
        r = await ac.post(f"/api/v1/evf/extractions/{ext['id']}/exports",
                          headers={**hdr(ANALYST), **idem()},
                          json={"review_revision": 2, "format": "json", "allow_incomplete": False})
        assert r.status_code == 422
        # wrong-project hint -> 404
        r = await ac.get(f"/api/v1/evf/documents/{doc['id']}",
                         headers=hdr(ANALYST, "00000000-0000-4000-8000-000000000999"))
        assert r.status_code in (403, 404)
        # viewer cannot create document
        r = await ac.post(f"/api/v1/projects/{PROJ}/evf/documents", headers={**VIEWER, **idem()},
                          json={"artifact_id": doc["source_artifact_id"], "title": "x"})
        assert r.status_code == 403
        # deletion revokes reads
        r = await ac.request("DELETE", f"/api/v1/evf/documents/{doc['id']}",
                             headers={**hdr(ADMIN), **idem()})
        assert r.status_code == 202, r.text
        r = await ac.get(f"/api/v1/evf/documents/{doc['id']}", headers=hdr(ANALYST))
        assert r.status_code == 404
        r = await ac.get(f"/api/v1/evf/extractions/{ext['id']}", headers=hdr(ANALYST))
        assert r.status_code == 404

@pytest.mark.asyncio
async def test_nonbundled_pdf_rejected_by_fixture_parser():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        pdf = b"%PDF-1.4 not the bundled fixture"
        sha = hashlib.sha256(pdf).hexdigest()
        r = await ac.post(f"/api/v1/projects/{PROJ}/uploads", headers={**ANALYST, **idem()},
                          json={"filename": "x.pdf", "media_type": "application/pdf",
                                "byte_size": len(pdf), "sha256": sha, "classification": "synthetic"})
        up = r.json()
        await ac.put(up["put_path"], headers=hdr(ANALYST), content=pdf)
        r = await ac.post(f"/api/v1/uploads/{up['id']}:finalize", headers={**hdr(ANALYST), **idem()},
                          json={"sha256": sha, "byte_size": len(pdf)})
        art = r.json()
        r = await ac.post(f"/api/v1/projects/{PROJ}/evf/documents", headers={**ANALYST, **idem()},
                          json={"artifact_id": art["id"], "title": "Other"})
        doc = r.json()
        r = await ac.post(f"/api/v1/evf/documents/{doc['id']}/parses", headers={**hdr(MULTI), **idem()},
                          json={"profile": "fixture/1", "source_sha256": sha})
        parse = r.json()
        job = process_one()
        assert job["state"] == "failed" and job["error_code"] == "fixture_digest_mismatch"

@pytest.mark.asyncio
async def test_project_creation_org_scoped_idempotency():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        key = str(uuid.uuid4())
        h = {**ADMIN, "Idempotency-Key": key}
        r1 = await ac.post("/api/v1/projects", headers=h, json={"name": "P1"})
        r2 = await ac.post("/api/v1/projects", headers=h, json={"name": "P1"})
        assert r1.status_code == r2.status_code == 201 and r1.json()["id"] == r2.json()["id"]
        r3 = await ac.post("/api/v1/projects", headers=h, json={"name": "Different"})
        assert r3.status_code == 409
        assert len(store.projects) == 1
