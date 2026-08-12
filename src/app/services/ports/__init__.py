"""Port declarations (``typing.Protocol``).

A port names a capability the domain needs without naming a technology.
Every port has a fake for tests, and a contract test suite that runs against
both the fake and the real adapter.
"""
