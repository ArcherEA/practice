"""Domain events of the community module.

`emit` turns events into in-app notifications (see `notifications.py`). The service calls
it at the right moments, always *after* the change was committed, so a handler never
sees a state that is rolled back.
"""

import logging
import uuid
from dataclasses import dataclass
from enum import StrEnum

logger = logging.getLogger(__name__)


class CommunityEventType(StrEnum):
    comment_replied = "comment_replied"  # recipient: author of the parent comment
    comment_liked = "comment_liked"  # recipient: author of the comment
    comment_hidden = "comment_hidden"  # recipient: author of the comment
    comment_deleted_by_moderator = "comment_deleted_by_moderator"  # same
    user_followed = "user_followed"  # recipient: the user who was followed


@dataclass(frozen=True)
class CommunityEvent:
    type: CommunityEventType
    actor_id: uuid.UUID
    # Who should hear about it; None when the author no longer exists.
    recipient_id: uuid.UUID | None
    # Not set for `user_followed`.
    comment_id: uuid.UUID | None = None
    # "post" or "page", and the id of that post or page.
    target_type: str | None = None
    target_id: uuid.UUID | None = None


def emit(event: CommunityEvent) -> None:
    """Create the notification for an event (own session; never raises).

    The change that caused the event is already committed, so a failure here must not
    turn a successful request into an error: it is logged instead.
    """
    from sqlmodel import Session

    from app.core.db import engine
    from app.modules.community import notifications

    try:
        with Session(engine) as session:
            notifications.handle_event(session, event)
    except Exception:  # noqa: BLE001 - see the docstring
        logger.exception("Could not create the notification for %s", event.type)
