"""Tenant self-service storefront domain management (D4, M8) under
``/admin``.

Registration is the only write here — no update/delete route yet, since
nothing consumes a domain removal or edit until the storefront resolver
(``public.py``) actually depends on these rows existing. DNS ownership
verification (the diagram's ``verified`` column) needs a real TXT-record
lookup this environment has no way to perform yet; every row is created
``verified=False`` and stays that way until that capability exists — the
same credential-blocked posture D21's OAuth connect flow has.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.deps.authorization import PrincipalDep, require_capability
from app.bootstrap.di import ListTenantDomainsDep, RegisterTenantDomainDep
from app.entities.capabilities import Capability
from app.entities.tenant_domain import TenantDomain

router = APIRouter()
_manage = [Depends(require_capability(Capability.DOMAINS_MANAGE))]


class TenantDomainResponse(BaseModel):
    id: str
    hostname: str
    is_primary: bool
    verified: bool

    @staticmethod
    def from_entity(domain: TenantDomain) -> TenantDomainResponse:
        return TenantDomainResponse(
            id=str(domain.id),
            hostname=domain.hostname,
            is_primary=domain.is_primary,
            verified=domain.verified,
        )


class RegisterTenantDomainRequest(BaseModel):
    hostname: str


@router.post(
    "/domains",
    status_code=201,
    response_model=TenantDomainResponse,
    dependencies=_manage,
)
async def register_domain(
    body: RegisterTenantDomainRequest,
    principal: PrincipalDep,
    use_case: RegisterTenantDomainDep,
) -> TenantDomainResponse:
    assert principal.tenant_id is not None
    domain = await use_case(
        tenant_id=principal.tenant_id,
        hostname=body.hostname,
        actor_user_id=principal.user_id,
    )
    return TenantDomainResponse.from_entity(domain)


@router.get("/domains", response_model=list[TenantDomainResponse])
async def list_domains(
    principal: PrincipalDep, use_case: ListTenantDomainsDep
) -> list[TenantDomainResponse]:
    assert principal.tenant_id is not None
    domains = await use_case(tenant_id=principal.tenant_id)
    return [TenantDomainResponse.from_entity(domain) for domain in domains]
