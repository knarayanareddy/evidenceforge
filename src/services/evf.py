"""EvidenceForge domain service: fixture parsing, 8-field extraction, review, export.

Fixture profile `fixture/1` accepts ONLY the bundled synthetic PDF digest.
Values are Decimal-based (never binary float for finance); base-unit values are
raw * scale. Missing values carry explicit missing_reason, never invented zeros.
"""
import csv, hashlib, io, json, re
from decimal import Decimal, InvalidOperation
from src.services.store import store, new_id, now_iso

BUNDLED_SHA256 = "ec14a14dcd0afc635c34446c6b4e4374dcb8f24866872c4523baf078e6c40a4a"
FIXTURE_TEXT = ("Synthetic annual report FY 2025 | Entity: Example Labs | "
                "Revenue: 1,234 | Assets: 5,678 | Currency EUR; units 1000")
FIELD_KEYS = ["entity", "period_end", "currency", "scale",
              "revenue_current", "revenue_prior", "assets_current", "assets_prior"]
SCALE_BY_UNITS = {"1": "1", "1000": "1000", "1000000": "1000000"}

def fixture_elements(document_id, parse_id):
    """Authored synthetic fixture elements (NOT Docling output)."""
    return {"e1": {"page_ordinal": 1,
                   "region": {"page_ordinal": 1, "x0": 0.1, "y0": 0.1, "x1": 0.9, "y1": 0.2},
                   "text": FIXTURE_TEXT}}

def run_fixture_parse(parse):
    """Worker entry: parse only the bundled digest, else fail the job honestly."""
    doc = store.documents.get(parse["document_id"])
    if not doc or doc["state"] == "deleting":
        return None, "source_unavailable"
    if parse["source_sha256"] != BUNDLED_SHA256 or doc["source_sha256"] != BUNDLED_SHA256:
        return None, "fixture_digest_mismatch"
    parse["elements"] = fixture_elements(doc["id"], parse["id"])
    parse["state"] = "parsed"; parse["page_count"] = 1
    doc["state"] = "parsed"; doc["page_count"] = 1
    return parse, None

def run_docling_parse(parse):
    """B09 pilot: real local parsing via docling-parse (no ML models, no egress)."""
    from src.services.docling_local import parse_pdf_bytes, DoclingUnavailable
    doc = store.documents.get(parse["document_id"])
    if not doc or doc["state"] == "deleting":
        return None, "source_unavailable"
    art = store.artifacts.get(doc["source_artifact_id"])
    data = store.artifact_bytes.get(art["id"]) if art else None
    if data is None:
        return None, "source_unavailable"
    try:
        elements, page_count = parse_pdf_bytes(data)
    except DoclingUnavailable:
        return None, "docling_unavailable"
    except ValueError as e:
        return None, str(e)
    parse["elements"] = elements; parse["state"] = "parsed"; parse["page_count"] = page_count
    doc["state"] = "parsed"; doc["page_count"] = page_count
    return parse, None


def _evidence(doc, parse, quote):
    eid = next((k for k, el in parse["elements"].items() if quote in el["text"]), None)
    if eid is None:
        return {"document_id": doc["id"], "source_sha256": doc["source_sha256"],
                "parse_id": parse["id"], "element_id": "unknown", "region": {"page_ordinal": 1, "x0": 0, "y0": 0, "x1": 0, "y1": 0},
                "quote": quote, "method": "digital_text", "support": "unsupported"}
    el = parse["elements"][eid]
    return {"document_id": doc["id"], "source_sha256": doc["source_sha256"],
            "parse_id": parse["id"], "element_id": eid, "region": el["region"],
            "quote": quote, "method": "digital_text",
            "support": verify_quote(doc, parse, eid, quote)}

def verify_quote(doc, parse, element_id, quote):
    el = (parse.get("elements") or {}).get(element_id)
    if not el or doc["state"] == "deleting":
        return "source_unavailable"
    return "supported_exact" if quote in el["text"] else "unsupported"

def parse_amount(raw: str) -> Decimal:
    """Parse locale-grouped integer/decimal text without float ('-' is never zero)."""
    t = raw.strip()
    if t in {"-", "–", "—", ""}:
        raise ValueError("dash_or_empty_not_a_number")
    t = t.replace(" ", "")
    if re.fullmatch(r"\d{1,3}(\.\d{3})+(,\d+)?", t):  # 1.234,56 de grouping
        t = t.replace(".", "").replace(",", ".")
    elif "," in t and "." in t:  # 1,234.56 en grouping
        t = t.replace(",", "")
    elif "," in t:
        parts = t.split(",")
        t = "".join(parts) if all(len(p) == 3 for p in parts[1:]) else t.replace(",", ".")
    try:
        return Decimal(t)
    except InvalidOperation:
        raise ValueError("not_a_number")

def build_fields(doc, parse):
    """Produce exactly the eight contract fields, once each."""
    text = " ".join(el["text"] for el in parse["elements"].values())
    scale = "1000" if "units 1000" in text else "1"
    currency = "EUR" if "Currency EUR" in text else None
    period = None  # fixture states FY only; no invented calendar date
    def money(key, label):
        m = re.search(rf"{label}: ([\d.,]+)", text)
        if not m:
            return _field(key, None, None, currency, scale, period, "not_present", [])
        raw = m.group(1)
        try:
            base = parse_amount(raw) * Decimal(scale)
        except (ValueError, InvalidOperation):
            return _field(key, raw, None, currency, scale, period, "unreadable", [])
        val = format(base, "f")
        if val.endswith(".0"): val = val[:-2]
        return _field(key, raw, val, currency, scale, period, None,
                      [_evidence(doc, parse, f"{label}: {raw}")])
    entity = re.search(r"Entity: ([^|]+)", text)
    fields = [
        _field("entity", entity.group(1).strip() if entity else None,
               entity.group(1).strip() if entity else None, currency, scale, period,
               None if entity else "not_present",
               [_evidence(doc, parse, f"Entity: {entity.group(1).strip()}")] if entity else []),
        _field("period_end", None, None, currency, scale, period, "not_present", []),
        _field("currency", currency, currency, currency, scale, period,
               None if currency else "not_present",
               [_evidence(doc, parse, "Currency EUR")] if currency else []),
        _field("scale", scale, scale, currency, scale, period, None,
               [_evidence(doc, parse, "units 1000")] if scale != "1" else []),
        money("revenue_current", "Revenue"),
        _field("revenue_prior", None, None, currency, scale, period, "not_present", []),
        money("assets_current", "Assets"),
        _field("assets_prior", None, None, currency, scale, period, "not_present", []),
    ]
    if [f["key"] for f in fields] != FIELD_KEYS: raise RuntimeError("field_key_contract_violation")
    return fields

def _field(key, raw, value, currency, scale, period_end, missing, evidence):
    return {"key": key, "raw": raw, "value": value, "currency": currency,
            "scale": scale, "period_end": period_end, "missing_reason": missing,
            "evidence": evidence, "review_state": "unreviewed", "risk_flags": []}

def effective_fields(extraction):
    """Reconstruct current field state by applying append-only reviews in order."""
    fields = {f["key"]: json.loads(json.dumps(f)) for f in extraction["fields"]}
    for rev in sorted((r for r in store.reviews.values()
                       if r["extraction_id"] == extraction["id"]), key=lambda r: r["revision"]):
        for p in rev["patches"]:
            f = fields.get(p["key"])
            if f is None: continue
            if p["action"] == "accept": f["review_state"] = "accepted"
            elif p["action"] == "reject":
                f["review_state"] = "rejected"; f["value"] = None; f["missing_reason"] = "unsupported"
            elif p["action"] == "correct":
                f["review_state"] = "corrected"
                if p.get("value") is not None: f["value"] = p["value"]; f["missing_reason"] = None
                if p.get("currency") is not None: f["currency"] = p["currency"]
                if p.get("scale") is not None: f["scale"] = p["scale"]
                if p.get("period_end") is not None: f["period_end"] = p["period_end"]
                if p.get("evidence") is not None: f["evidence"] = p["evidence"]
    return [fields[k] for k in FIELD_KEYS]

def csv_safe(cell: str) -> str:
    """Spreadsheet-injection mitigation incl. leading whitespace (preserve it)."""
    if cell and cell.lstrip(" \t\r\n")[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + cell
    if cell[:1] in ("=", "+", "-", "@"):
        return "'" + cell
    return cell

def render_export(fields, fmt):
    warnings = [f"field_missing:{f['key']}:{f['missing_reason']}" for f in fields if f["value"] is None]
    incomplete = bool(warnings)
    if fmt == "csv":
        buf = io.StringIO(); w = csv.writer(buf)
        w.writerow(["key", "value", "raw", "currency", "scale", "period_end", "missing_reason", "review_state"])
        for f in fields:
            w.writerow([csv_safe(str(f[k] or "")) for k in
                        ("key", "value", "raw", "currency", "scale", "period_end", "missing_reason", "review_state")])
        payload = buf.getvalue().encode()
    else:
        payload = json.dumps({"fields": fields, "incomplete": incomplete, "warnings": warnings,
                              "provenance_note": "Evidence provenance/support is not proof of financial correctness."},
                             indent=2).encode()
    return payload, incomplete, warnings, hashlib.sha256(payload).hexdigest()
