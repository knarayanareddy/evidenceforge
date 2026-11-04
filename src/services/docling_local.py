"""B09 pilot: real local PDF parsing with docling-parse (IBM Docling's parser).

No ML model assets, no network, no OCR claims: digital text layer only.
Regions are REAL geometry from the PDF (normalized 0..1, top-left origin),
unlike fixture/1 whose geometry is authored test metadata.
"""
import os, tempfile

class DoclingUnavailable(Exception):
    pass

def parse_pdf_bytes(data: bytes):
    """Return (elements, page_count). Raises ValueError on malformed/encrypted input."""
    if not data.startswith(b"%PDF"):
        raise ValueError("not_a_pdf")
    try:
        from docling_parse.pdf_parser import DoclingPdfParser
    except ImportError as e:
        raise DoclingUnavailable() from e
    fd, path = tempfile.mkstemp(suffix=".pdf")
    try:
        with os.fdopen(fd, "wb") as f: f.write(data)
        try:
            pdf = DoclingPdfParser().load(path)
        except Exception as e:
            raise ValueError("malformed_or_encrypted_pdf") from e
        elements, page_count = {}, 0
        while True:
            page_count += 1
            try: page = pdf.get_page(page_count)
            except Exception: page_count -= 1; break
            if page is None: page_count -= 1; break
            d = page.export_to_dict()
            dim = d["dimension"]["rect"]
            w = max(dim["r_x1"] - dim["r_x0"], 1.0); h = max(dim["r_y2"] - dim["r_y0"], 1.0)
            for i, cell in enumerate(d.get("textline_cells", [])):
                text = (cell.get("text") or "").strip()
                if not text: continue
                r = cell["rect"]
                region = {"page_ordinal": page_count,
                          "x0": round(r["r_x0"] / w, 4), "x1": round(r["r_x2"] / w, 4),
                          # PDF origin is bottom-left; normalize to top-left
                          "y0": round(1 - r["r_y2"] / h, 4), "y1": round(1 - r["r_y0"] / h, 4)}
                elements[f"d{page_count}_{i}"] = {"page_ordinal": page_count, "region": region, "text": text}
            if page_count >= 100: break
        if not elements: raise ValueError("no_digital_text_layer")
        return elements, page_count
    finally:
        os.unlink(path)
