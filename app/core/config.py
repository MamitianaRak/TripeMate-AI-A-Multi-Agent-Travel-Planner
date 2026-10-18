"""Application settings loaded from environment variables and `.env`."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Runtime
    environment: str = "development"
    log_level: str = "INFO"
    log_json: bool = False

    # LLM
    groq_api_key: str = ""
    groq_model: str = "openai/gpt-oss-120b"
    llm_timeout_seconds: float = 60.0
    llm_max_retries: int = 2
    # Reasoning models (gpt-oss) spend output tokens on reasoning; "low" leaves
    # more room for the answer. Leave empty for non-reasoning models.
    llm_reasoning_effort: str = "low"
    # Times the LLM is asked to continue an answer cut by the output limit.
    llm_max_continuations: int = 2
    # Target prompt size; bigger sections are condensed by the LLM, never cut.
    prompt_budget_tokens: int = 4000

    # Persistence
    database_url: str = ""
    database_sslmode: str = "require"
    database_pool_size: int = 5

    # External services (consumed through MCP servers)
    tavily_api_key: str = ""
    aviationstack_api_key: str = ""
    openweather_api_key: str = ""

    # HTTP
    cors_origins: str = "http://localhost:5173"
    rate_limit_requests: int = 10
    rate_limit_window_seconds: int = 60
    trust_proxy_headers: bool = False

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def database_conninfo(self) -> str:
        """Database URL with an explicit sslmode (hosted databases require SSL)."""
        url = self.database_url

        if url and "sslmode=" not in url and self.database_sslmode:
            separator = "&" if "?" in url else "?"
            url = f"{url}{separator}sslmode={self.database_sslmode}"

        return url

    def missing_required(self) -> list[str]:
        required = {
            "GROQ_API_KEY": self.groq_api_key,
            "DATABASE_URL": self.database_url,
            "TAVILY_API_KEY": self.tavily_api_key,
            "AVIATIONSTACK_API_KEY": self.aviationstack_api_key,
            "OPENWEATHER_API_KEY": self.openweather_api_key,
        }
        return [name for name, value in required.items() if not value]


@lru_cache
def get_settings() -> Settings:
    return Settings()
