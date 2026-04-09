# backend/app/core/config.py
import os
from pydantic_settings import BaseSettings, SettingsConfigDict

# Get the absolute path to the backend directory where .env lives
backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
env_file_path = os.path.join(backend_dir, ".env")

class Settings(BaseSettings):
    PROJECT_NAME: str = "SRM AI SETU"
    MONGODB_URI: str = "mongodb://localhost:27017/aisetu_db"
    SECRET_KEY: str = "your-secret-key-for-development!"  # Change in production!
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days
    
    encryption_key: str = "default_placeholder_if_missing"
    google_api_key: str = "default_placeholder_if_missing"

    # WhatsApp Cloud API (Meta) — uncomment gateway code in billing/service.py to activate
    WHATSAPP_TOKEN: str = ""
    WHATSAPP_TOKEN_FALLBACK: str = ""
    WHATSAPP_PHONE_NUMBER_ID: str = ""

    # PhonePe Payment Gateway — uncomment gateway code in billing/service.py to activate
    # Test credentials (switch to production keys before go-live)
    PHONEPE_MERCHANT_ID: str = "PGTESTPAYUAT86"
    PHONEPE_SALT_KEY: str = "96434309-7796-489d-8924-ab56988a6076"
    PHONEPE_SALT_INDEX: str = "1"
    PHONEPE_BASE_URL: str = "https://api-preprod.phonepe.com/apis/pg-sandbox"
    PHONEPE_ENV: str = "sandbox"          # change to "production" for live
    PHONEPE_CALLBACK_BASE_URL: str = ""   # e.g. https://yourdomain.com (must be public)

    # SMTP Settings
    SMTP_SERVER: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    SENDER_EMAIL: str = ""
    
    SRM_HOST: str = "0.0.0.0"
    SRM_PORT: int = 8080
    # API_BASE_URL: str = "https://dev-srm.hkdigiskill.com/api"
    API_BASE_URL: str = ""



    model_config = SettingsConfigDict(
        env_file=env_file_path,
        extra="allow"
    )

settings = Settings()

# Global API Configuration (Networking)
HOST = settings.SRM_HOST
PORT = settings.SRM_PORT

# Final calculated API Base URL for internal/fallback use
if settings.API_BASE_URL:
    API_BASE_URL = settings.API_BASE_URL
else:
    _display_host = "localhost" if HOST == "0.0.0.0" else HOST
    API_BASE_URL = f"http://{_display_host}:{PORT}/api"
