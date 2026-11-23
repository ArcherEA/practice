import uuid
from typing import Any

from fastapi import APIRouter, HTTPException
from sqlmodel import col, func, select

from app.api.deps import CurrentUser, RequireAdmin, SessionDep, StorageDep
from app.core import files as file_service
from app.core.config import settings
from app.core.roles import UserRole, has_role
from app.core.storage import StorageNotConfiguredError
from app.models import (
    DownloadUrl,
    File,
    FileCreate,
    FilePublic,
    FilesPublic,
    Message,
    StorageUsage,
    UploadTicket,
)

router = APIRouter(prefix="/files", tags=["files"])


def _get_own_file(
    session: SessionDep,
    current_user: CurrentUser,
    file_id: uuid.UUID,
    *,
    admin_ok: bool,
) -> File:
    file = session.get(File, file_id)
    if file is None:
        raise HTTPException(status_code=404, detail="File not found")
    is_owner = file.owner_id == current_user.id
    if not is_owner and not (admin_ok and has_role(current_user, UserRole.admin)):
        raise HTTPException(status_code=404, detail="File not found")
    return file


@router.post("/", response_model=UploadTicket)
def create_upload(
    *,
    session: SessionDep,
    storage: StorageDep,
    current_user: CurrentUser,
    file_in: FileCreate,
) -> Any:
    """
    Reserve a file and get a presigned PUT URL. Upload the bytes straight to
    `upload_url` (with `upload_headers`), then call `POST /files/{id}/confirm`.
    Errors: 413 too large or user quota full, 429 daily limit, 507 storage full.
    """
    return file_service.create_upload(
        session=session, storage=storage, user=current_user, data=file_in
    )


@router.get("/usage", dependencies=[RequireAdmin], response_model=StorageUsage)
def read_usage(session: SessionDep) -> Any:
    """Total storage used vs limit, file count and top users by bytes (admin only)."""
    return file_service.storage_usage(session=session)


@router.get("/", response_model=FilesPublic)
def read_files(
    session: SessionDep, current_user: CurrentUser, skip: int = 0, limit: int = 100
) -> Any:
    """List my confirmed files, newest first."""
    where = (File.owner_id == current_user.id, File.status == "ready")
    count = session.exec(select(func.count()).select_from(File).where(*where)).one()
    files = session.exec(
        select(File)
        .where(*where)
        .order_by(col(File.created_at).desc())
        .offset(skip)
        .limit(limit)
    ).all()
    return FilesPublic(data=[FilePublic.model_validate(f) for f in files], count=count)


@router.post("/{file_id}/confirm", response_model=FilePublic)
def confirm_upload(
    session: SessionDep,
    storage: StorageDep,
    current_user: CurrentUser,
    file_id: uuid.UUID,
) -> Any:
    """Verify the uploaded object (real size) and mark the file ready; 400 and delete otherwise."""
    file = _get_own_file(session, current_user, file_id, admin_ok=False)
    return file_service.confirm_upload(session=session, storage=storage, file=file)


@router.get("/{file_id}/download", response_model=DownloadUrl)
def get_download_url(
    session: SessionDep,
    storage: StorageDep,
    current_user: CurrentUser,
    file_id: uuid.UUID,
) -> Any:
    """Short-lived signed URL. Only images are shown inline; other types download."""
    file = _get_own_file(session, current_user, file_id, admin_ok=True)
    try:
        url = file_service.download_url(storage=storage, file=file)
    except StorageNotConfiguredError:
        raise HTTPException(status_code=503, detail="File storage is not configured")
    return DownloadUrl(url=url, expires_in=settings.DOWNLOAD_URL_EXPIRE_SECONDS)


@router.delete("/{file_id}", response_model=Message)
def delete_file(
    session: SessionDep,
    storage: StorageDep,
    current_user: CurrentUser,
    file_id: uuid.UUID,
) -> Any:
    """Delete a file (row and object). Owner or admin."""
    file = _get_own_file(session, current_user, file_id, admin_ok=True)
    file_service.delete_file(session=session, storage=storage, file=file)
    return Message(message="File deleted successfully")
