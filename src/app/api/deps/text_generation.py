"""Text generation at the route boundary — the same shape
``api/deps/image_generation.py``/``api/deps/vision_analysis.py`` use for
the same reason: no honest default adapter exists (see the port's module
docstring), so ``bootstrap/app.py`` never sets ``app.state.text_generation``,
and ``getattr`` with a ``None`` default turns an unset provider into a
documented 503 rather than a bare ``AttributeError`` surfacing as an
unexplained 500.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from app.services.ports.text_generation import TextGeneration
from app.shared.errors import UnavailableError


def get_text_generation(request: Request) -> TextGeneration:
    generation: TextGeneration | None = getattr(request.app.state, "text_generation", None)
    if generation is None:
        raise UnavailableError(
            "Text generation is not configured on this deployment.",
            code="text_generation_unavailable",
        )
    return generation


TextGenerationDep = Annotated[TextGeneration, Depends(get_text_generation)]
