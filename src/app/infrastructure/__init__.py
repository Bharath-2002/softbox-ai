"""Adapters implementing the ports declared in ``services``.

SQLAlchemy repositories, object storage, provider SDKs, OAuth clients, the
queue driver.

Importable ONLY by ``bootstrap``. Nothing in api/agents/features/services/
entities may import this package - enforced by the ``infra_isolation``
contract in setup.cfg.
"""
