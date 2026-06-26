"""Application configuration."""
from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Database
    database_url: str = "sqlite+aiosqlite:///./data/odds_events.db"

    # CORS
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://localhost:3000",
    ]

    # App
    app_name: str = "Odds-Event Correlation API"
    debug: bool = True

    # Data
    data_dir: Path = Path("./data")

    # AI / LLM
    llm_api_key: str = "sk-1669f14c221b42fe90f64e51494c60d2"
    llm_base_url: str = "https://api.deepseek.com"
    llm_model: str = "deepseek-v4-flash"

    model_config = {"env_prefix": "OEC_", "extra": "allow"}


settings = Settings()
