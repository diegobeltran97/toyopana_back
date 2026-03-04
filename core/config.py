from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    SUPABASE_URL: str
    SUPABASE_SERVICE_ROLE_KEY: str
    ORGANIZATION_ID: str
    PIPEFY_API_TOKEN: str
    WHAPIFY_API_TOKEN: str
    WHAPIFY_BASE_URL: str = "https://gate.whapi.cloud"  # Optional with default
    ENVIRONMENT: str = "development"  # Optional with default

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

settings = Settings()