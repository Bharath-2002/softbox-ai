"""Health, readiness, request ids, and the problem+json error contract."""

from __future__ import annotations

import pytest
from fastapi import APIRouter
from httpx import ASGITransport, AsyncClient

from app.api.errors import PROBLEM_CONTENT_TYPE
from app.api.health import register_readiness_check
from app.bootstrap.app import create_app
from app.bootstrap.settings import Settings
from app.shared.errors import ConflictError, NotFoundError, QuotaExceededError

TEST_SETTINGS = Settings(environment="test", log_format="console")


def build_app(with_failing_check: bool = False):
    app = create_app(TEST_SETTINGS)

    async def ok() -> None:
        return None

    async def broken() -> None:
        raise RuntimeError("postgres unreachable at postgres://user:pa55w0rd@host/db")

    register_readiness_check(app, "database", broken if with_failing_check else ok)

    probe = APIRouter()

    @probe.get("/boom/{kind}")
    async def boom(kind: str) -> None:
        raise {
            "not_found": NotFoundError("No such product."),
            "conflict": ConflictError("Already exists.", details={"field": "sku"}),
            "quota": QuotaExceededError("Monthly image budget exhausted."),
            "unexpected": ValueError("something internal"),
        }[kind]

    app.include_router(probe)
    return app


async def client(app) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_health_is_ok_and_does_not_touch_dependencies() -> None:
    async with await client(build_app(with_failing_check=True)) as http:
        response = await http.get("/health")

    # Liveness must stay green even though the readiness check is failing.
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_ready_reports_ok_when_dependencies_are_healthy() -> None:
    async with await client(build_app()) as http:
        response = await http.get("/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "checks": {"database": "ok"}}


async def test_ready_degrades_without_leaking_the_failure_detail() -> None:
    async with await client(build_app(with_failing_check=True)) as http:
        response = await http.get("/ready")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "degraded"
    assert body["checks"]["database"] == "error: RuntimeError"
    # The exception message carried a password; it must not reach the response.
    assert "pa55w0rd" not in response.text


async def test_request_id_is_echoed_and_generated() -> None:
    async with await client(build_app()) as http:
        generated = await http.get("/health")
        supplied = await http.get("/health", headers={"X-Request-ID": "abc123"})

    assert generated.headers["X-Request-ID"]
    assert supplied.headers["X-Request-ID"] == "abc123"


async def test_hostile_inbound_request_id_is_replaced() -> None:
    """The id lands in logs, so it is not trusted as given."""
    async with await client(build_app()) as http:
        response = await http.get("/health", headers={"X-Request-ID": "a b\nc<script>"})

    assert response.headers["X-Request-ID"] != "a b\nc<script>"


@pytest.mark.parametrize(
    ("kind", "expected_status", "expected_code"),
    [
        ("not_found", 404, "not_found"),
        ("conflict", 409, "conflict"),
        ("quota", 402, "quota_exceeded"),
    ],
)
async def test_domain_errors_map_to_problem_json(
    kind: str, expected_status: int, expected_code: str
) -> None:
    async with await client(build_app()) as http:
        response = await http.get(f"/boom/{kind}")

    assert response.status_code == expected_status
    assert response.headers["content-type"].startswith(PROBLEM_CONTENT_TYPE)
    body = response.json()
    assert body["code"] == expected_code
    assert body["status"] == expected_status
    assert body["instance"] == f"/boom/{kind}"
    assert body["request_id"]


async def test_conflict_carries_its_details() -> None:
    async with await client(build_app()) as http:
        response = await http.get("/boom/conflict")

    assert response.json()["details"] == {"field": "sku"}


async def test_unexpected_errors_reveal_nothing_internal() -> None:
    transport = ASGITransport(app=build_app(), raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as http:
        response = await http.get("/boom/unexpected")

    assert response.status_code == 500
    body = response.json()
    assert body["code"] == "internal_error"
    assert body["detail"] == "An unexpected error occurred."
    assert "something internal" not in response.text
    assert "ValueError" not in response.text
