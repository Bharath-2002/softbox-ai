"""In-memory fakes for every port in ``app.services.ports``.

Each is exercised by the same contract test suite as its real adapter
(``tests/services/test_*_contract.py``), so a fake cannot drift into a lie
about the behaviour it stands in for.
"""
