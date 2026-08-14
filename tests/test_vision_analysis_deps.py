"""``get_vision_analysis`` (M3): unlike every other ``api/deps/*`` provider,
there is no default adapter wired into ``bootstrap/app.py`` (see the port's
module docstring for why), so this is the one dependency that must be
proven to fail *honestly* — a 503 with a clear reason — rather than an
unexplained 500 from a bare ``AttributeError`` on unset ``app.state``.
"""

from __future__ import annotations

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.deps.vision_analysis import VisionAnalysisDep
from app.bootstrap.app import create_app
from app.bootstrap.settings import Settings
from tests.fakes.vision_analysis import FakeVisionAnalysis


def _probe_app(app: FastAPI) -> FastAPI:
    @app.get("/probe")
    async def probe(vision_analysis: VisionAnalysisDep) -> dict[str, bool]:
        return {"configured": vision_analysis is not None}

    return app


async def test_the_real_app_maps_unconfigured_vision_analysis_to_503() -> None:
    settings = Settings(environment="test", log_format="console", access_token_signing_key="x" * 32)
    app = _probe_app(create_app(settings))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        response = await http.get("/probe")

    assert response.status_code == 503
    assert response.json()["code"] == "vision_analysis_unavailable"


async def test_a_configured_vision_analysis_is_returned() -> None:
    app = _probe_app(FastAPI())
    app.state.vision_analysis = FakeVisionAnalysis()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        response = await http.get("/probe")

    assert response.status_code == 200
    assert response.json() == {"configured": True}
