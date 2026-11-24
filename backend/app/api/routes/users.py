import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, HTTPException
from sqlmodel import Session, col, func, select

from app import crud
from app.api.deps import (
    CurrentUser,
    RequireAdmin,
    SessionDep,
    StorageDep,
)
from app.core import files as file_service
from app.core.config import settings
from app.core.roles import UserRole, has_role
from app.core.security import get_password_hash, verify_password
from app.core.storage import delete_objects_quietly
from app.models import (
    AvatarSet,
    Message,
    UpdatePassword,
    User,
    UserCreate,
    UserPublic,
    UserRegister,
    UsersPublic,
    UserUpdate,
    UserUpdateMe,
    get_datetime_utc,
)
from app.utils import generate_new_account_email, send_email

router = APIRouter(prefix="/users", tags=["users"])

USERNAME_CHANGE_INTERVAL = timedelta(days=30)
USERNAME_TAKEN = "This username is already taken"


def _username_taken(session: Session, username: str, *, owner: uuid.UUID) -> bool:
    other = crud.get_user_by_username(session=session, username=username)
    return other is not None and other.id != owner


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def _forbidden(detail: str) -> HTTPException:
    return HTTPException(status_code=403, detail=detail)


def _check_can_create(actor: User, user_in: UserCreate) -> None:
    if actor.is_superuser:
        return
    if user_in.is_superuser:
        raise _forbidden("Only superusers can create superusers")
    if user_in.role == UserRole.admin:
        raise _forbidden("Only superusers can create admins")


def _check_can_update(actor: User, target: User, user_in: UserUpdate) -> None:
    changes_role = user_in.role is not None and user_in.role != target.role
    is_self = target.id == actor.id
    if changes_role and is_self:
        raise _forbidden("Users cannot change their own role")
    # Guard against locking yourself (possibly the last superuser) out.
    if (
        is_self
        and user_in.is_superuser is not None
        and user_in.is_superuser != target.is_superuser
    ):
        raise _forbidden("Users cannot change their own superuser flag")
    if is_self and user_in.is_active is False and target.is_active:
        raise _forbidden("Users cannot deactivate themselves")
    if actor.is_superuser:
        return
    if target.is_superuser:
        raise _forbidden("Only superusers can modify superusers")
    if target.role == UserRole.admin:
        raise _forbidden("Only superusers can modify admins")
    if user_in.is_superuser is not None and user_in.is_superuser != target.is_superuser:
        raise _forbidden("Only superusers can change the superuser flag")
    if changes_role and UserRole.admin in (user_in.role, target.role):
        raise _forbidden("Only superusers can grant or revoke the admin role")


@router.get(
    "/",
    dependencies=[RequireAdmin],
    response_model=UsersPublic,
)
def read_users(
    session: SessionDep, storage: StorageDep, skip: int = 0, limit: int = 100
) -> Any:
    """
    Retrieve users.
    """

    count_statement = select(func.count()).select_from(User)
    count = session.exec(count_statement).one()

    statement = (
        select(User).order_by(col(User.created_at).desc()).offset(skip).limit(limit)
    )
    users = session.exec(statement).all()

    users_public = file_service.to_users_public(
        session=session, storage=storage, users=users
    )
    return UsersPublic(data=users_public, count=count)


@router.post("/", dependencies=[RequireAdmin], response_model=UserPublic)
def create_user(
    *, session: SessionDep, current_user: CurrentUser, user_in: UserCreate
) -> Any:
    """
    Create new user. Admins and superusers only; only superusers may create admins
    or superusers.
    """
    _check_can_create(current_user, user_in)
    user = crud.get_user_by_email(session=session, email=user_in.email)
    if user:
        raise HTTPException(
            status_code=400,
            detail="The user with this email already exists in the system.",
        )
    if user_in.username and crud.get_user_by_username(
        session=session, username=user_in.username
    ):
        raise HTTPException(status_code=400, detail=USERNAME_TAKEN)

    user = crud.create_user(session=session, user_create=user_in)
    if settings.emails_enabled and user_in.email:
        email_data = generate_new_account_email(
            email_to=user_in.email, username=user_in.email, password=user_in.password
        )
        send_email(
            email_to=user_in.email,
            subject=email_data.subject,
            html_content=email_data.html_content,
        )
    return user


@router.patch("/me", response_model=UserPublic)
def update_user_me(
    *,
    session: SessionDep,
    storage: StorageDep,
    user_in: UserUpdateMe,
    current_user: CurrentUser,
) -> Any:
    """
    Update own user.
    """

    if user_in.email:
        existing_user = crud.get_user_by_email(session=session, email=user_in.email)
        if existing_user and existing_user.id != current_user.id:
            raise HTTPException(
                status_code=409, detail="User with this email already exists"
            )
    user_data = user_in.model_dump(exclude_unset=True)
    new_username = user_data.pop("username", None)
    if new_username is not None and new_username != current_user.username:
        last = current_user.username_changed_at
        if (
            last is not None
            and _utc(last) + USERNAME_CHANGE_INTERVAL > get_datetime_utc()
        ):
            next_change = (_utc(last) + USERNAME_CHANGE_INTERVAL).date().isoformat()
            raise HTTPException(
                status_code=400,
                detail=(
                    "You can change your username once every 30 days; "
                    f"you can change it again on {next_change}"
                ),
            )
        if _username_taken(session, new_username, owner=current_user.id):
            raise HTTPException(status_code=409, detail=USERNAME_TAKEN)
        user_data["username"] = new_username
        user_data["username_changed_at"] = get_datetime_utc()
    current_user.sqlmodel_update(user_data)
    session.add(current_user)
    session.commit()
    session.refresh(current_user)
    return file_service.to_user_public(
        session=session, storage=storage, user=current_user
    )


@router.put("/me/avatar", response_model=UserPublic)
def set_avatar_me(
    *,
    session: SessionDep,
    storage: StorageDep,
    current_user: CurrentUser,
    body: AvatarSet,
) -> Any:
    """
    Use one of my confirmed image files (JPEG, PNG, WebP, GIF) as my avatar.
    The previous avatar file is deleted (row and object).
    """
    file_service.set_avatar(
        session=session, storage=storage, user=current_user, file_id=body.file_id
    )
    session.refresh(current_user)
    return file_service.to_user_public(
        session=session, storage=storage, user=current_user
    )


@router.delete("/me/avatar", response_model=UserPublic)
def delete_avatar_me(
    session: SessionDep, storage: StorageDep, current_user: CurrentUser
) -> Any:
    """
    Remove my avatar and delete its file.
    """
    file_service.clear_avatar(session=session, storage=storage, user=current_user)
    session.refresh(current_user)
    return file_service.to_user_public(
        session=session, storage=storage, user=current_user
    )


@router.patch("/me/password", response_model=Message)
def update_password_me(
    *, session: SessionDep, body: UpdatePassword, current_user: CurrentUser
) -> Any:
    """
    Update own password.
    """
    verified, _ = verify_password(body.current_password, current_user.hashed_password)
    if not verified:
        raise HTTPException(status_code=400, detail="Incorrect password")
    if body.current_password == body.new_password:
        raise HTTPException(
            status_code=400, detail="New password cannot be the same as the current one"
        )
    hashed_password = get_password_hash(body.new_password)
    current_user.hashed_password = hashed_password
    session.add(current_user)
    session.commit()
    return Message(message="Password updated successfully")


@router.get("/me", response_model=UserPublic)
def read_user_me(
    session: SessionDep, storage: StorageDep, current_user: CurrentUser
) -> Any:
    """
    Get current user.
    """
    return file_service.to_user_public(
        session=session, storage=storage, user=current_user
    )


@router.delete("/me", response_model=Message)
def delete_user_me(
    session: SessionDep, storage: StorageDep, current_user: CurrentUser
) -> Any:
    """
    Delete own user.
    """
    if current_user.is_superuser:
        raise HTTPException(
            status_code=403, detail="Super users are not allowed to delete themselves"
        )
    file_service.ensure_user_deletable(session, current_user.id)
    keys = file_service.user_object_keys(session=session, user_id=current_user.id)
    session.delete(current_user)
    session.commit()
    delete_objects_quietly(storage, keys)
    return Message(message="User deleted successfully")


@router.post("/signup", response_model=UserPublic)
def register_user(session: SessionDep, user_in: UserRegister) -> Any:
    """
    Create new user without the need to be logged in.
    """
    user = crud.get_user_by_email(session=session, email=user_in.email)
    if user:
        raise HTTPException(
            status_code=400,
            detail="The user with this email already exists in the system",
        )
    if user_in.username and crud.get_user_by_username(
        session=session, username=user_in.username
    ):
        raise HTTPException(status_code=400, detail=USERNAME_TAKEN)
    user_create = UserCreate.model_validate(user_in)
    user = crud.create_user(session=session, user_create=user_create)
    return user


@router.get("/{user_id}", response_model=UserPublic)
def read_user_by_id(
    user_id: uuid.UUID,
    session: SessionDep,
    storage: StorageDep,
    current_user: CurrentUser,
) -> Any:
    """
    Get a specific user by id.
    """
    user = session.get(User, user_id)
    if user == current_user:
        return file_service.to_user_public(session=session, storage=storage, user=user)
    if not has_role(current_user, UserRole.admin):
        raise HTTPException(
            status_code=403,
            detail="The user doesn't have enough privileges",
        )
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return file_service.to_user_public(session=session, storage=storage, user=user)


@router.patch(
    "/{user_id}",
    dependencies=[RequireAdmin],
    response_model=UserPublic,
)
def update_user(
    *,
    session: SessionDep,
    storage: StorageDep,
    current_user: CurrentUser,
    user_id: uuid.UUID,
    user_in: UserUpdate,
) -> Any:
    """
    Update a user. Only superusers can modify admins or superusers, grant/revoke
    admin or set the superuser flag; nobody can change their own role.
    """

    db_user = session.get(User, user_id)
    if not db_user:
        raise HTTPException(
            status_code=404,
            detail="The user with this id does not exist in the system",
        )
    _check_can_update(current_user, db_user, user_in)
    if user_in.email:
        existing_user = crud.get_user_by_email(session=session, email=user_in.email)
        if existing_user and existing_user.id != user_id:
            raise HTTPException(
                status_code=409, detail="User with this email already exists"
            )
    if user_in.username and _username_taken(session, user_in.username, owner=user_id):
        raise HTTPException(status_code=409, detail=USERNAME_TAKEN)

    db_user = crud.update_user(session=session, db_user=db_user, user_in=user_in)
    return file_service.to_user_public(session=session, storage=storage, user=db_user)


@router.delete("/{user_id}", dependencies=[RequireAdmin])
def delete_user(
    session: SessionDep,
    storage: StorageDep,
    current_user: CurrentUser,
    user_id: uuid.UUID,
) -> Message:
    """
    Delete a user.
    """
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user == current_user:
        raise HTTPException(
            status_code=403, detail="Super users are not allowed to delete themselves"
        )
    if user.is_superuser and not current_user.is_superuser:
        raise _forbidden("Only superusers can delete superusers")
    if user.role == UserRole.admin and not current_user.is_superuser:
        raise _forbidden("Only superusers can delete admins")
    # Module-owned rows (e.g. items) go via the ORM cascade / FK ON DELETE CASCADE.
    file_service.ensure_user_deletable(session, user.id)
    keys = file_service.user_object_keys(session=session, user_id=user.id)
    session.delete(user)
    session.commit()
    delete_objects_quietly(storage, keys)
    return Message(message="User deleted successfully")
