"""Internal helpers for converting dict <-> object for reports."""
from types import SimpleNamespace
from typing import Any


def _to_obj(d: Any) -> Any:
    """Recursively convert a dict/list structure to SimpleNamespace/list-of-obj
    so attribute-style access (c.label, c.passed) works on data loaded from
    JSON. Non-dict/non-list values pass through unchanged.
    """
    if isinstance(d, dict):
        return SimpleNamespace(**{k: _to_obj(v) for k, v in d.items()})
    if isinstance(d, list):
        return [_to_obj(v) for v in d]
    return d


def hydrate(d: Any) -> Any:
    """Public alias for _to_obj."""
    return _to_obj(d)
