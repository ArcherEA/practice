import uuid
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.core.security import get_password_hash, verify_password
from app.core.usernames import base_username, pick_username
from app.models import User, UserCreate, UserUpdate


def get_user_by_username(*, session: Session, username: str) -> User | None:
    """Case-insensitive (usernames are stored lowercase)."""
    return session.exec(select(User).where(User.username == username.lower())).first()


def generate_username(
    *, session: Session, full_name: str | None, user_id: uuid.UUID
) -> str:
    """A free username from the name, else `member_<id>` (`name`, `name_2`, ...)."""
    return pick_username(
        base_username(full_name, user_id),
        lambda name: get_user_by_username(session=session, username=name) is not None,
    )


def create_user(*, session: Session, user_create: UserCreate) -> User:
    """Create a user. A missing username is generated; a taken one raises IntegrityError."""
    extra = {"hashed_password": get_password_hash(user_create.password)}
    if user_create.username is not None:
        db_obj = User.model_validate(user_create, update=extra)
        session.add(db_obj)
        session.commit()
        session.refresh(db_obj)
        return db_obj
    # Two requests may pick the same free name at once: the loser retries.
    user_id = uuid.uuid4()
    for _ in range(5):
        username = generate_username(
            session=session, full_name=user_create.full_name, user_id=user_id
        )
        db_obj = User.model_validate(
            user_create, update={**extra, "id": user_id, "username": username}
        )
        session.add(db_obj)
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            if get_user_by_email(session=session, email=user_create.email):
                raise
            continue
        session.refresh(db_obj)
        return db_obj
    raise RuntimeError("Could not generate a free username")  # pragma: no cover


def update_user(*, session: Session, db_user: User, user_in: UserUpdate) -> Any:
    user_data = user_in.model_dump(exclude_unset=True)
    if user_data.get("username") is None:
        user_data.pop("username", None)  # the column is NOT NULL: null means "keep"
    extra_data = {}
    if "password" in user_data:
        password = user_data["password"]
        hashed_password = get_password_hash(password)
        extra_data["hashed_password"] = hashed_password
    db_user.sqlmodel_update(user_data, update=extra_data)
    session.add(db_user)
    session.commit()
    session.refresh(db_user)
    return db_user


def get_user_by_email(*, session: Session, email: str) -> User | None:
    statement = select(User).where(User.email == email)
    session_user = session.exec(statement).first()
    return session_user


# Dummy hash to use for timing attack prevention when user is not found
# This is an Argon2 hash of a random password, used to ensure constant-time comparison
DUMMY_HASH = "$argon2id$v=19$m=65536,t=3,p=4$MjQyZWE1MzBjYjJlZTI0Yw$YTU4NGM5ZTZmYjE2NzZlZjY0ZWY3ZGRkY2U2OWFjNjk"


def authenticate(*, session: Session, email: str, password: str) -> User | None:
    db_user = get_user_by_email(session=session, email=email)
    if not db_user:
        # Prevent timing attacks by running password verification even when user doesn't exist
        # This ensures the response time is similar whether or not the email exists
        verify_password(password, DUMMY_HASH)
        return None
    verified, updated_password_hash = verify_password(password, db_user.hashed_password)
    if not verified:
        return None
    if updated_password_hash:
        db_user.hashed_password = updated_password_hash
        session.add(db_user)
        session.commit()
        session.refresh(db_user)
    return db_user
