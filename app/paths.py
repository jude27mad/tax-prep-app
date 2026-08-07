"""Path-containment guard for building filesystem paths from untrusted input.

Any path built from external input (profile slugs, user ids, uploaded
filenames, API-supplied output paths, ...) should be validated with
:func:`resolve_within` before touching the filesystem: pass the trusted root
directory plus the untrusted segment(s), and it returns a path guaranteed to
live under that root, raising :class:`PathTraversalError` otherwise. This
follows the normalize-then-check-prefix pattern (CWE-22): join, normalize
with ``os.path.normpath`` to collapse ``..``/symlink-free traversal
sequences, then require the result to start with the resolved root.
"""

from __future__ import annotations

import os.path
from pathlib import Path


class PathTraversalError(ValueError):
    """Raised when a candidate path would escape its intended root."""


def resolve_within(root: Path, *parts: str) -> Path:
    root_str = os.path.normpath(str(root.resolve()))
    candidate = os.path.normpath(os.path.join(root_str, *parts))
    if candidate != root_str and not candidate.startswith(root_str + os.sep):
        raise PathTraversalError(f"path {candidate!r} escapes root {root_str!r}")
    return Path(candidate)
