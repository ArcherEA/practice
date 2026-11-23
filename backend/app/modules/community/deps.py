"""Optional authentication for public community reads."""

from typing import Annotated

import jwt
from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from jwt.exceptions import InvalidTokenError
from pydantic import ValidationError

from app.api.deps import SessionDep
from app.core import security
from app.core.config import settings
from app.models import TokenPayload, User

_optional_oauth2 = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_V1_STR}/login/access-token", auto_error=False
)


def get_optional_user(
    session: SessionDep, token: Annotated[str | None, Depends(_optional_oauth2)]
) -> User | None:
    """The logged-in user, or None for anonymous visitors and unusable tokens.

    Public lists use this only to add `liked_by_me`; they never fail because of a
    stale token.
    """
    if token is None:
        return None
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[security.ALGORITHM]
        )
        token_data = TokenPayload(**payload)
    except InvalidTokenError, ValidationError:
        return None
    user = session.get(User, token_data.sub)
    return user if user is not None and user.is_active else None


OptionalUser = Annotated[User | None, Depends(get_optional_user)]
