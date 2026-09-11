import importlib
import logging

import pytest
from fastapi import FastAPI

from app import lifespan


@pytest.mark.asyncio
async def test_invoke_hook_none():
    app = FastAPI()
    # Should complete without error when hook is None
    await lifespan._invoke_hook(None, app)


@pytest.mark.asyncio
async def test_invoke_hook_sync_success():
    app = FastAPI()
    called = []

    def hook(a: FastAPI):
        called.append(a)

    await lifespan._invoke_hook(hook, app)
    assert called == [app]


@pytest.mark.asyncio
async def test_invoke_hook_async_success():
    app = FastAPI()
    called = []

    async def hook(a: FastAPI):
        called.append(a)

    await lifespan._invoke_hook(hook, app)
    assert called == [app]


@pytest.mark.asyncio
async def test_invoke_hook_sync_exception(caplog):
    app = FastAPI()

    def failing_hook(a: FastAPI):
        raise ValueError("Sync hook error")

    with caplog.at_level(logging.ERROR, logger="tax_app"):
        await lifespan._invoke_hook(failing_hook, app)

    assert "Application lifecycle hook failed" in caplog.text
    assert "ValueError: Sync hook error" in caplog.text


@pytest.mark.asyncio
async def test_invoke_hook_async_exception(caplog):
    app = FastAPI()

    async def failing_hook(a: FastAPI):
        raise RuntimeError("Async hook error")

    with caplog.at_level(logging.ERROR, logger="tax_app"):
        await lifespan._invoke_hook(failing_hook, app)

    assert "Application lifecycle hook failed" in caplog.text
    assert "RuntimeError: Async hook error" in caplog.text


@pytest.mark.asyncio
async def test_build_application_lifespan_hooks_with_exceptions(caplog):
    def failing_startup(app: FastAPI):
        raise RuntimeError("Startup hook failed")

    async def failing_shutdown(app: FastAPI):
        raise ValueError("Shutdown hook failed")

    lifespan_cm = lifespan.build_application_lifespan(
        "test-app",
        startup_hook=failing_startup,
        shutdown_hook=failing_shutdown,
    )

    app = FastAPI()
    with caplog.at_level(logging.ERROR, logger="tax_app"):
        async with lifespan_cm(app):
            pass

    assert "Startup hook failed" in caplog.text
    assert "Shutdown hook failed" in caplog.text


def test_build_application_lifespan_requires_python_multipart(monkeypatch):
    original_import_module = importlib.import_module

    def fake_import_module(name: str, package: str | None = None):
        if name == "python_multipart":
            raise ImportError("No module named 'python_multipart'")
        return original_import_module(name, package)

    monkeypatch.setattr(importlib, "import_module", fake_import_module)

    with pytest.raises(
        RuntimeError, match="python-multipart is required for form submissions"
    ):
        lifespan.build_application_lifespan("test-app")
