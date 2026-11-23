"""The community module as a module: enabling, disabling, dependency on content."""

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.config import Settings, settings
from app.main import create_app
from tests.modules.test_module_system import make_settings

COMMUNITY_PATHS = (
    "/community/posts/00000000-0000-0000-0000-000000000000/comments",
    "/community/pages/00000000-0000-0000-0000-000000000000/comments",
    "/community/posts/00000000-0000-0000-0000-000000000000/like",
    "/community/me/suspension",
    "/community/moderation/comments",
    "/community/moderation/suspensions",
)


def test_community_requires_content_with_a_clear_message() -> None:
    with pytest.raises(ValidationError) as exc_info:
        make_settings("items,community")
    message = str(exc_info.value)
    assert "community" in message
    assert "content" in message
    assert "MODULES=items,content,community" in message
    with pytest.raises(ValidationError):
        make_settings("community")
    assert make_settings("community,content").MODULES == ["community", "content"]


def test_community_without_content_fails_at_startup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MODULES", "community")
    with pytest.raises(ValidationError, match="requires module"):
        Settings()  # type: ignore[call-arg] # required fields come from env


def test_community_routes_are_404_when_the_module_is_off(
    superuser_token_headers: dict[str, str],
) -> None:
    app = create_app(make_settings("items,content"))
    with TestClient(app) as client:
        for path in COMMUNITY_PATHS:
            response = client.get(
                f"{settings.API_V1_STR}{path}", headers=superuser_token_headers
            )
            assert response.status_code == 404, path
        config = client.get(f"{settings.API_V1_STR}/utils/config").json()
    assert "community" not in config["modules"]
    assert not any(
        path.startswith(f"{settings.API_V1_STR}/community")
        for path in app.openapi()["paths"]
    )


def test_community_enabled_is_listed_in_the_config(cclient: TestClient) -> None:
    config = cclient.get(f"{settings.API_V1_STR}/utils/config").json()
    assert config["modules"] == ["items", "content", "community"]
    response = cclient.get(f"{settings.API_V1_STR}/community/moderation/comments")
    assert response.status_code == 401
