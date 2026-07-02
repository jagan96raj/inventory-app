from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "postgresql+psycopg://inventory:inventory@localhost:5432/inventory"
    # Database connection pool (Spec v16.0.4).
    db_pool_size: int = 5
    db_max_overflow: int = 10
    db_pool_timeout: int = 30
    db_pool_recycle: int = 1800
    google_client_id: str = ""
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_hours: int = 24
    cookie_secure: bool = False
    allowed_emails: str = ""
    require_allowed_emails: bool = False
    business_timezone: str = "Asia/Kolkata"
    cors_origins: str = ""
    # Password required to void payments, fulfillment, operations, cash book entries.
    # Users may also authorize with their own login password.
    void_auth_password: str = ""
    login_otp_expire_minutes: int = 15
    login_max_failed_attempts: int = 5
    login_lockout_minutes: int = 15
    # Dev only — never true on production (Spec v15.7).
    allow_destructive_scripts: bool = False
    destructive_script_confirm: str = ""
    # Idempotency guard table retention (Spec v16.0.3).
    idempotency_retention_days: int = 90
    idempotency_stale_in_progress_hours: int = 24


settings = Settings()
