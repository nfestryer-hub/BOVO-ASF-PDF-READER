"""Router : documents attachés (upload + download + suppression)."""

from __future__ import annotations

import shutil
import uuid
from datetime import date
from pathlib import Path
from typing import Annotated

from fastapi import (
    APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status,
)
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import audit
from app.db import get_db
from app.deps import get_current_user, require_editor
from app.models import Document, User
from app.schemas import DocumentOut

router = APIRouter(prefix="/api/documents", tags=["documents"])

STORAGE_ROOT = Path("/data/documents")
_MIME_BY_EXT: dict[str, str] = {
    ".pdf": "application/pdf",
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
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


@router.get("", response_model=list[DocumentOut])
def list_documents(
    _user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    entity: Annotated[str, Query(max_length=40)] = "",
    entity_id: Annotated[str, Query(max_length=80)] = "",
) -> list[DocumentOut]:
    """Liste les documents (filtres optionnels par entité)."""
    query = select(Document).order_by(Document.id.desc())
    if entity:
        query = query.where(Document.entity == entity)
    if entity_id:
        query = query.where(Document.entity_id == entity_id)
    docs = db.scalars(query).all()
    return [DocumentOut.model_validate(d) for d in docs]


@router.post("", response_model=DocumentOut, status_code=status.HTTP_201_CREATED)
def upload_document(
    entity: Annotated[str, Form(max_length=40)],
    entity_id: Annotated[str, Form(max_length=80)],
    file: Annotated[UploadFile, File()],
    user: Annotated[User, Depends(require_editor)],
    db: Annotated[Session, Depends(get_db)],
    notes: Annotated[str, Form(max_length=500)] = "",
) -> DocumentOut:
    """Téléverse un fichier et l'attache à une entité (Admin ou Planificateur)."""
    STORAGE_ROOT.mkdir(parents=True, exist_ok=True)
    original_name = file.filename or "document"
    suffix = Path(original_name).suffix or ""
    year_dir = STORAGE_ROOT / str(date.today().year)
    year_dir.mkdir(parents=True, exist_ok=True)
    stored_name = f"{uuid.uuid4().hex}{suffix.lower()}"
    destination = year_dir / stored_name
    with destination.open("wb") as target:
        shutil.copyfileobj(file.file, target)
    size = destination.stat().st_size
    doc = Document(
        entity=entity, entity_id=entity_id, filename=original_name,
        storage_path=str(destination),
        mime_type=file.content_type or _guess_mime(suffix),
        size_bytes=size, uploaded_by=user.username, notes=notes,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    audit.record(
        db, user=user, action="create", entity="document",
        entity_id=str(doc.id),
        after={"filename": original_name, "entity": entity,
               "entity_id": entity_id, "size_bytes": size},
    )
    return DocumentOut.model_validate(doc)


@router.get("/{document_id}/download")
def download_document(
    document_id: int,
    _user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> FileResponse:
    """Télécharge le fichier binaire d'un document."""
    doc = db.get(Document, document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document introuvable.")
    path = Path(doc.storage_path)
    if not path.exists():
        raise HTTPException(status_code=410, detail="Fichier absent du stockage.")
    return FileResponse(
        path=path, filename=doc.filename, media_type=doc.mime_type or None,
    )


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    document_id: int,
    user: Annotated[User, Depends(require_editor)],
    db: Annotated[Session, Depends(get_db)],
) -> None:
    """Supprime un document (base + fichier)."""
    doc = db.get(Document, document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document introuvable.")
    before = {"filename": doc.filename, "entity": doc.entity,
              "entity_id": doc.entity_id}
    path = Path(doc.storage_path)
    if path.exists():
        try:
            path.unlink()
        except OSError:  # pragma: no cover — best effort
            pass
    db.delete(doc)
    db.commit()
    audit.record(
        db, user=user, action="delete", entity="document",
        entity_id=str(document_id), before=before,
    )
