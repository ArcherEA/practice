"""File service: upload reservations, limits, confirm, download URLs, avatars, cleanup.

Routes stay thin and call these functions. Errors are raised as `HTTPException`
(same style as the rest of the API).
"""

import logging
import uuid
from collections.abc import Sequence
from datetime import timedelta
from typing import NoReturn

from fastapi import HTTPException
from sqlalchemy import text
from sqlmodel import Session, col, func, select

from app.core.config import settings
from app.core.storage import (
    Storage,
    StorageNotConfiguredError,
    delete_objects_quietly,
    is_inline_content_type,
)
from app.models import (
    File,
    FileCreate,
    FilePublic,
    FileStatus,
    StorageUsage,
    UploadTicket,
    User,
    UserPublic,
    UserUsage,
    get_datetime_utc,
)

logger = logging.getLogger(__name__)

PENDING_MAX_AGE = timedelta(hours=24)
DAILY_WINDOW = timedelta(hours=24)
# Serialises create-upload so parallel requests can't overshoot the limits.
_UPLOAD_LOCK_ID = 60060001


def _used_bytes(session: Session, owner_id: uuid.UUID | None = None) -> int:
    """Bytes of ready + pending files (pending ones are reservations)."""
    statement = select(func.coalesce(func.sum(File.size), 0))
    if owner_id is not None:
        statement = statement.where(File.owner_id == owner_id)
    return int(session.exec(statement).one())


def create_upload(
    *, session: Session, storage: Storage, user: User, data: FileCreate
) -> UploadTicket:
    if data.size > settings.UPLOAD_MAX_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File is too large (max {settings.UPLOAD_MAX_BYTES} bytes)",
        )
    if data.public and not is_inline_content_type(data.content_type):
        raise HTTPException(
            status_code=400, detail="Only JPEG, PNG, WebP and GIF images can be public"
        )

    session.execute(text("SELECT pg_advisory_xact_lock(:id)"), {"id": _UPLOAD_LOCK_ID})
    if not user.is_superuser:
        since = get_datetime_utc() - DAILY_WINDOW
        recent = session.exec(
            select(func.count())
            .select_from(File)
            .where(File.owner_id == user.id, File.created_at >= since)
        ).one()
        if recent >= settings.UPLOADS_PER_USER_PER_DAY:
            raise HTTPException(
                status_code=429, detail="Daily upload limit reached, try again later"
            )
        if (
            _used_bytes(session, user.id) + data.size
            > settings.STORAGE_USER_QUOTA_BYTES
        ):
            raise HTTPException(status_code=413, detail="Your storage quota is full")
    if _used_bytes(session) + data.size > settings.STORAGE_TOTAL_LIMIT_BYTES:
        raise HTTPException(status_code=507, detail="Storage is full")

    file_id = uuid.uuid4()
    file = File(
        id=file_id,
        owner_id=user.id,
        key=f"{user.id}/{file_id}",
        filename=data.filename,
        content_type=data.content_type,
        size=data.size,
        public=data.public,
        status=FileStatus.pending,
    )
    session.add(file)
    session.commit()  # also releases the advisory lock
    session.refresh(file)
    try:
        presigned = storage.presign_upload(
            file.key,
            content_type=file.content_type,
            size=file.size,
            expires_in=settings.UPLOAD_URL_EXPIRE_SECONDS,
        )
    except StorageNotConfiguredError:
        session.delete(file)
        session.commit()
        raise HTTPException(status_code=503, detail="File storage is not configured")
    return UploadTicket(
        file=FilePublic.model_validate(file),
        upload_url=presigned.url,
        upload_headers=presigned.headers,
        expires_in=settings.UPLOAD_URL_EXPIRE_SECONDS,
    )


def _reject(session: Session, storage: Storage, file: File, detail: str) -> NoReturn:
    key = file.key
    session.delete(file)
    session.commit()
    delete_objects_quietly(storage, [key])
    raise HTTPException(status_code=400, detail=detail)


def confirm_upload(*, session: Session, storage: Storage, file: File) -> File:
    if file.status == FileStatus.ready:
        return file
    try:
        info = storage.head(file.key)
    except StorageNotConfiguredError:
        raise HTTPException(status_code=503, detail="File storage is not configured")
    if info is None:
        _reject(session, storage, file, "Upload not found; start again")
    elif info.size > settings.UPLOAD_MAX_BYTES:
        _reject(session, storage, file, "File is too large")
    elif info.size != file.size:
        _reject(
            session, storage, file, "Uploaded size does not match the declared size"
        )
    file.status = FileStatus.ready
    session.add(file)
    session.commit()
    session.refresh(file)
    return file


def download_url(*, storage: Storage, file: File) -> str:
    if file.status != FileStatus.ready:
        raise HTTPException(status_code=409, detail="File is not ready")
    return storage.presign_download(
        file.key,
        filename=file.filename,
        content_type=file.content_type,
        expires_in=settings.DOWNLOAD_URL_EXPIRE_SECONDS,
    )


def delete_file(*, session: Session, storage: Storage, file: File) -> None:
    key = file.key
    session.delete(file)
    session.commit()
    delete_objects_quietly(storage, [key])


def storage_usage(*, session: Session) -> StorageUsage:
    count = session.exec(select(func.count()).select_from(File)).one()
    rows = session.exec(
        select(
            User.id,
            User.email,
            func.sum(File.size).label("bytes"),
            func.count().label("n"),
        )
        .join(File, col(File.owner_id) == col(User.id))
        .group_by(col(User.id), col(User.email))
        .order_by(func.sum(File.size).desc())
        .limit(10)
    ).all()
    return StorageUsage(
        total_bytes=_used_bytes(session),
        limit_bytes=settings.STORAGE_TOTAL_LIMIT_BYTES,
        file_count=count,
        top_users=[
            UserUsage(
                user_id=uid, email=str(email), total_bytes=int(total), file_count=n
            )
            for uid, email, total, n in rows
        ],
    )


# --- avatars ---


def set_avatar(
    *, session: Session, storage: Storage, user: User, file_id: uuid.UUID
) -> None:
    file = session.get(File, file_id)
    if file is None or file.owner_id != user.id:
        raise HTTPException(status_code=404, detail="File not found")
    if file.status != FileStatus.ready:
        raise HTTPException(status_code=400, detail="File upload is not confirmed")
    if not is_inline_content_type(file.content_type):
        raise HTTPException(
            status_code=400, detail="Avatar must be a JPEG, PNG, WebP or GIF image"
        )
    old_id = user.avatar_file_id
    if old_id == file.id:
        return
    user.avatar_file_id = file.id
    session.add(user)
    session.commit()
    if old_id is not None:
        _delete_by_id(session=session, storage=storage, file_id=old_id)


def clear_avatar(*, session: Session, storage: Storage, user: User) -> None:
    old_id = user.avatar_file_id
    if old_id is None:
        return
    user.avatar_file_id = None
    session.add(user)
    session.commit()
    _delete_by_id(session=session, storage=storage, file_id=old_id)


def _delete_by_id(*, session: Session, storage: Storage, file_id: uuid.UUID) -> None:
    old = session.get(File, file_id)
    if old is not None:
        delete_file(session=session, storage=storage, file=old)


def to_users_public(
    *, session: Session, storage: Storage, users: Sequence[User]
) -> list[UserPublic]:
    """UserPublic for each user, with `avatar_url` (one query for all avatars)."""
    ids = [u.avatar_file_id for u in users if u.avatar_file_id is not None]
    files: dict[uuid.UUID, File] = {}
    if ids:
        files = {
            f.id: f for f in session.exec(select(File).where(col(File.id).in_(ids)))
        }
    result: list[UserPublic] = []
    for user in users:
        public = UserPublic.model_validate(user)
        avatar = files.get(user.avatar_file_id) if user.avatar_file_id else None
        if avatar is not None and avatar.status == FileStatus.ready:
            public.avatar_url = _avatar_url(storage, avatar)
        result.append(public)
    return result


def to_user_public(*, session: Session, storage: Storage, user: User) -> UserPublic:
    return to_users_public(session=session, storage=storage, users=[user])[0]


def _avatar_url(storage: Storage, file: File) -> str | None:
    try:
        if file.public and (url := storage.public_url(file.key)):
            return url
        # Local signing, no network call, so it is cheap even for long lists.
        return storage.presign_download(
            file.key,
            filename=file.filename,
            content_type=file.content_type,
            expires_in=settings.DOWNLOAD_URL_EXPIRE_SECONDS,
        )
    except StorageNotConfiguredError:
        return None


# --- cleanup and user deletion ---


def user_object_keys(*, session: Session, user_id: uuid.UUID) -> list[str]:
    """Collect before deleting a user (their rows vanish via ON DELETE CASCADE)."""
    return list(session.exec(select(File.key).where(File.owner_id == user_id)).all())


def cleanup_stale_pending(*, session: Session, storage: Storage) -> int:
    """Remove pending files older than 24h (object + row). Returns how many."""
    cutoff = get_datetime_utc() - PENDING_MAX_AGE
    stale = session.exec(
        select(File).where(File.status == FileStatus.pending, File.created_at < cutoff)
    ).all()
    for file in stale:
        delete_file(session=session, storage=storage, file=file)
    return len(stale)
