"""Quality control at the route boundary - the same shape
``api/deps/vision_analysis.py``/``api/deps/image_generation.py`` use for the
same reason: no honest default adapter exists (see the port's module
docstring), so ``bootstrap/app.py`` never sets ``app.state.quality_control``,
and ``getattr`` with a ``None`` default turns an unset provider into a
documented 503 rather than a bare ``AttributeError`` surfacing as an
unexplained 500.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from app.services.ports.quality_control import QualityControl
from app.shared.errors import UnavailableError


def get_quality_control(request: Request) -> QualityControl:
    control: QualityControl | None = getattr(request.app.state, "quality_control", None)
    if control is None:
        raise UnavailableError(
            "Quality control is not configured on this deployment.",
            code="quality_control_unavailable",
        )
    return control


QualityControlDep = Annotated[QualityControl, Depends(get_quality_control)]
