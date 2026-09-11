import os
from pathlib import Path
import pytest

from app.main import BASE_DIR, _friendly_path


def test_friendly_path_base_dir():
    """BASE_DIR itself should return '.' as a relative path string."""
    assert _friendly_path(BASE_DIR) == "."


def test_friendly_path_direct_child():
    """Direct child file inside BASE_DIR should return filename string."""
    child = BASE_DIR / "user_data.toml"
    assert _friendly_path(child) == "user_data.toml"


def test_friendly_path_nested_child():
    """Nested path inside BASE_DIR should return relative path string."""
    nested = BASE_DIR / "inbox" / "subfolder" / "data.csv"
    expected = os.path.join("inbox", "subfolder", "data.csv")
    assert _friendly_path(nested) == expected


def test_friendly_path_outside_base_dir_parent():
    """Parent directory of BASE_DIR raises ValueError on relative_to and returns str(path)."""
    parent = BASE_DIR.parent
    assert _friendly_path(parent) == str(parent)


def test_friendly_path_outside_base_dir_absolute():
    """Completely external absolute path returns str(path)."""
    external = Path("/tmp/external_file.txt")
    assert _friendly_path(external) == str(external)


def test_friendly_path_root():
    """Root directory returns str(root)."""
    root = Path("/")
    assert _friendly_path(root) == str(root)


def test_friendly_path_unanchored_relative():
    """Unanchored relative path (not under BASE_DIR) returns str(path)."""
    rel = Path("standalone_file.txt")
    assert _friendly_path(rel) == "standalone_file.txt"


def test_friendly_path_unresolved_dotdot():
    """Path containing '..' relative components inside BASE_DIR."""
    unresolved = BASE_DIR / "inbox" / ".." / "user_data.toml"
    expected = os.path.join("inbox", "..", "user_data.toml")
    assert _friendly_path(unresolved) == expected


def test_friendly_path_resolved_dotdot():
    """Resolved path with '..' evaluates to direct child of BASE_DIR."""
    resolved = (BASE_DIR / "inbox" / ".." / "user_data.toml").resolve()
    assert _friendly_path(resolved) == "user_data.toml"


@pytest.mark.parametrize(
    "path_suffix,expected_suffix",
    [
        ("a/b/c.json", os.path.join("a", "b", "c.json")),
        ("profiles/default.toml", os.path.join("profiles", "default.toml")),
        ("test.py", "test.py"),
    ],
)
def test_friendly_path_parametrized(path_suffix, expected_suffix):
    """Parametrized check for various subpaths within BASE_DIR."""
    path = BASE_DIR / path_suffix
    assert _friendly_path(path) == expected_suffix
