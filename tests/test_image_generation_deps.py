"""``get_image_generation``: the same ``UnavailableError``-on-unset proof
``test_vision_analysis_deps.py`` runs for its own port — no default adapter
is wired into ``bootstrap/app.py`` (see the port's module docstring), so an
unconfigured deployment must fail with a clear 503, not a bare
``AttributeError``.
"""

from __future__ import annotations

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.deps.image_generation import ImageGenerationDep
from app.bootstrap.app import create_app
from app.bootstrap.settings import Settings
from tests.fakes.image_generation import FakeImageGeneration


def _probe_app(app: FastAPI) -> FastAPI:
    @app.get("/probe")
    async def probe(image_generation: ImageGenerationDep) -> dict[str, bool]:
        return {"configured": image_generation is not None}

    return app


async def test_the_real_app_maps_unconfigured_image_generation_to_503() -> None:
    settings = Settings(environment="test", log_format="console", access_token_signing_key="x" * 32)
    app = _probe_app(create_app(settings))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        response = await http.get("/probe")

    assert response.status_code == 503
    assert response.json()["code"] == "image_generation_unavailable"


async def test_a_configured_image_generation_is_returned() -> None:
    app = _probe_app(FastAPI())
    app.state.image_generation = FakeImageGeneration()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        response = await http.get("/probe")

    assert response.status_code == 200
    assert response.json() == {"configured": True}
