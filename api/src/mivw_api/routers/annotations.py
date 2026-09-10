"""Annotation routes.

The per-series collection lives in `series.py`; this module re-exports the
item-level routes so `main.py` can mount them under a stable name.
"""

from mivw_api.routers.series import annotations_router as router

__all__ = ["router"]
