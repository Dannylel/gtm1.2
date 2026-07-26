from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "GTM AI Backend"
    app_env: str = "development"

    database_url: str = "sqlite:///./gtm_ai.db"

    # OpenRouter configuration
    openrouter_api_key: str = "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"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"

    ai_chat_chat_model: str = "google/gemini-2.5-flash: free"
    ai_chat_router_model: str = "google/gemini-2.5-flash: free"

    # ai_chat_max_tokens: int = 4000
    # ai_router_max_tokens: int = 1200
    # Short replies: asking questions, confirming answers, navigation
    ai_chat_reply_max_tokens: int = 1000

    # Large JSON objects: ICP profiles, search recipes, quality reviews
    ai_structured_max_tokens: int = 4096
    app_site_url: str = "http://localhost:8000"
    app_site_name: str = "GTM AI ICP Builder"

    reports_dir: str = "reports"

    cors_origins: str = "http://localhost:3000,http://localhost:5173"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def cors_origin_list(self) -> list[str]:
        return [
            origin.strip()
            for origin in self.cors_origins.split(",")
            if origin.strip()
        ]


@lru_cache
def get_settings() -> Settings:
    return Settings()