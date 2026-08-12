"""Use cases.

One class per use case. Owns the transaction boundary (one use case, one
transaction) and emits domain events to the outbox in that same transaction.

May import: services, entities, shared.
"""
