"""
Riskism Backend Configuration
"""
import os
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # App
    app_name: str = "Riskism"
    app_env: str = "development"
    app_secret_key: str = "change-me-in-production"
    secret_key: str = ""
    debug: bool = True

    # PostgreSQL
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "riskism"
    postgres_user: str = "riskism"
    postgres_password: str = "riskism_secret_2024"

    # Redis
    redis_host: str = "localhost"
    redis_port: int = 6379

    # Gemini AI
    gemini_api_key: str = ""
    gemini_fast_models: str = "gemini-2.5-flash,gemini-2.0-flash"
    gemini_reasoning_models: str = "gemini-2.5-pro,gemini-2.5-flash,gemini-2.0-flash"
    gemini_fallback_models: str = "gemini-2.5-flash,gemini-2.0-flash"

    # Firebase Auth
    firebase_project_id: str = ""
    firebase_api_key: str = ""
    firebase_auth_domain: str = ""
    firebase_storage_bucket: str = ""
    firebase_messaging_sender_id: str = ""
    firebase_app_id: str = ""
    firebase_measurement_id: str = ""
    firebase_service_account_path: str = ""
    firebase_service_account_json: str = ""

    # Celery
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"

    # Market
    market_timezone: str = "Asia/Ho_Chi_Minh"
    morning_analysis_time: str = "08:30"
    afternoon_review_time: str = "15:30"

    @property
    def database_url(self) -> str:
        return f"postgresql://{self.postgres_user}:{self.postgres_password}@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"

    @property
    def async_database_url(self) -> str:
        return f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"

    @property
    def redis_url(self) -> str:
        return f"redis://{self.redis_host}:{self.redis_port}"

    @property
    def jwt_secret_key(self) -> str:
        return self.secret_key or self.app_secret_key

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
