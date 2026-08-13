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

Other external source dependencies
----------------------------------

The following UBC-FRESH packages are not on PyPI yet and are expected as
local source checkouts whose paths come from configuration or environment:

- ``nemora`` — distribution fit and sampling (Phase 3).
- ``freshforge`` — workflow and matrix orchestration (Phase 5).
