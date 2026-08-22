"""Deprecated compatibility namespace for pre-CharityGraph integrations."""

from __future__ import annotations

import warnings

from charitygraph import __path__ as _charitygraph_path

warnings.warn(
    "causebase_builder is deprecated; import charitygraph instead. "
    "This compatibility namespace will be removed at the next pre-1.0 breaking release.",
    DeprecationWarning,
    stacklevel=2,
)

# Make legacy submodule imports resolve to the canonical package without copying code.
__path__ = _charitygraph_path
