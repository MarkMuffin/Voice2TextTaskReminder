from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Telegram
    telegram_bot_token: str = "changeme"

    # Database
    database_url: str = "sqlite+aiosqlite:///data/app.db"

    # LLM
    llm_provider: str = "mock"  # mock | openrouter
    openrouter_api_key: str = ""
    openrouter_model: str = "openai/gpt-4o-mini"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"

    # STT
    stt_provider: str = "mock"  # mock | openai | groq
    stt_api_key: str = ""
    stt_model: str = "whisper-1"
    stt_base_url: str = "https://api.openai.com/v1"

    # App
    default_timezone: str = "Europe/Amsterdam"
    log_level: str = "INFO"

    # Recurring tasks
    enable_recurring_tasks: bool = True
    recurring_task_generator_interval_seconds: int = 60


settings = Settings()
