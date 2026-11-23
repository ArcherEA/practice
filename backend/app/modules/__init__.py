"""Optional feature modules.

Each module lives in ``app/modules/<name>/`` (models, crud, routes, tests) and is
switched on per deployment with the ``MODULES`` env var (see docs/ARCHITECTURE.md).

This file stays import-light on purpose: ``app.core.config`` imports it to validate
module names, so it must not import settings, models or routes. The router registry
lives in ``app.modules.registry``.
"""

from dataclasses import dataclass

from fastapi import APIRouter

# Every module that exists in the codebase. Keep in sync with registry.MODULES
# (a test enforces it).
MODULE_NAMES: tuple[str, ...] = ("items",)

# Setting value that disables all optional modules (an empty env var is ignored).
NO_MODULES = "none"
# Enabled when MODULES is not set, so existing deployments keep working.
DEFAULT_MODULES: tuple[str, ...] = ("items",)


@dataclass(frozen=True)
class Module:
    name: str
    router: APIRouter
