from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://sheet2portal:sheet2portal@localhost:5433/sheet2portal"
    upload_dir: str = "./uploads"
    max_upload_size_bytes: int = 25 * 1024 * 1024
    max_rows_per_sheet: int = 50_000
    sample_row_count: int = 20
    allowed_extensions: tuple[str, ...] = (".xlsx", ".csv")
    llm_provider: str = "none"


settings = Settings()
