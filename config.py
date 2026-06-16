from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


DEFAULT_SECRET_KEY = "super_secret_key_please_change_in_production"


class Settings(BaseSettings):
    app_name: str = "CyberBooking System"
    environment: str = "development"
    database_url: str = "postgresql+asyncpg://postgres:12345678@localhost:5432/club"
    secret_key: str = DEFAULT_SECRET_KEY
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 10080  # 7 days
    cookie_secure: bool = False
    public_origin: str | None = None
    csrf_protection_enabled: bool = True
    csrf_trusted_origins: str = ""
    allowed_hosts: str = "*"
    allow_private_integration_hosts: bool = False
    auto_create_db_schema: bool = False
    enable_kaspi_test_payment: bool = False
    log_level: str = "INFO"
    log_json: bool = False
    sentry_dsn: str | None = None
    release: str | None = None
    superadmin_email: str | None = None
    superadmin_password: str | None = None

    # --- Business rules (вынесены из сервисов, настраиваются через env) ---
    kaspi_test_min_amount: int = 500
    kaspi_test_max_amount: int = 200_000
    max_review_comment_length: int = 1000
    max_booking_duration_minutes: int = 1440  # 24 часа
    history_page_size: int = 50
    notifications_page_size: int = 100

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"

    @model_validator(mode="after")
    def validate_production_settings(self):
        if not self.is_production:
            return self

        errors = []
        if self.secret_key == DEFAULT_SECRET_KEY or len(self.secret_key) < 32:
            errors.append("SECRET_KEY must be set to a unique value with at least 32 characters")
        if not self.cookie_secure:
            errors.append("COOKIE_SECURE must be true in production")
        if not self.public_origin:
            errors.append("PUBLIC_ORIGIN must be set in production")
        if self.allowed_hosts.strip() == "*":
            errors.append("ALLOWED_HOSTS must list explicit hosts in production")
        if self.auto_create_db_schema:
            errors.append("AUTO_CREATE_DB_SCHEMA must be false in production; use Alembic migrations")
        if self.enable_kaspi_test_payment:
            errors.append("ENABLE_KASPI_TEST_PAYMENT must be false in production")
        if self.superadmin_password and len(self.superadmin_password) < 12:
            errors.append("SUPERADMIN_PASSWORD must be at least 12 characters when set")

        if errors:
            raise ValueError("; ".join(errors))
        return self

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
