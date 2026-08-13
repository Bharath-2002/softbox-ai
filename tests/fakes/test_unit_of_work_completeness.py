"""Guards against the fake UnitOfWork silently drifting from the port.

Each repository is hand-added in three places (FakeUnitOfWork's constructor,
FakeUnitOfWorkFactory.__init__, and its __call__) — nothing forces those three
to stay in sync with the UnitOfWork Protocol. A property wired into __init__
but missed in __call__ would still let every existing test pass; only a test
that touches that exact property would ever notice. This test makes the gap
visible immediately instead of at the next milestone's expense.
"""

from __future__ import annotations

from app.services.ports.unit_of_work import UnitOfWork
from tests.fakes.unit_of_work import FakeUnitOfWorkFactory


def test_fake_exposes_every_repository_the_protocol_declares() -> None:
    protocol_properties = {
        name for name, value in vars(UnitOfWork).items() if isinstance(value, property)
    }
    assert protocol_properties, "sanity check: the protocol declares no properties at all"

    uow = FakeUnitOfWorkFactory()(None)

    for name in protocol_properties:
        assert hasattr(uow, name), f"FakeUnitOfWork is missing '{name}' from UnitOfWork"
