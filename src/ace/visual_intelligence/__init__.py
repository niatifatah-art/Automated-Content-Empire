"""ACE visual-intelligence subsystem.

The package intentionally keeps planning, candidate creation, scoring, judging,
and final decisions separate so each part can be tested or replaced without
rewriting the renderer.
"""

from ace.visual_intelligence.contracts import (
    CandidateOrigin,
    DecisionStatus,
    ShotIntent,
    VisualCandidate,
    VisualDecision,
    VisualFormat,
    VisualPurpose,
    VisualScore,
    VisualValidationReport,
)

__all__ = [
    "CandidateOrigin",
    "DecisionStatus",
    "ShotIntent",
    "VisualCandidate",
    "VisualDecision",
    "VisualFormat",
    "VisualPurpose",
    "VisualScore",
    "VisualValidationReport",
]
