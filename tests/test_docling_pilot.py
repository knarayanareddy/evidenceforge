"""B09 pilot: real docling-parse parsing (skipped, not faked, if wheel absent)."""
import hashlib, uuid
import pytest
pytest.importorskip("docling_parse")
from httpx import AsyncClient, ASGITransport
from src.main import app
from src.services.store import store
from src.worker.main import process_one

PROJ = "00000000-0000-4000-8000-000000000001"
ANALYST = {"Authorization": "Bearer test-token-analyst"}
MULTI = {"Authorization": "Bearer test-token-analyst-operator"}
def idem(): return {"Idempotency-Key": str(uuid.uuid4())}
def hdr(a): return {**a, "X-Project-Id": PROJ}

@pytest.fixture(autouse=True)
def clean():
    store.reset(); yield; store.reset()

@pytest.mark.asyncio
async def test_docling_local_real_geometry_and_extraction():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        pdf = open("fixtures/synthetic-report.pdf", "rb").read()
        sha = hashlib.sha256(pdf).hexdigest()
        r = await ac.post(f"/api/v1/projects/{PROJ}/uploads", headers={**ANALYST, **idem()},
                          json={"filename": "s.pdf", "media_type": "application/pdf", "byte_size": len(pdf),
                                "sha256": sha, "classification": "synthetic"})
        up = r.json()
        await ac.put(up["put_path"], headers=hdr(ANALYST), content=pdf)
        art = (await ac.post(f"/api/v1/uploads/{up['id']}:finalize", headers={**hdr(ANALYST), **idem()},
                             json={"sha256": sha, "byte_size": len(pdf)})).json()
        doc = (await ac.post(f"/api/v1/projects/{PROJ}/evf/documents", headers={**ANALYST, **idem()},
                             json={"artifact_id": art["id"], "title": "Docling pilot"})).json()
        r = await ac.post(f"/api/v1/evf/documents/{doc['id']}/parses", headers={**hdr(MULTI), **idem()},
                          json={"profile": "docling_local/1", "source_sha256": sha})
        assert r.status_code == 202, r.text
        job = process_one(); assert job["state"] == "succeeded", job
        parse = (await ac.get(f"/api/v1/evf/parses/{r.json()['id']}", headers=hdr(ANALYST))).json()
        assert parse["synthetic_fixture"] is False
        els = parse["elements"]; assert els
        el = next(iter(els.values()))
        # real geometry: x near left margin 50/612, not the authored fixture box
        assert el["region"]["x0"] == pytest.approx(50 / 612, abs=0.01)
        ext = (await ac.post(f"/api/v1/projects/{PROJ}/evf/extractions", headers={**ANALYST, **idem()},
                             json={"schema_version": "annual-report-8/1", "method": "deterministic",
                                   "parse_id": parse["id"]})).json()
        fields = {f["key"]: f for f in ext["fields"]}
        # Real source text ends at "Currency EUR" — no units statement exists in
        # the PDF (the fixture JSON's authored text adds one). Honest base value:
        assert fields["revenue_current"]["value"] == "1234"
        assert fields["scale"]["value"] == "1"
        assert fields["revenue_current"]["evidence"][0]["support"] == "supported_exact"

@pytest.mark.asyncio
async def test_docling_rejects_malformed_pdf():
    from src.services.docling_local import parse_pdf_bytes
    with pytest.raises(ValueError):
        parse_pdf_bytes(b"%PDF-1.4 garbage not a real pdf at all")
    with pytest.raises(ValueError):
        parse_pdf_bytes(b"not a pdf")
