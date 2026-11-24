import uuid
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError

from app import crud
from app.api.deps import SessionDep
from app.core.security import get_password_hash
from app.models import (
    User,
    UserPublic,
)

router = APIRouter(tags=["private"], prefix="/private")


class PrivateUserCreate(BaseModel):
    email: str
    password: str
    full_name: str
    is_verified: bool = False


@router.post("/users/", response_model=UserPublic)
def create_user(user_in: PrivateUserCreate, session: SessionDep) -> Any:
    """
    Create a new user.
    """

    # Parallel test workers create many users with the same name, so two requests can
    # pick the same free username at once: the loser retries (as crud.create_user does).
    user_id = uuid.uuid4()
    for _ in range(5):
        user = User(
            id=user_id,
            email=user_in.email,
            full_name=user_in.full_name,
            username=crud.generate_username(
                session=session, full_name=user_in.full_name, user_id=user_id
            ),
            hashed_password=get_password_hash(user_in.password),
        )
        session.add(user)
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            if crud.get_user_by_email(session=session, email=user_in.email):
                raise
            continue
        return user
    raise RuntimeError("Could not generate a free username")  # pragma: no cover
