from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", populate_by_name=True)

    database_url: str = "postgresql+psycopg://sheet2portal:sheet2portal@localhost:5433/sheet2portal"
    upload_dir: str = "./uploads"
    max_upload_size_bytes: int = 25 * 1024 * 1024
    max_rows_per_sheet: int = 50_000
    sample_row_count: int = 20
    allowed_extensions: tuple[str, ...] = (".xlsx", ".csv")

    # Auth: session token in an httpOnly cookie. Set SESSION_COOKIE_SECURE=true
    # when served over HTTPS (production) so the cookie is never sent in clear.
    session_cookie_name: str = "s2p_session"
    session_ttl_hours: int = 24 * 7
    session_cookie_secure: bool = False
    cors_origins: tuple[str, ...] = ("http://localhost:5173",)

    # Chatbot: AI is used exclusively here -- parsing/analysis/KPIs stay
    # deterministic. Names match the existing Vedha/Orka project's Render
    # env vars so those credentials can be reused as-is on a shared service.
    chatbot_provider: str = "groq"  # which configured provider is used by default
    groq_api_key: str = ""
    # Vedha reads GEMINI_API_KEY_1 first, then GEMINI_API_KEY -- accept both.
    gemini_api_key: str = Field(default="", validation_alias=AliasChoices("GEMINI_API_KEY_1", "GEMINI_API_KEY"))
    # Optional second Gemini key (e.g. another Google project with its own
    # free quota), tried when the first is rate limited / out of quota.
    gemini_api_key_2: str = ""
    openrouter_api_key: str = ""
    cerebras_api_key: str = ""
    chatbot_model: str = ""  # optional override; blank = provider's built-in default
    chat_request_timeout_seconds: float = 20.0
    chat_max_history_messages: int = 20
    chat_max_tool_iterations: int = 4
    chat_tool_max_page_size: int = 50


settings = Settings()
