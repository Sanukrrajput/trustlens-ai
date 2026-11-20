"""Machine-learning package for TrustLens AI.

The subpackages are deliberately split into:

* :mod:`app.ml.features` - shared text normalisation and feature definitions.
* :mod:`app.ml.datasets` - dataset loaders with explicit provenance.
* :mod:`app.ml.training` - offline training and artifact publication.
* :mod:`app.ml.evaluation` - metric computation and threshold selection.
* :mod:`app.ml.inference` - runtime prediction with honest fallbacks.

Only artifacts explicitly marked ``approved: true`` in the model manifest are
loaded at runtime. Nothing in this package auto-promotes a model.
"""

from __future__ import annotations

__all__ = ["features", "datasets", "evaluation", "inference", "training"]
