from fastapi import APIRouter, Depends, Request
from pydantic.networks import EmailStr
from sqlmodel import SQLModel

from app.api.deps import get_current_active_superuser
from app.core.config import Settings
from app.models import Message
from app.utils import generate_test_email, send_email

router = APIRouter(prefix="/utils", tags=["utils"])


class PublicConfig(SQLModel):
    project_name: str
    modules: list[str]


@router.get("/config")
def get_public_config(request: Request) -> PublicConfig:
    """
    Public (no auth) deployment config for the frontend: name and enabled modules.
    """
    app_settings: Settings = request.app.state.settings
    return PublicConfig(
        project_name=app_settings.PROJECT_NAME, modules=app_settings.MODULES
    )


@router.post(
    "/test-email/",
    dependencies=[Depends(get_current_active_superuser)],
    status_code=201,
)
def test_email(email_to: EmailStr) -> Message:
    """
    Test emails.
    """
    email_data = generate_test_email(email_to=email_to)
    send_email(
        email_to=email_to,
        subject=email_data.subject,
        html_content=email_data.html_content,
    )
    return Message(message="Test email sent")


@router.get("/health-check/")
async def health_check() -> bool:
    return True
