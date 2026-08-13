Installation
============

(Under construction — Phase 0. Filled in as the pipeline lands.)

Requirements
------------

- Python >= 3.11
- The ``ws3`` and ``highspy`` packages (PyPI; installed by default)

External source dependencies
----------------------------

The following UBC-FRESH packages are not on PyPI yet and are expected as
local source checkouts whose paths come from configuration or environment:

- ``femic`` — instance bundle and model bridge.
- ``nemora`` — distribution fit and sampling.
- ``freshforge`` — workflow and matrix orchestration.

Editable install::

   pip install -e ".[dev]"

Verification::

   fresh-fuchs --help
   python -m pytest
