Development
===========

Local verification gate (run all before opening a PR)::

   python -m ruff check .
   python -m ruff format --check .
   python -m pytest
   sphinx-build -b html docs _build/html -W
   python -m build
   twine check dist/*

Testing
-------

- All tests use synthetic/public-safe fixtures
  (``fresh_fuchs.instance.synthetic`` and ``tests/conftest.py``); no private
  bundle data, commercial GIS, desktop applications, credentials, or Gurobi
  licences are required in CI.
- The orchestration tests (``tests/test_orchestration.py``) need the
  ``freshforge`` package (the ``orchestration``/``dev`` extra) and guard
  with ``pytest.importorskip`` so the core suite stays green without it.
- Deterministic anchors (managed land base, even-flow mean harvest, NPV-max
  parity) are regression-gated in the tests and recorded in
  ``planning/validation-report.md``.

ws3 version compatibility
-------------------------

The suite runs against both PyPI ``ws3`` 1.0.5 (what CI installs) and the
editable 1.1.0a4 source checkout. Two compatibility rules matter:

- Never write ``dt.operability[acode][period] = None`` — 1.0.5 crashes; use
  an empty age window ``(0, -1)`` to close a period.
- Rotation floor/ceiling policies are applied as operability age windows
  ``(floor, ceiling)``, which works on both versions.

Layout
------

- ``src/fresh_fuchs/instance`` — bundle -> extended ws3 model + synthetic
  instance (Phase 1).
- ``src/fresh_fuchs/economy`` — NPV surface and cash flows (Phase 2).
- ``src/fresh_fuchs/scenario`` — full-MC scenario engine (Phase 3).
- ``src/fresh_fuchs/outer`` — policy grid + risk + ranking (Phase 4).
- ``src/fresh_fuchs/orchestration`` — freshforge workflows/matrices +
  evidence (Phase 5).
- ``src/fresh_fuchs/cli.py`` — thin CLI wrappers over the Python APIs.

Governance, the strict development workflow (one phase = one parent issue =
one feature branch), issue-quality standards, and the reuse boundary are
documented in ``AGENTS.md`` and ``CONTRIBUTING.md``.
