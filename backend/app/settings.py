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
    firebase_project_id: str = ""
    firestore_project_id: str = ""
    storage_bucket: str = ""
    cloud_tasks_project: str = ""
    cloud_tasks_location: str = ""
    cloud_tasks_queue: str = ""
    cloud_run_service_url: str = ""
    cloud_tasks_secret: str = ""
    default_model_reference: Path = Path("./model_data/model-reference.png")
    signed_url_minutes: int = 30


settings = Settings()
settings.data_dir.mkdir(parents=True, exist_ok=True)
