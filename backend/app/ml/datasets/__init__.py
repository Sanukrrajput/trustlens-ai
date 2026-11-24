"""Dataset loaders with explicit provenance and documented limitations."""

from __future__ import annotations

from app.ml.datasets.difraud import (
    ALL_DOMAINS as DIFRAUD_ALL_DOMAINS,
)
from app.ml.datasets.difraud import (
    JOB_DOMAINS as DIFRAUD_JOB_DOMAINS,
)
from app.ml.datasets.difraud import (
    MESSAGE_DOMAINS as DIFRAUD_MESSAGE_DOMAINS,
)
from app.ml.datasets.difraud import difraud_limitations, load_difraud_dataset
from app.ml.datasets.synthetic_messages import (
    DATASET_PROVENANCE as SYNTHETIC_MESSAGE_PROVENANCE,
)
from app.ml.datasets.synthetic_messages import (
    load_synthetic_messages,
    synthetic_message_dataframe,
)

__all__ = [
    "DIFRAUD_ALL_DOMAINS",
    "DIFRAUD_JOB_DOMAINS",
    "DIFRAUD_MESSAGE_DOMAINS",
    "difraud_limitations",
    "load_difraud_dataset",
    "SYNTHETIC_MESSAGE_PROVENANCE",
    "load_synthetic_messages",
    "synthetic_message_dataframe",
]
