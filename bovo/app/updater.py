"""Auto-updater Bovo ASF Manager — MSI + SHA256 + silent install.

Version enrichie qui supporte deux canaux de mise à jour :

* **UNC** : ``latest.json`` sur un partage réseau (``\\SERVEUR\\Partage\\Bovo``).
  Le MSI est déjà présent à côté, ``launch_installer`` lance msiexec dessus.
* **HTTP(S)** : ``latest.json`` accessible en HTTP. Le MSI est téléchargé
  depuis ``msi_url`` dans ``%TEMP%\\Bovo-Update\\``, son SHA256 vérifié,
  puis msiexec installe silencieusement (``/qn``).

L'auto-update est TOTALEMENT sûr vis-à-vis des données utilisateur :
Windows Installer désinstalle proprement l'ancienne version (via
``upgrade_code`` fixe), puis installe la nouvelle. Le dossier
``%APPDATA%\\Bovo\\`` n'est jamais touché — préférences, journal,
« Se souvenir de moi » sont préservés.

Contrat ``latest.json`` (émis par ``publish-release.ps1``) :

    {
      "version":       "1.7.0",
      "msi_url":       "http://serveur/updates/Bovo-Setup.msi",  // optionnel
      "msi_path":      "\\\\SERVEUR\\Partage\\Bovo\\Bovo-Setup.msi",  // optionnel
      "sha256":        "abcdef123...",
      "size":          62914560,
      "release_notes": "...",
      "mandatory":     false,
      "published_at":  "2026-07-30T10:15:00+00:00"
    }

Au moins un de ``msi_url`` / ``msi_path`` doit être présent. Si les deux
le sont, l'updater tente d'abord ``msi_url`` (téléchargement HTTP), puis
retombe sur ``msi_path`` (UNC) en cas d'échec.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
import threading
from dataclasses import dataclass, field
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
    msi_url: str = ""
    msi_path: str = ""
    sha256: str = ""
    size: int = 0
    release_notes: str = ""
    mandatory: bool = False
    published_at: str = ""


def _parse_version(v: str) -> tuple[int, ...]:
    """Convertit une chaîne SemVer en tuple pour comparaison numérique."""
    parts: list[int] = []
    for chunk in v.split("."):
        try:
            parts.append(int(chunk.split("-")[0].split("+")[0]))
        except ValueError:
            parts.append(0)
    return tuple(parts)


def check_for_update(latest_json_source: str | Path) -> UpdateInfo | None:
    """Interroge la source de mise à jour et retourne un ``UpdateInfo``.

    Accepte :
      * chemin UNC / local vers ``latest.json`` ;
      * URL HTTP(S).

    Retourne ``None`` si aucune mise à jour disponible ou en cas d'erreur
    (jamais bloquant).
    """
    src = str(latest_json_source).strip()
    if not src:
        return None
    payload: dict = {}
    try:
        if src.startswith(("http://", "https://")):
            import requests
            resp = requests.get(src, timeout=8)
            resp.raise_for_status()
            payload = resp.json()
        else:
            path = Path(src)
            if not path.exists():
                logger.info("check_for_update: %s introuvable — skip.", src)
                return None
            payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 — never blocking
        logger.warning("check_for_update: échec de lecture (%s).", exc)
        return None

    latest = str(payload.get("version", "")).strip()
    msi_url = str(payload.get("msi_url", "")).strip()
    msi_path = str(payload.get("msi_path", "")).strip()

    if not latest:
        logger.warning("check_for_update: pas de champ 'version' dans %s", src)
        return None
    if not (msi_url or msi_path):
        logger.warning(
            "check_for_update: aucun msi_url/msi_path dans %s — impossible d'installer.",
            src,
        )
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
        msi_url=msi_url,
        msi_path=msi_path,
        sha256=str(payload.get("sha256", "")).strip().lower(),
        size=int(payload.get("size", 0) or 0),
        release_notes=str(payload.get("release_notes", "")).strip(),
        mandatory=bool(payload.get("mandatory", False)),
        published_at=str(payload.get("published_at", "")).strip(),
    )


def check_for_update_async(
    latest_json_source: str | Path,
    on_available: Callable[[UpdateInfo], None],
) -> None:
    """Lance ``check_for_update`` dans un thread daemon."""
    def _worker() -> None:
        info = check_for_update(latest_json_source)
        if info is not None:
            try:
                on_available(info)
            except Exception:  # noqa: BLE001
                logger.exception("Callback on_available a levé une exception.")

    threading.Thread(target=_worker, daemon=True, name="bovo-updater").start()


# --------------------------------------------------------------------- #
# Téléchargement + vérification SHA256
# --------------------------------------------------------------------- #
def _sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    """Calcule le SHA256 d'un fichier en streaming (économe en RAM)."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            block = f.read(chunk)
            if not block:
                break
            h.update(block)
    return h.hexdigest().lower()


def _download_msi(
    url: str,
    dest: Path,
    expected_sha256: str = "",
    progress: Callable[[int, int], None] | None = None,
) -> bool:
    """Télécharge un MSI depuis ``url`` vers ``dest`` (streaming).

    Vérifie ensuite le SHA256 si fourni. Retourne ``True`` si le fichier
    est prêt et valide, ``False`` sinon (fichier partiel supprimé).
    """
    import requests

    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    try:
        with requests.get(url, stream=True, timeout=30) as resp:
            resp.raise_for_status()
            total = int(resp.headers.get("Content-Length", 0))
            downloaded = 0
            with tmp.open("wb") as f:
                for chunk in resp.iter_content(chunk_size=1 << 20):
                    if not chunk:
                        continue
                    f.write(chunk)
                    downloaded += len(chunk)
                    if progress and total:
                        try:
                            progress(downloaded, total)
                        except Exception:  # noqa: BLE001
                            pass
    except Exception as exc:  # noqa: BLE001
        logger.error("Téléchargement MSI échoué (%s).", exc)
        tmp.unlink(missing_ok=True)
        return False

    if expected_sha256:
        actual = _sha256_file(tmp)
        if actual != expected_sha256.lower():
            logger.error(
                "SHA256 mismatch : attendu=%s, calculé=%s — refus d'installer.",
                expected_sha256, actual,
            )
            tmp.unlink(missing_ok=True)
            return False
        logger.info("SHA256 OK : %s", actual)

    tmp.replace(dest)
    return True


# --------------------------------------------------------------------- #
# Lancement de l'installation
# --------------------------------------------------------------------- #
def _msiexec_args(msi: Path, silent: bool) -> list[str]:
    """Assemble la ligne de commande msiexec.

    Windows Installer 5.0+ (Win10/11) — les options utilisées :

    * ``/i``          : install (upgrade code géré côté MSI).
    * ``/qn``         : quiet no-UI (installation totalement silencieuse).
    * ``/qb``         : quiet basic (une petite barre de progression).
    * ``/norestart``  : ne redémarre pas Windows automatiquement.
    * ``/L*v <log>``  : log verbeux dans un fichier (utile en debug).
    """
    log = Path(tempfile.gettempdir()) / "Bovo-msi-install.log"
    ui = "/qn" if silent else "/qb"
    return [
        "msiexec", "/i", str(msi),
        ui, "/norestart",
        "/L*v", str(log),
    ]


def launch_installer(msi_path: str | Path, silent: bool = True) -> bool:
    """Lance l'installateur MSI puis retourne (ne quitte pas l'app ici).

    L'appelant DOIT fermer l'app côté Tk juste après l'appel — sinon les
    fichiers verrouillés empêchent la MAJ. Le processus msiexec survit à
    la fermeture grâce à ``DETACHED_PROCESS`` (Windows uniquement).

    Args:
        msi_path: Chemin local vers le ``.msi`` (déjà téléchargé/résolu).
        silent:   Si ``True`` (défaut), installation totalement silencieuse
                  (``/qn``). Sinon, barre de progression basique (``/qb``).

    Retourne ``True`` si msiexec a bien démarré.
    """
    msi = Path(msi_path)
    if not msi.exists():
        logger.error("launch_installer: MSI introuvable : %s", msi)
        return False
    args = _msiexec_args(msi, silent=silent)
    try:
        flags = 0
        if os.name == "nt":
            # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP.
            flags = 0x00000008 | 0x00000200
        subprocess.Popen(args, creationflags=flags)  # noqa: S603
        logger.info(
            "launch_installer: msiexec lancé (%s) — mode %s.",
            msi.name, "silent /qn" if silent else "basic /qb",
        )
        return True
    except OSError as exc:
        logger.error("launch_installer: échec lancement msiexec (%s).", exc)
        return False


def install_update(
    info: UpdateInfo,
    silent: bool = True,
    progress: Callable[[int, int], None] | None = None,
) -> bool:
    """Télécharge (si HTTP) puis installe silencieusement une mise à jour.

    Ordre de préférence pour obtenir le MSI :
      1. ``info.msi_url`` (HTTP) → téléchargement dans %TEMP%\\Bovo-Update\\,
         vérification SHA256, puis msiexec.
      2. ``info.msi_path`` (UNC / local) → msiexec direct sur le chemin.

    Args:
        info:     Métadonnées renvoyées par :func:`check_for_update`.
        silent:   Installation totalement silencieuse (``/qn``, défaut).
        progress: Callback ``(downloaded, total)`` en octets pendant le
                  téléchargement HTTP (facultatif).

    Retourne ``True`` si l'installation a été DÉMARRÉE avec succès.
    L'appelant doit fermer l'app juste après pour laisser Windows
    Installer écraser les fichiers verrouillés.
    """
    # Tentative HTTP en premier (accessible hors partage réseau).
    if info.msi_url:
        cache_dir = Path(tempfile.gettempdir()) / "Bovo-Update"
        dest = cache_dir / f"Bovo-{info.latest_version}.msi"
        if _download_msi(info.msi_url, dest, info.sha256, progress):
            return launch_installer(dest, silent=silent)
        logger.warning("install_update: HTTP download échoué, fallback UNC.")

    # Fallback UNC / chemin local.
    if info.msi_path:
        # Optionnel : vérification SHA256 aussi sur le chemin UNC.
        if info.sha256:
            unc = Path(info.msi_path)
            if unc.exists():
                actual = _sha256_file(unc)
                if actual != info.sha256.lower():
                    logger.error(
                        "install_update: SHA256 mismatch UNC (attendu=%s, calculé=%s).",
                        info.sha256, actual,
                    )
                    return False
        return launch_installer(info.msi_path, silent=silent)

    logger.error("install_update: aucun MSI accessible (ni HTTP ni UNC).")
    return False


__all__ = [
    "UpdateInfo",
    "check_for_update",
    "check_for_update_async",
    "install_update",
    "launch_installer",
]
