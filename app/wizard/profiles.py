"""Profile filesystem store (TOML drafts + trash + history + active pointer).

User scoping (D1.6): every public function accepts an optional ``user_id``.
When provided, the profile lives under ``profiles/<user_id>/<slug>.toml``
and the active-profile pointer + trash + history are all scoped under the
same ``profiles/<user_id>/`` directory. When ``user_id`` is ``None`` the
functions behave like the pre-D1.6 global namespace (``profiles/<slug>.toml``),
which is the mode used by the CLI and by pre-auth tests.

Router handlers gated by ``require_user_web`` always pass ``user_id=user.id``,
so an authenticated request cannot see another user's drafts even if they
guess the slug.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:  # pragma: no cover - fallback for older interpreters
    import tomli as tomllib  # type: ignore[import-not-found,no-redef]

from .estimator import round_cents
from .fields import (
    CLI_BOOL_FIELDS,
    CLI_INT_FIELDS,
    CLI_NUMERIC_FIELDS,
    CLI_SAVE_ORDER,
    CLI_SUBMIT_FIELDS,
    canonicalize_data,
)

BASE_DIR = Path(__file__).resolve().parent.parent
INBOX_DIR = BASE_DIR / "inbox"
PROFILES_DIR = BASE_DIR / "profiles"
PROFILE_HISTORY_DIR = PROFILES_DIR / "history"
PROFILE_TRASH_DIR = PROFILES_DIR / ".trash"
DEFAULT_PROFILE_FILE = PROFILES_DIR / "active_profile.txt"


def slugify(value: str) -> str:
    import re

    cleaned = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return cleaned or "profile"


def _user_root(user_id: str | None) -> Path:
    # Per-user scoping carves out ``profiles/<user_id>/`` so two authenticated
    # users cannot see each other's drafts even if they guess a slug. The
    # ``None`` branch keeps the pre-D1.6 global layout for CLI + legacy tests.
    if user_id:
        return PROFILES_DIR / "users" / user_id
    return PROFILES_DIR


def _ensure_profiles_dirs(user_id: str | None = None) -> None:
    root = _user_root(user_id)
    for directory in (root, root / "history", root / ".trash"):
        directory.mkdir(parents=True, exist_ok=True)


def _profile_path(slug: str, user_id: str | None = None) -> Path:
    return _user_root(user_id) / f"{slug}.toml"


def _history_dir(slug: str, user_id: str | None = None) -> Path:
    return _user_root(user_id) / "history" / slug


def _trash_dir(user_id: str | None = None) -> Path:
    return _user_root(user_id) / ".trash"


def _active_pointer(user_id: str | None = None) -> Path:
    return _user_root(user_id) / "active_profile.txt"


def load_profile(
    slug: str | None,
    *,
    user_id: str | None = None,
) -> tuple[dict[str, Any], Path | None, list[str]]:
    if not slug:
        return {}, None, []
    _ensure_profiles_dirs(user_id)
    path = _profile_path(slug, user_id)
    if not path.exists():
        return {}, None, []
    errors: list[str] = []
    try:
        with path.open("rb") as handle:
            raw = tomllib.load(handle)
    except Exception as exc:  # pragma: no cover - corrupt file
        errors.append(f"{path.name}: {exc}")
        return {}, path, errors
    try:
        data = canonicalize_data(raw)
    except ValueError as exc:
        errors.append(f"{path.name}: {exc}")
        data = {}
    return data, path, errors


def _snapshot_profile(slug: str, path: Path, user_id: str | None = None) -> None:
    if not path.exists():
        return
    timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    history_dir = _history_dir(slug, user_id)
    history_dir.mkdir(parents=True, exist_ok=True)
    snapshot = history_dir / f"{timestamp}.toml"
    snapshot.write_bytes(path.read_bytes())


def _trash_profile(slug: str, path: Path, user_id: str | None = None) -> Path | None:
    if not path.exists():
        return None
    _ensure_profiles_dirs(user_id)
    trash = _trash_dir(user_id)
    trash.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    dest = trash / f"{slug}-{timestamp}.toml"
    path.replace(dest)
    return dest


def list_profiles(*, user_id: str | None = None) -> list[str]:
    root = _user_root(user_id)
    if not root.exists():
        return []
    # Only direct *.toml children, not the active_profile.txt pointer or
    # anything nested under history/.trash.
    return sorted(p.stem for p in root.glob("*.toml") if p.is_file())


def list_trash(
    slug: str | None = None,
    *,
    user_id: str | None = None,
) -> list[Path]:
    trash = _trash_dir(user_id)
    if not trash.exists():
        return []
    files = [p for p in trash.glob("*.toml") if p.is_file()]
    if slug:
        prefix = f"{slug}-"
        files = [p for p in files if p.name.startswith(prefix)]
    return sorted(files)


def set_active_profile(slug: str | None, *, user_id: str | None = None) -> None:
    _ensure_profiles_dirs(user_id)
    pointer = _active_pointer(user_id)
    if slug is None:
        if pointer.exists():
            pointer.unlink()
        return
    pointer.write_text(slug + "\n", encoding="utf-8")


def get_active_profile(*, user_id: str | None = None) -> str | None:
    pointer = _active_pointer(user_id)
    if pointer.exists():
        content = pointer.read_text(encoding="utf-8").strip()
        return content or None
    return None


def save_user_data(data: dict[str, Any], path: Path) -> None:
    lines: list[str] = []
    for key in CLI_SAVE_ORDER:
        value = data.get(key)
        if value is None:
            continue
        if key in CLI_NUMERIC_FIELDS:
            lines.append(f"{key} = {round_cents(float(value)):.2f}")
        elif key in CLI_BOOL_FIELDS:
            lines.append(f"{key} = {'true' if bool(value) else 'false'}")
        elif key in CLI_INT_FIELDS:
            lines.append(f"{key} = {int(value)}")
        else:
            escaped = str(value).replace("\"", "\\\"")
            lines.append(f"{key} = \"{escaped}\"")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def save_profile_data(
    slug: str,
    data: dict[str, Any],
    *,
    user_id: str | None = None,
) -> Path:
    _ensure_profiles_dirs(user_id)
    path = _profile_path(slug, user_id)
    if path.exists():
        _snapshot_profile(slug, path, user_id)
    save_user_data(data, path)
    set_active_profile(slug, user_id=user_id)
    return path


def delete_profile(slug: str, *, user_id: str | None = None) -> Path | None:
    path = _profile_path(slug, user_id)
    if not path.exists():
        return None
    trashed = _trash_profile(slug, path, user_id)
    if get_active_profile(user_id=user_id) == slug:
        set_active_profile(None, user_id=user_id)
    return trashed


def restore_profile(slug: str, *, user_id: str | None = None) -> Path | None:
    candidates = list_trash(slug, user_id=user_id)
    if not candidates:
        return None
    candidate = candidates[-1]
    dest = _profile_path(slug, user_id)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(candidate.read_bytes())
    candidate.unlink()
    return dest


def rename_profile(
    slug: str,
    new_slug: str,
    *,
    user_id: str | None = None,
) -> tuple[Path | None, Path | None]:
    if slug == new_slug:
        return _profile_path(slug, user_id), None
    old_path = _profile_path(slug, user_id)
    if not old_path.exists():
        return None, None
    new_path = _profile_path(new_slug, user_id)
    if new_path.exists():
        raise ValueError(f"Profile '{new_slug}' already exists.")
    new_path.parent.mkdir(parents=True, exist_ok=True)
    new_path.write_bytes(old_path.read_bytes())
    old_path.unlink()
    old_history = _history_dir(slug, user_id)
    new_history = _history_dir(new_slug, user_id)
    if old_history.exists():
        new_history.parent.mkdir(parents=True, exist_ok=True)
        if new_history.exists():
            for item in old_history.glob("*"):
                target = new_history / item.name
                target.write_bytes(item.read_bytes())
                item.unlink()
            old_history.rmdir()
        else:
            old_history.rename(new_history)
    if get_active_profile(user_id=user_id) == slug:
        set_active_profile(new_slug, user_id=user_id)
    return new_path, new_history


__all__ = [
    "BASE_DIR",
    "DEFAULT_PROFILE_FILE",
    "INBOX_DIR",
    "PROFILE_HISTORY_DIR",
    "PROFILE_TRASH_DIR",
    "PROFILES_DIR",
    "CLI_BOOL_FIELDS",
    "CLI_INT_FIELDS",
    "CLI_NUMERIC_FIELDS",
    "CLI_SAVE_ORDER",
    "CLI_SUBMIT_FIELDS",
    "delete_profile",
    "get_active_profile",
    "list_profiles",
    "list_trash",
    "load_profile",
    "rename_profile",
    "restore_profile",
    "save_profile_data",
    "save_user_data",
    "set_active_profile",
    "slugify",
]
