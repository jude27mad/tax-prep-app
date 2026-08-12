"""Plan V3 explanation layer.

Phase 2 ships the deterministic explanation *contracts* (see
:mod:`app.explain.models`). They describe what the deterministic tax engine
produced, the source/evidence behind it, and how the user can verify it —
without recomputing anything and without any AI-provider dependency.

Later phases add the engine that fills these contracts from a
:class:`~app.core.models.ReturnCalc` (Phase 3), the read-only API (Phase 4),
CLI explain mode (Phase 5), and the refund waterfall (Phase 7).
"""

from app.explain.models import (
    EvidenceKind,
    EvidenceRef,
    ExplanationItem,
    ReturnExplanation,
    VerificationStep,
)

__all__ = [
    "EvidenceKind",
    "EvidenceRef",
    "ExplanationItem",
    "ReturnExplanation",
    "VerificationStep",
]
