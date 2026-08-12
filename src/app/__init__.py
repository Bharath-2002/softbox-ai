"""Softbox AI backend.

Layering (enforced by import-linter, see setup.cfg):

    api -> agents -> features -> services -> entities -> shared

Ports are declared in ``services``; implementations live in ``infrastructure``,
which only ``bootstrap`` may import.
"""
