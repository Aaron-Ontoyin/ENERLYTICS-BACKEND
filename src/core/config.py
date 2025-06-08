import hashlib
from typing import Literal

from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)
from dotenv import load_dotenv

load_dotenv(override=True)


def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


class Settings(BaseSettings):
    SECRET_KEY: str
    ENVIRONMENT: Literal["development", "production"] = "production"

    API_VERSION: str
    API_NAME: str = "enerlytics"
    APOSTGRES_DATABASE_URL: str
    GEMINI_API_KEY: str
    LYTI_LLM: str
    ACCESS_TOKEN_EXPIRE_HOURS: int = 24
    REFRESH_TOKEN_EXPIRE_HOURS: int = 24 * 7

    model_config = SettingsConfigDict(
        case_sensitive=False,
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @classmethod
    def customise_sources(
        cls,
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (
            dotenv_settings,
            file_secret_settings,
            env_settings,
            init_settings,
        )


settings = Settings()  # type: ignore
