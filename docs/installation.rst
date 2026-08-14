Installation
============

Requirements
------------

- Python >= 3.11
- The ``ws3`` and ``highspy`` packages (PyPI; installed by default)

Editable install::

   pip install -e ".[dev]"

Verification::

   fresh-fuchs --help
   python -m pytest

Bundle builds (Phase 1)
-----------------------

Building the ws3 model from a real femic bundle requires the ``bundle``
extra, which pulls ``femic`` (pinned to the PyPI alpha ``0.2.0a1``) and
``geopandas``::

   pip install -e ".[dev,bundle]"

A local femic source checkout can be used instead (for example during
development alongside the femic repo)::

   pip install --no-deps -e /path/to/femic

Orchestration (Phase 5)
-----------------------

The freshforge workflow/matrix orchestration (``fresh_fuchs.orchestration``)
requires the ``orchestration`` extra, which pulls ``freshforge`` (pinned to
the PyPI alpha ``0.1.0a6``, the first release with the evidence-manifest
API)::

   pip install -e ".[dev,orchestration]"

The ``dev`` extra already includes ``freshforge``, so the full test suite
(including the orchestration tests) runs in CI. Without freshforge, the core
package and the rest of the test suite still run — the orchestration tests
guard with ``pytest.importorskip``. A local source checkout can be used
instead::

   pip install --no-deps -e /path/to/freshforge

Other external source dependencies
----------------------------------

``nemora`` — distribution fit and sampling — is an optional stochastic-driver
basis and is not yet on PyPI (expected as a local source checkout whose path
comes from configuration). The v0.1.0a1 scenario engine uses a built-in
Gaussian/fixed distribution registry, so nemora is not required for the
default pipeline.
