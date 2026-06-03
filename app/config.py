from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_host: str = "0.0.0.0"
    app_port: int = 3052

    ttlock_base_url: str = "https://euapi.ttlock.com"
    ttlock_client_id: str
    ttlock_client_secret: str
    ttlock_username: str
    ttlock_password_md5: str
    ttlock_lock_id: int

    ttlock_default_permanent: bool = True
    data_dir: str = "./data"
    debug_ttlock: bool = False

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
