"""Remove pending uploads older than 24h (object + row).

Run from `backend/`:  uv run python -m app.scripts.cleanup_files
There is no scheduler; run it by hand or from any cron (see docs/ARCHITECTURE.md).
"""

import logging

from sqlmodel import Session

from app.core.db import engine
from app.core.files import cleanup_stale_pending
from app.core.storage import get_storage

logger = logging.getLogger(__name__)


def main() -> int:
    with Session(engine) as session:
        removed = cleanup_stale_pending(session=session, storage=get_storage())
    logger.info("Removed %d stale pending upload(s)", removed)
    return removed


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
