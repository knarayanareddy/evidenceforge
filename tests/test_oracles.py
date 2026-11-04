"""Independent Acceptance Tests against Reference Oracles for EVF."""
from reference.oracles import rotate_box, rotate_point, normalize_numeric, sanitize_formula
import pytest

def test_geometry_rotation_roundtrip():
    # Rotate 90, 180, 270, 360 and ensure it returns to original coordinates
    box = [10.0, 20.0, 50.0, 80.0]
    b90 = rotate_box(box, 90, 100.0, 100.0)
    b180 = rotate_box(b90, 90, 100.0, 100.0)
    b270 = rotate_box(b180, 90, 100.0, 100.0)
    b360 = rotate_box(b270, 90, 100.0, 100.0)
    assert b360 == pytest.approx(box)

def test_spreadsheet_formula_sanitization():
    assert sanitize_formula("=SUM(A1:A10)") == "'=SUM(A1:A10)"
    assert sanitize_formula("+12345") == "'+12345"
    assert sanitize_formula("Normal Text") == "Normal Text"
