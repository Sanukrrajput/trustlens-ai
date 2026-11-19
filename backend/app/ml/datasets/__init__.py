"""Dataset loaders with explicit provenance and documented limitations."""

from __future__ import annotations

from app.ml.datasets.synthetic_messages import (
    DATASET_PROVENANCE as SYNTHETIC_MESSAGE_PROVENANCE,
)
from app.ml.datasets.synthetic_messages import (
    load_synthetic_messages,
    synthetic_message_dataframe,
)

__all__ = [
    "SYNTHETIC_MESSAGE_PROVENANCE",
    "load_synthetic_messages",
    "synthetic_message_dataframe",
]
