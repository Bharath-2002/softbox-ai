"""SQLAlchemy adapters: engine/session construction and the unit of work.

Imperative ORM mappings (D7) land here too, from the first persisted entity
in M2 onward — ``mapping.py``, kept separate from the pure domain classes in
``app.entities``.
"""
