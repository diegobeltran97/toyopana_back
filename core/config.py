from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    SUPABASE_URL: str
    SUPABASE_SERVICE_ROLE_KEY: str
    ORGANIZATION_ID: str
    PIPEFY_API_TOKEN: str
    WHAPIFY_API_TOKEN: str
    WHAPIFY_BASE_URL: str = "https://gate.whapi.cloud"  # Optional with default
    # Active messaging provider. Must be a key of the factory's builder map;
    # an unknown value raises at startup rather than falling back silently.
    WHATSAPP_PROVIDER: str = "whapi"
    # Shared secret Whapi sends back in the X-Webhook-Token header. Empty means
    # the inbound webhook rejects everything -- deliberate: a blank secret must
    # never read as "no authentication required".
    WHAPI_WEBHOOK_SECRET: str = ""
    # Testing-mode allowlist: comma-separated numbers that may receive a reply.
    # EMPTY = disabled = the bot answers everyone, which is the production
    # behaviour. Set it while testing against a live channel so real customers
    # never get a half-built bot; unset it to go live. Never the other way
    # round: an accidental value here silences the bot for everyone else.
    WHATSAPP_ALLOWED_NUMBERS: str = ""
    # Firma de los links de agenda que se le mandan al cliente por WhatsApp.
    # Vacío = no se pueden emitir ni verificar links: falla cerrado, para que un
    # .env incompleto nunca se lea como "sin firma".
    AGENDA_TOKEN_SECRET: str = ""
    ENVIRONMENT: str = "development"  # Optional with default

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

settings = Settings()