from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Sales AI Backend"
    database_url: str = "sqlite:///./sales_ai.db"
    jwt_secret_key: str = "sales-ai-default-dev-key-change-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440
    upload_dir: str = "uploads"
    default_admin_username: str = "admin"
    default_admin_password: str = "admin123"
    deepseek_api_key: str | None = None
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-v4-flash"
    dashscope_api_key: str | None = None
    dashscope_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    dashscope_ocr_model: str = "qwen-vl-plus"
    dashscope_asr_model: str = "paraformer-v2"
    asr_audio_base_url: str | None = None
    public_file_token: str | None = None
    qwen_api_key: str | None = None
    asr_provider: str | None = None
    asr_api_key: str | None = None
    asr_poll_timeout: int = 300
    asr_poll_interval: float = 2.0
    funasr_docker_image: str = "sales-ai-funasr:local"
    funasr_docker_timeout: int = 1800
    call_provider: str = "mock"
    call_provider_base_url: str | None = None
    call_provider_app_id: str | None = None
    call_provider_app_key: str | None = None
    call_provider_app_secret: str | None = None
    call_provider_caller: str | None = None
    call_provider_script_id: str | None = None
    call_provider_webhook_secret: str | None = None
    call_provider_config_secret: str | None = None
    call_provider_timeout: float = 30.0
    ai_robot_auto_sync_enabled: bool = True
    ai_robot_auto_sync_interval_seconds: int = 15
    ai_robot_auto_sync_batch_size: int = 20
    integration_api_key: str | None = None
    integration_tenant_id: int = 1
    platform_service_token: str | None = None
    platform_tenant_id: int = 1
    storage_backend: str = "local"
    oss_endpoint: str | None = None
    oss_bucket: str | None = None
    oss_access_key_id: str | None = None
    oss_access_key_secret: str | None = None
    oss_prefix: str = "sales-ai"
    oss_public_base_url: str | None = None
    oss_signed_url_expires: int = 600
    cors_origins: str = "*"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    @property
    def upload_path(self) -> Path:
        return Path(self.upload_dir)

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
