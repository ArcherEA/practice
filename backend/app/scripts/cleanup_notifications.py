"""Delete community notifications older than 90 days.

Run from `backend/`:  uv run python -m app.scripts.cleanup_notifications
There is no scheduler; run it by hand or from any cron (see docs/DATABASE.md).
"""

import logging

from sqlmodel import Session

from app.core.db import engine
from app.modules.community.notifications import cleanup_old_notifications

logger = logging.getLogger(__name__)


def main() -> int:
    with Session(engine) as session:
        removed = cleanup_old_notifications(session=session)
    logger.info("Removed %d old notification(s)", removed)
    return removed


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
