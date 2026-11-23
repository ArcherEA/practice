import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.config import Settings, settings
from app.main import create_app
from app.modules import DEFAULT_MODULES, MODULE_NAMES
from app.modules.registry import MODULES


def make_settings(modules: str) -> Settings:
    # The validator accepts the env format (comma-separated str) as well as a list.
    overrides: dict[str, str] = {"MODULES": modules}
    return Settings(**overrides)  # type: ignore[arg-type] # str is parsed by the validator


def test_registry_matches_module_names() -> None:
    assert set(MODULES) == set(MODULE_NAMES)
    assert set(DEFAULT_MODULES) <= set(MODULE_NAMES)


def test_default_modules(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MODULES", raising=False)
    settings_from_env = Settings()  # type: ignore[call-arg] # required fields come from env
    assert settings_from_env.MODULES == list(DEFAULT_MODULES)


def test_modules_parsed_from_comma_separated_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MODULES", " items , items ")
    settings_from_env = Settings()  # type: ignore[call-arg] # required fields come from env
    assert settings_from_env.MODULES == ["items"]


def test_modules_none_disables_all() -> None:
    assert make_settings("none").MODULES == []


def test_unknown_module_fails_validation() -> None:
    with pytest.raises(ValidationError) as exc_info:
        make_settings("items,bogus")
    message = str(exc_info.value)
    assert "bogus" in message
    for name in MODULE_NAMES:
        assert name in message


def test_items_enabled_exposes_items_api_and_config(
    superuser_token_headers: dict[str, str],
) -> None:
    app = create_app(make_settings("items"))
    with TestClient(app) as client:
        response = client.get(
            f"{settings.API_V1_STR}/items/", headers=superuser_token_headers
        )
        assert response.status_code == 200
        config = client.get(f"{settings.API_V1_STR}/utils/config").json()
    assert config == {"project_name": settings.PROJECT_NAME, "modules": ["items"]}


def test_modules_none_hides_items_but_core_works(
    superuser_token_headers: dict[str, str],
) -> None:
    app = create_app(make_settings("none"))
    with TestClient(app) as client:
        response = client.get(
            f"{settings.API_V1_STR}/items/", headers=superuser_token_headers
        )
        assert response.status_code == 404
        me = client.get(
            f"{settings.API_V1_STR}/users/me", headers=superuser_token_headers
        )
        assert me.status_code == 200
        health = client.get(f"{settings.API_V1_STR}/utils/health-check/")
        assert health.status_code == 200
        config = client.get(f"{settings.API_V1_STR}/utils/config").json()
    assert config == {"project_name": settings.PROJECT_NAME, "modules": []}
    assert not any("/items" in path for path in app.openapi()["paths"])
