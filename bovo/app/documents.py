"""Gestion documentaire de Bovo ASF Manager.

Attache des fichiers (PDF, images, docs) à une intervention ou un rapport.
Les fichiers sont copiés localement dans ``bovo/documents/<AAAA>/<uuid>.<ext>``
et référencés dans la table SQLite ``documents``. Aucun BLOB en base.

Aucune logique GUI ici — le service est consommé par ``gui.py``.
"""

from __future__ import annotations

import shutil
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from app.database import Database
from app.logger import LogAction, LogLevel, get_logger, log_action
from app.utils import PROJECT_ROOT, human_readable_size

logger = get_logger("documents")

DOCUMENTS_DIR = PROJECT_ROOT / "documents"


@dataclass(slots=True)
class Document:
    """Métadonnées d'un document attaché."""

    id: int
    entity: str
    entity_id: str
    filename: str
    storage_path: str
    mime_type: str
    size_bytes: int
    uploaded_by: str
    uploaded_at: str
    notes: str = ""

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> Document:
        """Construit un Document depuis une ligne SQLite."""
        return cls(
            id=int(row["id"]),
            entity=row.get("entity", "") or "",
            entity_id=row.get("entity_id", "") or "",
            filename=row.get("filename", "") or "",
            storage_path=row.get("storage_path", "") or "",
            mime_type=row.get("mime_type", "") or "",
            size_bytes=int(row.get("size_bytes") or 0),
            uploaded_by=row.get("uploaded_by", "") or "",
            uploaded_at=row.get("uploaded_at", "") or "",
            notes=row.get("notes", "") or "",
        )

    @property
    def path(self) -> Path:
        """Chemin absolu du fichier."""
        return Path(self.storage_path)

    @property
    def size_readable(self) -> str:
        """Taille lisible (Ko/Mo/Go)."""
        return human_readable_size(self.size_bytes)


_MIME_BY_EXT: dict[str, str] = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xls": "application/vnd.ms-excel",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".txt": "text/plain",
}


def _guess_mime(extension: str) -> str:
    """Retourne le MIME probable en fonction de l'extension."""
    return _MIME_BY_EXT.get(extension.lower(), "application/octet-stream")


class DocumentService:
    """Service de gestion documentaire (attach / list / delete)."""

    def __init__(self, database: Database) -> None:
        """Initialise le service et crée la table ``documents`` si absente."""
        self._db = database
        self._db.ensure_documents_table()
        DOCUMENTS_DIR.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ #
    # Attach / list / delete
    # ------------------------------------------------------------------ #
    def attach(
        self,
        *,
        entity: str,
        entity_id: str,
        source: Path,
        uploaded_by: str,
        notes: str = "",
    ) -> Document:
        """Copie un fichier dans le stockage local et l'enregistre en base.

        Args:
            entity: Nom d'entité (ex. ``intervention``, ``rapport``).
            entity_id: Identifiant de l'entité (chaîne).
            source: Chemin du fichier source à joindre.
            uploaded_by: Username de l'auteur (pour traçabilité).
            notes: Commentaire optionnel.

        Returns:
            Le document persisté.

        Raises:
            FileNotFoundError: Si le fichier source est introuvable.
        """
        source = Path(source)
        if not source.exists() or not source.is_file():
            raise FileNotFoundError(f"Fichier introuvable : {source}")

        year_dir = DOCUMENTS_DIR / str(date.today().year)
        year_dir.mkdir(parents=True, exist_ok=True)
        safe_name = f"{uuid.uuid4().hex}{source.suffix.lower()}"
        destination = year_dir / safe_name
        shutil.copy2(source, destination)

        now = datetime.now(UTC).isoformat()
        new_id = self._db.insert_document(
            entity=entity, entity_id=str(entity_id),
            filename=source.name, storage_path=str(destination),
            mime_type=_guess_mime(source.suffix),
            size_bytes=destination.stat().st_size,
            uploaded_by=uploaded_by, uploaded_at=now, notes=notes,
        )
        log_action(
            self._db, LogAction.CREATE,
            f"Document attaché à {entity}#{entity_id} : {source.name}",
            level=LogLevel.SUCCESS,
        )
        return Document(
            id=new_id, entity=entity, entity_id=str(entity_id),
            filename=source.name, storage_path=str(destination),
            mime_type=_guess_mime(source.suffix),
            size_bytes=destination.stat().st_size,
            uploaded_by=uploaded_by, uploaded_at=now, notes=notes,
        )

    def list_for(self, entity: str, entity_id: str = "") -> list[Document]:
        """Liste les documents attachés à une entité.

        Si ``entity_id`` est vide, retourne tous les documents de l'entité.
        """
        rows = self._db.list_documents(entity=entity, entity_id=entity_id)
        return [Document.from_row(r) for r in rows]

    def list_all(self, search: str = "") -> list[Document]:
        """Liste tous les documents (utile pour l'écran Documents)."""
        rows = self._db.list_documents(search=search)
        return [Document.from_row(r) for r in rows]

    def get(self, document_id: int) -> Document | None:
        """Retourne un document par son id."""
        row = self._db.get_document(document_id)
        return Document.from_row(row) if row else None

    def delete(self, document_id: int) -> bool:
        """Supprime un document (base + fichier local). Retourne ``True`` si OK."""
        row = self._db.get_document(document_id)
        if row is None:
            return False
        try:
            path = Path(row.get("storage_path", ""))
            if path.exists():
                path.unlink()
        except OSError as exc:  # noqa: BLE001
            logger.warning("Suppression fichier échouée : %s", exc)
        self._db.delete_document(document_id)
        log_action(
            self._db, LogAction.DELETE,
            f"Document supprimé : {row.get('filename', '?')}",
            level=LogLevel.WARNING,
        )
        return True


__all__ = ["DOCUMENTS_DIR", "Document", "DocumentService"]
