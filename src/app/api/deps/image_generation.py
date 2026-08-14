"""Image generation at the route boundary — the same shape
``api/deps/vision_analysis.py`` uses for the same reason: no honest default
adapter exists (see the port's module docstring), so ``bootstrap/app.py``
never sets ``app.state.image_generation``, and ``getattr`` with a ``None``
default turns an unset provider into a documented 503 rather than a bare
``AttributeError`` surfacing as an unexplained 500.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from app.services.ports.image_generation import ImageGeneration
from app.shared.errors import UnavailableError


def get_image_generation(request: Request) -> ImageGeneration:
    generation: ImageGeneration | None = getattr(request.app.state, "image_generation", None)
    if generation is None:
        raise UnavailableError(
            "Image generation is not configured on this deployment.",
            code="image_generation_unavailable",
        )
    return generation


ImageGenerationDep = Annotated[ImageGeneration, Depends(get_image_generation)]
