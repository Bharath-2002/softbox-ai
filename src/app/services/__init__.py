"""Domain services and ALL ports.

Ports are ``typing.Protocol`` declarations - repositories, object storage,
model providers, channel publishers, the task queue, the unit of work. Their
implementations live in ``infrastructure`` and are wired in ``bootstrap``.

May import: entities, shared.
"""
