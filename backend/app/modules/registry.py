"""Explicit registry of available modules (no auto-discovery)."""

from app.modules import Module
from app.modules.content.public_routes import router as content_public_router
from app.modules.content.routes import router as content_router
from app.modules.items.routes import router as items_router

MODULES: dict[str, Module] = {
    module.name: module
    for module in (
        Module(name="items", router=items_router),
        Module(
            name="content", router=content_router, public_router=content_public_router
        ),
    )
}


def enabled_modules(names: list[str]) -> list[Module]:
    return [MODULES[name] for name in names]
