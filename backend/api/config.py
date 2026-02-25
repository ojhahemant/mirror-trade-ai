"""
Central configuration using pydantic-settings.
All values loaded from environment variables / .env file.
"""
from pydantic_settings import BaseSettings
from pydantic import Field
from typing import List
import os


class Settings(BaseSettings):
    # App
    app_env: str = Field(default="development", env="APP_ENV")
    app_host: str = Field(default="0.0.0.0", env="APP_HOST")
    app_port: int = Field(default=8000, env="APP_PORT")
    frontend_url: str = Field(default="http://localhost:3000", env="FRONTEND_URL")
    cors_origins: str = Field(default="http://localhost:3000", env="CORS_ORIGINS")

    # Database
    database_url: str = Field(env="DATABASE_URL")
    postgres_host: str = Field(default="localhost", env="POSTGRES_HOST")

    # Redis
    redis_url: str = Field(default="redis://localhost:6379/0", env="REDIS_URL")
    celery_broker_url: str = Field(default="redis://localhost:6379/1", env="CELERY_BROKER_URL")
    celery_result_backend: str = Field(default="redis://localhost:6379/2", env="CELERY_RESULT_BACKEND")

    # Security
    jwt_secret: str = Field(env="JWT_SECRET")
    jwt_algorithm: str = Field(default="HS256", env="JWT_ALGORITHM")
    jwt_expiry_hours: int = Field(default=24, env="JWT_EXPIRY_HOURS")

    # Kite Connect
    kite_api_key: str = Field(default="", env="KITE_API_KEY")
    kite_api_secret: str = Field(default="", env="KITE_API_SECRET")
    kite_access_token: str = Field(default="", env="KITE_ACCESS_TOKEN")

    # Alerts
    telegram_bot_token: str = Field(default="", env="TELEGRAM_BOT_TOKEN")
    telegram_chat_id: str = Field(default="", env="TELEGRAM_CHAT_ID")
    sendgrid_api_key: str = Field(default="", env="SENDGRID_API_KEY")
    sendgrid_from_email: str = Field(default="alerts@mirrortradeai.com", env="SENDGRID_FROM_EMAIL")

    # ML Config
    model_dir: str = Field(default="/app/models_saved", env="MODEL_DIR")
    min_confidence: float = Field(default=65.0, env="MIN_CONFIDENCE_BUY")

    # Market Config
    banknifty_token: int = Field(default=260105, env="BANKNIFTY_INSTRUMENT_TOKEN")
    banknifty_symbol: str = Field(default="NSE:BANKNIFTY", env="BANKNIFTY_SYMBOL")
    ist_timezone: str = Field(default="Asia/Kolkata", env="IST_TIMEZONE")
    market_open_hour: int = Field(default=9, env="MARKET_OPEN_HOUR")
    market_open_minute: int = Field(default=15, env="MARKET_OPEN_MINUTE")
    market_close_hour: int = Field(default=15, env="MARKET_CLOSE_HOUR")
    market_close_minute: int = Field(default=30, env="MARKET_CLOSE_MINUTE")

    @property
    def cors_origins_list(self) -> List[str]:
        return [origin.strip() for origin in self.cors_origins.split(",")]

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        extra = "ignore"


settings = Settings()
