"""Vision analysis at the route boundary.

Unlike every other ``api/deps/*`` provider, ``bootstrap/app.py`` never sets
``app.state.vision_analysis`` — there is no honest default adapter (see the
port's module docstring). ``getattr`` with a ``None`` default is
deliberate: ``request.app.state.vision_analysis`` would raise a bare
``AttributeError`` when unset, which is not one of ``api/errors.py``'s
mapped domain errors and would surface as an unexplained 500. Raising
``UnavailableError`` here (mapped to 503) makes "no provider is configured"
an honest, documented response instead.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from app.services.ports.vision_analysis import VisionAnalysis
from app.shared.errors import UnavailableError


def get_vision_analysis(request: Request) -> VisionAnalysis:
    analysis: VisionAnalysis | None = getattr(request.app.state, "vision_analysis", None)
    if analysis is None:
        raise UnavailableError(
            "Template analysis is not configured on this deployment.",
            code="vision_analysis_unavailable",
        )
    return analysis


VisionAnalysisDep = Annotated[VisionAnalysis, Depends(get_vision_analysis)]
