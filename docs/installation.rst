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
extra, which pulls ``femic`` (source dependency) and ``geopandas``::

   pip install -e ".[dev,bundle]"

``femic`` is not on PyPI; the extra installs it from the UBC-FRESH git
repository at the pinned tag. A local source checkout can be used instead
(for example during development alongside the femic repo)::

   pip install --no-deps -e /path/to/femic

Orchestration (Phase 5)
-----------------------

The freshforge workflow/matrix orchestration (``fresh_fuchs.orchestration``)
requires the ``orchestration`` extra, which pulls ``freshforge`` (source
dependency, not on PyPI) from the UBC-FRESH git repository at the pinned
commit::

   pip install -e ".[dev,orchestration]"

The ``dev`` extra already includes ``freshforge``, so the full test suite
(including the orchestration tests) runs in CI. Without freshforge, the core
package and the rest of the test suite still run — the orchestration tests
guard with ``pytest.importorskip``. A local source checkout can be used
instead::

   pip install --no-deps -e /path/to/freshforge

Other external source dependencies
----------------------------------

The following UBC-FRESH packages are not on PyPI yet and are expected as
local source checkouts whose paths come from configuration or environment:

- ``nemora`` — distribution fit and sampling (an optional stochastic-driver
  basis; the v0.1.0a1 scenario engine uses a built-in Gaussian/fixed
  distribution registry, so nemora is not required for the default pipeline).
