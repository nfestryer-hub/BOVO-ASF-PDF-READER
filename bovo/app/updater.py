"""Auto-updater Bovo ASF Manager (mode partage réseau).

Modèle de mise à jour très simple, adapté au déploiement décrit par
l'utilisateur (MSI copié sur un partage réseau Windows) :

    \\SERVEUR\Partage\Bovo\
        Bovo-Setup.msi           ← le dernier installateur MSI
        latest.json              ← métadonnées de version publiées
        release-notes.txt        ← optionnel, notes de version

Le fichier ``latest.json`` a la forme suivante :

    {
      "version": "1.7.0",
      "msi_path": "\\\\SERVEUR\\Partage\\Bovo\\Bovo-Setup.msi",
      "release_notes": "…",
      "mandatory": false
    }

Au démarrage, l'app compare :attr:`__version__` avec ``version`` publiée.
Si une mise à jour est disponible, un bandeau non-bloquant s'affiche
(sauf si ``mandatory=true``, auquel cas un modal exige l'installation).

L'auto-updater ne bloque JAMAIS le démarrage : si le partage n'est pas
joignable (VPN coupé, poste offline…), l'app démarre normalement.
"""
from __future__ import annotations

import json
import os
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from app.logger import get_logger
from app.version import __version__

logger = get_logger("updater")


@dataclass(slots=True)
class UpdateInfo:
    """Métadonnées d'une mise à jour disponible."""

    current_version: str
    latest_version: str
    msi_path: str
    release_notes: str = ""
    mandatory: bool = False


def _parse_version(v: str) -> tuple[int, ...]:
    """Convertit une chaîne SemVer en tuple pour comparaison numérique.

    Tolérant : ``"1.2.3.4"`` ou ``"1.2"`` sont acceptés ; les composants
    non-numériques (pré-release) sont ignorés.
    """
    parts: list[int] = []
    for chunk in v.split("."):
        try:
            parts.append(int(chunk.split("-")[0].split("+")[0]))
        except ValueError:
            parts.append(0)
    return tuple(parts)


def check_for_update(latest_json_source: str | Path) -> UpdateInfo | None:
    """Interroge la source de mise à jour et retourne un ``UpdateInfo``.

    ``latest_json_source`` peut être :

    * un chemin UNC / local vers ``latest.json`` (ex : partage réseau) ;
    * une URL HTTP(S) — dans ce cas ``requests`` est utilisé.

    Retourne ``None`` si aucune mise à jour disponible ou en cas d'erreur
    (pas d'accès partage, JSON invalide, etc.). Les erreurs sont loguées
    en WARNING, jamais levées : l'app doit démarrer même offline.
    """
    src = str(latest_json_source).strip()
    if not src:
        return None
    payload: dict[str, str | bool] = {}
    try:
        if src.startswith(("http://", "https://")):
            import requests
            resp = requests.get(src, timeout=5)
            resp.raise_for_status()
            payload = resp.json()
        else:
            path = Path(src)
            if not path.exists():
                logger.info("check_for_update: %s introuvable — skip.", src)
                return None
            payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 — best-effort, jamais bloquant
        logger.warning("check_for_update: échec de lecture (%s).", exc)
        return None

    latest = str(payload.get("version", "")).strip()
    msi_path = str(payload.get("msi_path", "")).strip()
    if not latest or not msi_path:
        logger.warning("check_for_update: payload incomplet — %s", payload)
        return None
    if _parse_version(latest) <= _parse_version(__version__):
        logger.info(
            "check_for_update: déjà à jour (installée=%s, distribuée=%s).",
            __version__, latest,
        )
        return None
    return UpdateInfo(
        current_version=__version__,
        latest_version=latest,
        msi_path=msi_path,
        release_notes=str(payload.get("release_notes", "")).strip(),
        mandatory=bool(payload.get("mandatory", False)),
    )


def check_for_update_async(
    latest_json_source: str | Path,
    on_available: Callable[[UpdateInfo], None],
) -> None:
    """Lance ``check_for_update`` dans un thread daemon.

    Le callback ``on_available`` est invoqué UNIQUEMENT si une mise à
    jour est disponible. Le callback doit lui-même schedule ses appels
    Tk via ``root.after(0, ...)`` pour rester thread-safe.
    """
    def _worker() -> None:
        info = check_for_update(latest_json_source)
        if info is not None:
            try:
                on_available(info)
            except Exception:  # noqa: BLE001 — log & swallow
                logger.exception("Callback on_available a levé une exception.")

    threading.Thread(target=_worker, daemon=True, name="bovo-updater").start()


def launch_installer(msi_path: str | Path, silent: bool = False) -> bool:
    """Lance l'installateur MSI puis quitte l'app.

    Windows n'autorise pas la mise à jour à chaud (l'exe et ses DLLs
    sont verrouillés en écriture pendant l'exécution). On délègue donc
    à ``msiexec`` qui exécute l'installation, puis on ferme l'app pour
    que la nouvelle version puisse écraser proprement les fichiers.

    Args:
        msi_path: Chemin vers le fichier ``.msi`` (UNC ou local).
        silent:  Si ``True``, installation sans interaction (``/qb``).

    Retourne ``True`` si l'installateur a démarré, ``False`` sinon.
    """
    msi = Path(msi_path)
    if not msi.exists():
        logger.error("launch_installer: MSI introuvable : %s", msi)
        return False
    args = ["msiexec", "/i", str(msi)]
    if silent:
        args += ["/qb"]  # barre de progression basique, sans questions
    args += ["/norestart"]
    try:
        # DETACHED_PROCESS + CREATE_NEW_PROCESS_GROUP pour survivre à la
        # fermeture de notre app. os.name est 'nt' sur Windows.
        flags = 0
        if os.name == "nt":
            flags = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
        subprocess.Popen(args, creationflags=flags)  # noqa: S603 — args contrôlés
        logger.info("launch_installer: msiexec lancé pour %s", msi)
        return True
    except OSError as exc:
        logger.error("launch_installer: échec lancement msiexec (%s).", exc)
        return False


__all__ = [
    "UpdateInfo",
    "check_for_update",
    "check_for_update_async",
    "launch_installer",
]
