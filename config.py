from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import SecretStr

class Settings(BaseSettings):
    bot_token: SecretStr
    database_url: SecretStr
    meat_price: int = 95000

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

config = Settings()