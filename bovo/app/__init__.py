"""Bovo ASF Manager — package applicatif.

Logiciel professionnel de gestion automatique des interventions ASF réalisées
par BOVO. Toute la logique métier est répartie dans les modules de ce package ;
l'interface (``gui.py``) ne contient aucune logique métier.

Développé par HENRI Dylan.
"""

from __future__ import annotations

__app_name__ = "Bovo ASF Manager"
from app.version import __version__  # noqa: F401 - source unique v1.2+
__author__ = "HENRI Dylan"

__all__ = ["__app_name__", "__version__", "__author__"]
