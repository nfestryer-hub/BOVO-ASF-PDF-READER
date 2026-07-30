"""Numéro de version canonique de l'application Bovo ASF Manager.

Utilisé par :
* le bandeau « À propos » de l'app (affichage utilisateur)
* le mécanisme d'auto-update (comparaison avec la version distribuée)
* le build MSI (metadata Windows via cx_Freeze)

Convention SemVer : ``MAJOR.MINOR.PATCH``.
"""

__version__ = "1.6.0"
