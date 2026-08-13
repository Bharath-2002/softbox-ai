"""OpenAPI generation, verified (CLAUDE.md checklist, M1 chunk 5).

The schema-hiding branch in ``bootstrap/app.py`` (``docs_url``/``openapi_url``
``None`` in production) existed since M1 chunk 1 but had no test until now -
"verified" means both that the schema actually generates without error, and
that production genuinely hides it rather than just being intended to.
"""

from __future__ import annotations

from httpx import ASGITransport, AsyncClient

from app.bootstrap.app import create_app
from app.bootstrap.settings import Settings


def _client(settings: Settings) -> AsyncClient:
    app = create_app(settings)
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_the_openapi_schema_generates_without_error() -> None:
    app = create_app(Settings(environment="test", log_format="console"))

    schema = app.openapi()

    assert schema["info"]["title"] == "Softbox AI"
    assert "paths" in schema


async def test_the_openapi_schema_is_reachable_outside_production() -> None:
    async with _client(Settings(environment="test", log_format="console")) as http:
        response = await http.get("/openapi.json")
    assert response.status_code == 200


async def test_interactive_docs_are_reachable_outside_production() -> None:
    async with _client(Settings(environment="test", log_format="console")) as http:
        response = await http.get("/docs")
    assert response.status_code == 200


async def test_the_openapi_schema_is_hidden_in_production() -> None:
    async with _client(Settings(environment="production", log_format="json")) as http:
        response = await http.get("/openapi.json")
    assert response.status_code == 404


async def test_interactive_docs_are_hidden_in_production() -> None:
    async with _client(Settings(environment="production", log_format="json")) as http:
        response = await http.get("/docs")
    assert response.status_code == 404
