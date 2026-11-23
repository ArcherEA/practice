from pathlib import Path

import sentry_sdk
from fastapi import FastAPI
from fastapi.routing import APIRoute
from starlette.middleware.cors import CORSMiddleware

from app.api.main import create_api_router
from app.core.config import Settings, settings

FRONTEND_DIR = Path(__file__).parent / "frontend"


def custom_generate_unique_id(route: APIRoute) -> str:
    return f"{route.tags[0]}-{route.name}"


if settings.SENTRY_DSN and settings.FASTAPI_ENV != "development":
    sentry_sdk.init(dsn=str(settings.SENTRY_DSN), enable_tracing=True)


def create_app(app_settings: Settings = settings) -> FastAPI:
    """Build the FastAPI app. Enabled modules come from ``app_settings.MODULES``."""
    application = FastAPI(
        title=app_settings.PROJECT_NAME,
        openapi_url=f"{app_settings.API_V1_STR}/openapi.json",
        generate_unique_id_function=custom_generate_unique_id,
    )
    application.state.settings = app_settings

    application.add_middleware(
        CORSMiddleware,
        allow_origins=[app_settings.FRONTEND_HOST],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    application.include_router(
        create_api_router(app_settings), prefix=app_settings.API_V1_STR
    )
    # Serve the built SPA only when a build exists. On Vercel the CDN serves the
    # static files and in development Vite serves them, so a missing folder is fine.
    if FRONTEND_DIR.is_dir():
        application.frontend("/", directory=FRONTEND_DIR)
    return application


app = create_app()
