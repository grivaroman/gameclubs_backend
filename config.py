from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    app_name: str = "CyberBooking System"
    database_url: str = "postgresql+asyncpg://postgres:12345678@localhost:5432/club"
    secret_key: str = "super_secret_key_please_change_in_production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 10080  # 7 days

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

settings = Settings()
