"""Domain events of the community module.

Task 015 (notifications) will make `emit` do something. Until then it is a no-op, but
the service already calls it at the right moments, always *after* the change was
committed, so a handler never sees a state that is rolled back.
"""

import uuid
from dataclasses import dataclass
from enum import StrEnum


class CommunityEventType(StrEnum):
    comment_replied = "comment_replied"  # recipient: author of the parent comment
    comment_liked = "comment_liked"  # recipient: author of the comment
    comment_hidden = "comment_hidden"  # recipient: author of the comment
    comment_deleted_by_moderator = "comment_deleted_by_moderator"  # same


@dataclass(frozen=True)
class CommunityEvent:
    type: CommunityEventType
    comment_id: uuid.UUID
    actor_id: uuid.UUID
    # Who should hear about it; None when the author no longer exists.
    recipient_id: uuid.UUID | None
    # "post" or "page", and the id of that post or page.
    target_type: str
    target_id: uuid.UUID


def emit(event: CommunityEvent) -> None:
    """Hook for notifications (015). Intentionally does nothing yet."""
    del event  # nothing listens yet
