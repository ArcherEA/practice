from fastapi import APIRouter

from app.api.routes import login, private, users, utils
from app.core.config import Settings
from app.modules.registry import enabled_modules


def create_api_router(settings: Settings) -> APIRouter:
    """Core routers always; module routers only for modules enabled in settings."""
    api_router = APIRouter()
    api_router.include_router(login.router)
    api_router.include_router(users.router)
    api_router.include_router(utils.router)
    for module in enabled_modules(settings.MODULES):
        api_router.include_router(module.router)

    if settings.FASTAPI_ENV == "development":
        api_router.include_router(private.router)
    return api_router
