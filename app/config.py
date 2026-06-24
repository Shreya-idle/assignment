from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql://postgres:postgres@db:5432/transactions"
    redis_url: str = "redis://redis:6379/0"
    gemini_api_key: str = ""
    llm_model: str = "gemini-1.5-flash"

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
