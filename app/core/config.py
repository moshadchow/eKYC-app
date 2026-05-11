from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    APP_NAME: str = "eKYC Onboarding API"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:root@localhost:5432/ekyc"
    DB_ECHO: bool = False

    # JWT
    SECRET_KEY: str = "change-me-in-production-use-32-char-secret"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # OTP
    OTP_EXPIRE_MINUTES: int = 5
    OTP_MAX_ATTEMPTS: int = 3
    OTP_LOCKOUT_MINUTES: int = 30

    # Biometric retry limits (BFIU)
    BIOMETRIC_MAX_ATTEMPTS_PER_SESSION: int = 10
    BIOMETRIC_MAX_SESSIONS_PER_DAY: int = 2
    BIOMETRIC_MAX_TOTAL_SESSIONS: int = 3

    # Risk thresholds (BFIU section 2.3)
    SIMPLIFIED_BO_THRESHOLD_BDT: float = 1_500_000
    SIMPLIFIED_LIFE_SUM_ASSURED_BDT: float = 2_000_000
    SIMPLIFIED_LIFE_PREMIUM_BDT: float = 250_000
    SIMPLIFIED_NON_LIFE_PREMIUM_BDT: float = 250_000

    # EDD window
    EDD_DEADLINE_DAYS: int = 30

    # Risk score threshold (BFIU section 6.2)
    HIGH_RISK_SCORE_THRESHOLD: int = 15

    # Storage
    STORAGE_BUCKET: str = "ekyc-documents"
    STORAGE_ENDPOINT: str = "http://localhost:9000"
    STORAGE_ACCESS_KEY: str = "minioadmin"
    STORAGE_SECRET_KEY: str = "minioadmin"

    # OCR extraction
    OCR_PROVIDER: str = "mock"
    OCR_API_KEY: str = ""
    OCR_API_ENDPOINT: str = ""
    OCR_CONFIDENCE_THRESHOLD: float = 0.60

    # EC (Election Commission) verification
    EC_PROVIDER: str = "mock"
    EC_API_ENDPOINT: str = ""
    EC_API_KEY: str = ""

    # Notification gateway
    NOTIFICATION_MOCK: bool = True
    SMS_GATEWAY_URL: str = ""
    SMS_API_KEY: str = ""
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
