InvalidOperation: 
Line |
   2 |  [Console]::OutputEncoding=[Text.Encoding]::UTF8; Get-Content -Literal ��
     |  ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
     | Cannot set property. Property setting is supported only on core types in this language mode.
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="BLING_", env_file=".env", extra="ignore")

    data_dir: Path = Path("./data")
    model_dir: Path = Path("./model_data")
    frontend_origin: str = "https://axiyea-jpg.github.io"
    owner_token: str = ""
    openai_api_key: str = ""
    vision_model: str = "gpt-5.4-mini"
    image_model: str = "gpt-image-2"
    public_base_url: str = ""


settings = Settings()
settings.data_dir.mkdir(parents=True, exist_ok=True)


