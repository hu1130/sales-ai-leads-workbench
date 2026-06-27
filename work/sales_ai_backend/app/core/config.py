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
    qwen_api_key: str | None = None
    asr_provider: str | None = None
    asr_api_key: str | None = None
    funasr_docker_image: str = "sales-ai-funasr:local"
    funasr_docker_timeout: int = 1800
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
