from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:3000", "http://127.0.0.1:3000"]
    )
    openai_api_key: str | None = None
    ollama_base_url: str = "http://localhost:11434"
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "muninn"
    postgres_user: str = "muninn"
    postgres_password: str = "muninn"
    chroma_host: str = "localhost"
    chroma_port: int = 8001
    security_mode: str = "assistive"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")
