import importlib.util
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import settings


def _load_main_without_frontend(monkeypatch: pytest.MonkeyPatch) -> FastAPI:
    """Import a fresh copy of app.main while pretending backend/app/frontend is absent."""
    original_is_dir = Path.is_dir

    def is_dir(self: Path) -> bool:
        if self.name == "frontend" and self.parent.name == "app":
            return False
        return original_is_dir(self)

    monkeypatch.setattr(Path, "is_dir", is_dir)

    import app.main as real_main

    assert real_main.__file__ is not None
    spec = importlib.util.spec_from_file_location(
        "app_main_without_frontend", real_main.__file__
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert isinstance(module.app, FastAPI)
    return module.app


def test_app_works_without_built_frontend(monkeypatch: pytest.MonkeyPatch) -> None:
    app = _load_main_without_frontend(monkeypatch)
    with TestClient(app) as client:
        r = client.get(f"{settings.API_V1_STR}/utils/health-check/")
        assert r.status_code == 200
        assert r.json() is True

        # No frontend mounted: unknown paths are a plain 404, not a 500.
        assert client.get("/").status_code == 404
