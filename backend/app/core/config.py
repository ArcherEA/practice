import warnings
from typing import Annotated, Literal, Self

from pydantic import (
    EmailStr,
    HttpUrl,
    PostgresDsn,
    computed_field,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from app.modules import (
    DEFAULT_MODULES,
    MODULE_DEPENDENCIES,
    MODULE_NAMES,
    NO_MODULES,
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # Use top level .env file (one level above ./backend/)
        env_file="../.env",
        env_ignore_empty=True,
        extra="ignore",
    )
    API_V1_STR: str = "/api/v1"
    SECRET_KEY: str
    # 60 minutes * 24 hours * 8 days = 8 days
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 8
    FRONTEND_HOST: str = "http://localhost:5173"
    # Public base URL of the site (no trailing slash): canonical links, og:url,
    # sitemap.xml and robots.txt. Production URL on Vercel / own server.
    SITE_URL: str = "http://localhost:5173"
    FASTAPI_ENV: Literal["development"] | None = None

    PROJECT_NAME: str
    # Optional modules to enable, comma-separated (MODULES=items,content).
    # Not set -> DEFAULT_MODULES. An empty value is ignored (env_ignore_empty),
    # so use MODULES=none to run with Core only.
    MODULES: Annotated[list[str], NoDecode] = list(DEFAULT_MODULES)
    SENTRY_DSN: HttpUrl | None = None
    DATABASE_URL: PostgresDsn

    @field_validator("MODULES", mode="before")
    @classmethod
    def _parse_modules(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            names = [name.strip() for name in value.split(",")]
        else:
            names = [name.strip() for name in value]
        names = [name for name in names if name]
        if names == [NO_MODULES]:
            return []
        unknown = [name for name in names if name not in MODULE_NAMES]
        if unknown:
            raise ValueError(
                f"Unknown module(s) in MODULES: {', '.join(unknown)}. "
                f"Valid names: {', '.join(MODULE_NAMES)} "
                f"(or '{NO_MODULES}' to disable all optional modules)."
            )
        names = list(dict.fromkeys(names))
        for name in names:
            missing = [
                dep for dep in MODULE_DEPENDENCIES.get(name, ()) if dep not in names
            ]
            if missing:
                raise ValueError(
                    f"Module '{name}' requires module(s) {', '.join(missing)} "
                    f"to be enabled too. Add them to MODULES "
                    f"(e.g. MODULES=items,{','.join(missing)},{name})."
                )
        return names

    @field_validator("SITE_URL")
    @classmethod
    def _strip_trailing_slash(cls, value: str) -> str:
        return value.rstrip("/")

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def _use_psycopg_driver(cls, value: str | PostgresDsn) -> str:
        database_url = str(value)
        for scheme in ("postgres://", "postgresql://"):
            if database_url.startswith(scheme):
                return database_url.replace(scheme, "postgresql+psycopg://", 1)
        return database_url

    # --- File storage (any S3-compatible server: SeaweedFS locally, R2 on Vercel) ---
    S3_ENDPOINT_URL: str | None = None
    # Hostname the *browser* uses for presigned URLs. Defaults to S3_ENDPOINT_URL;
    # set it when the backend reaches the bucket through an internal hostname.
    S3_PUBLIC_ENDPOINT_URL: str | None = None
    S3_REGION: str = "auto"
    S3_ACCESS_KEY_ID: str | None = None
    S3_SECRET_ACCESS_KEY: str | None = None
    S3_BUCKET: str | None = None
    # Optional permanent public URL prefix (e.g. an R2 public bucket / custom domain).
    S3_PUBLIC_BASE_URL: str | None = None
    UPLOAD_URL_EXPIRE_SECONDS: int = 900
    DOWNLOAD_URL_EXPIRE_SECONDS: int = 3600
    # Usage limits (R2 has no hard spending cap, so the app enforces its own).
    UPLOAD_MAX_BYTES: int = 10 * 1024**2
    STORAGE_TOTAL_LIMIT_BYTES: int = 8 * 1024**3
    STORAGE_USER_QUOTA_BYTES: int = 100 * 1024**2
    UPLOADS_PER_USER_PER_DAY: int = 50

    # Community limits (database counts, superusers are exempt) -> HTTP 429.
    COMMENTS_PER_USER_PER_HOUR: int = 30
    REPORTS_PER_USER_PER_DAY: int = 20

    SMTP_TLS: bool = True
    SMTP_SSL: bool = False
    SMTP_PORT: int = 587
    SMTP_HOST: str | None = None
    SMTP_USER: str | None = None
    SMTP_PASSWORD: str | None = None
    EMAILS_FROM_EMAIL: EmailStr | None = None
    EMAILS_FROM_NAME: str | None = None

    @model_validator(mode="after")
    def _set_default_emails_from(self) -> Self:
        if not self.EMAILS_FROM_NAME:
            self.EMAILS_FROM_NAME = self.PROJECT_NAME
        return self

    EMAIL_RESET_TOKEN_EXPIRE_HOURS: int = 48

    @computed_field  # type: ignore[prop-decorator]
    @property
    def emails_enabled(self) -> bool:
        return bool(self.SMTP_HOST and self.EMAILS_FROM_EMAIL)

    EMAIL_TEST_USER: EmailStr = "test@example.com"
    FIRST_SUPERUSER: EmailStr
    FIRST_SUPERUSER_PASSWORD: str

    def _check_default_secret(self, var_name: str, value: str | None) -> None:
        if value == "changethis":
            message = (
                f'The value of {var_name} is "changethis", '
                "for security, please change it, at least for deployments."
            )
            if self.FASTAPI_ENV == "development":
                warnings.warn(message, stacklevel=1)
            else:
                raise ValueError(message)

    @model_validator(mode="after")
    def _enforce_non_default_secrets(self) -> Self:
        self._check_default_secret("SECRET_KEY", self.SECRET_KEY)
        for host in self.DATABASE_URL.hosts():
            self._check_default_secret("DATABASE_URL password", host["password"])
        self._check_default_secret(
            "FIRST_SUPERUSER_PASSWORD", self.FIRST_SUPERUSER_PASSWORD
        )

        return self


settings = Settings()  # type: ignore # ty: ignore[unused-ignore-comment]
