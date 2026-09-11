import importlib
import sys
from unittest.mock import MagicMock

import app


def test_app_init_windows_success(monkeypatch):
    """Test that event loop policy is set when running on Windows."""
    mock_set_policy = MagicMock()
    monkeypatch.setattr("asyncio.set_event_loop_policy", mock_set_policy)

    mock_selector = MagicMock()
    monkeypatch.setattr("asyncio.WindowsSelectorEventLoopPolicy", mock_selector, raising=False)
    monkeypatch.setattr(sys, "platform", "win32")

    importlib.reload(app)

    mock_set_policy.assert_called_once_with(mock_selector.return_value)


def test_app_init_windows_exception_suppressed(monkeypatch):
    """Test that exceptions raised during event loop policy configuration are suppressed."""
    def fail_set_policy(*args, **kwargs):
        raise RuntimeError("Failed to set event loop policy")

    monkeypatch.setattr("asyncio.set_event_loop_policy", fail_set_policy)
    monkeypatch.setattr("asyncio.WindowsSelectorEventLoopPolicy", MagicMock(), raising=False)
    monkeypatch.setattr(sys, "platform", "win32")

    # Should not raise exception
    importlib.reload(app)


def test_app_init_non_windows(monkeypatch):
    """Test that event loop policy is not touched on non-Windows platforms."""
    mock_set_policy = MagicMock()

    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr("asyncio.set_event_loop_policy", mock_set_policy)

    importlib.reload(app)

    mock_set_policy.assert_not_called()
