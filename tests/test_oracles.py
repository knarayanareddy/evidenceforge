"""Independent Acceptance Tests against Reference Oracles for EvidenceForge (EVF)."""
import json, copy, random, hashlib
from pathlib import Path
import pytest
from reference.oracles import (
    pdf_point, inverse_pdf_point, normalize_number, validate_evidence, csv_safe
)

ROOT = Path(__file__).resolve().parents[1]

@pytest.mark.parametrize('rotation', [0, 90, 180, 270])
def test_geometry_rotation_roundtrip(rotation):
    crop = (-10, 20, 190, 420)
    rng = random.Random(42)
    for _ in range(50):
        x = -10 + rng.random() * 200
        y = 20 + rng.random() * 400
        u, v = pdf_point(x, y, crop, rotation)
        xx, yy = inverse_pdf_point(u, v, crop, rotation)
        assert abs(xx - x) < 1e-10 and abs(yy - y) < 1e-10
    
    corners = {0: (0, 0), 90: (1, 0), 180: (1, 1), 270: (0, 1)}
    assert pdf_point(-10, 420, crop, rotation) == corners[rotation]
    with pytest.raises(ValueError):
        pdf_point(-11, 420, crop, rotation)

@pytest.mark.parametrize('raw,locale,scale,expected', [
    ('1,234', 'en', '1000', '1234000'),
    ('(1,234.50)', 'en', '1', '-1234.50'),
    ('1.234,50', 'de', '1', '1234.50'),
    ('0', 'en', '1', '0')
])
def test_number_normalization(raw, locale, scale, expected):
    assert normalize_number(raw, locale, scale)['value'] == expected

@pytest.mark.parametrize('raw', ['1,23', '12x', '1e5', 'NaN', '(−3)', '(+1)'])
def test_ambiguous_numbers_rejected(raw):
    with pytest.raises(ValueError):
        normalize_number(raw)

def test_dash_is_not_zero():
    assert normalize_number('—')['value'] is None

def test_source_evidence_verification():
    fixture_path = ROOT / "fixtures/document-evidence.json"
    pdf_path = ROOT / "fixtures/synthetic-report.pdf"
    assert fixture_path.exists() and pdf_path.exists()
    
    d = json.loads(fixture_path.read_text())
    assert validate_evidence(d['evidence'], d['source'], d['parse'])
    assert hashlib.sha256(pdf_path.read_bytes()).hexdigest() == d['source']['sha256']
    
    tampered = copy.deepcopy(d['evidence'])
    tampered['quote'] = 'unsupported hallucination'
    with pytest.raises(ValueError):
        validate_evidence(tampered, d['source'], d['parse'])

@pytest.mark.parametrize('value', ['=SUM(A1)', ' @cmd', '+1', '-3', '	=1', 'normal text'])
def test_csv_formula_mitigation(value):
    safe = csv_safe(value)
    if value.startswith(('=', '@', '+', '-', '	')):
        assert safe.startswith("'")
    else:
        assert safe == 'normal text'
