import importlib

import pytest

from app import lifespan


def test_build_application_lifespan_requires_python_multipart(monkeypatch):
    original_import_module = importlib.import_module

    def fake_import_module(name: str, package: str | None = None):
        if name == "multipart":
            raise ImportError("No module named 'multipart'")
        return original_import_module(name, package)

    monkeypatch.setattr(importlib, "import_module", fake_import_module)

    with pytest.raises(
        RuntimeError, match="Install python-multipart to enable form parsing"
    ):
        lifespan.build_application_lifespan("test-app")
