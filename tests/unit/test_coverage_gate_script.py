import sys
from pathlib import Path

from scripts import coverage_gate


def test_coverage_gate_pass(tmp_path, monkeypatch):
    xml = """<coverage line-rate=\"0.95\"></coverage>"""
    path = tmp_path / "coverage.xml"
    path.write_text(xml, encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["coverage_gate", str(path), "--minimum", "80"])
    coverage_gate.main()
