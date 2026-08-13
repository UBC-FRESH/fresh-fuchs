Development
===========

(Under construction — Phase 0. Filled in as the pipeline lands.)

Local checks::

   python -m ruff check .
   python -m pytest
   sphinx-build -b html docs _build/html -W
   python -m build
   twine check dist/*

Governance, the strict development workflow, issue-quality standards, and
the reuse boundary are documented in ``AGENTS.md`` and ``CONTRIBUTING.md``.
