from __future__ import annotations

import pytest

from app.entities.tenant_domain import TenantDomain
from app.shared.clock import utcnow
from app.shared.errors import ValidationError
from app.shared.ids import new_tenant_id


def test_create_normalises_hostname_to_lowercase() -> None:
    domain = TenantDomain.create(new_tenant_id(), "Shop.Example.COM", now=utcnow())

    assert domain.hostname == "shop.example.com"


def test_create_strips_surrounding_whitespace() -> None:
    domain = TenantDomain.create(new_tenant_id(), "  shop.example.com  ", now=utcnow())

    assert domain.hostname == "shop.example.com"


def test_create_starts_unverified() -> None:
    domain = TenantDomain.create(new_tenant_id(), "shop.example.com", now=utcnow())

    assert domain.verified is False


@pytest.mark.parametrize("hostname", ["", "   "])
def test_create_rejects_an_empty_hostname(hostname: str) -> None:
    with pytest.raises(ValidationError):
        TenantDomain.create(new_tenant_id(), hostname, now=utcnow())
