import enum
from typing import Any

from pydantic import PostgresDsn, ValidationInfo, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppEnvironment(enum.StrEnum):
    DEVELOP = "development"
    PRODUCTION = "production"


class Settings(BaseSettings):
    # 明示的に環境変数を読み込む（Pydantic_v2以降）
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    ENVIRONMENT: AppEnvironment

    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "UI Recommender"

    # PostgreSQL接続情報
    POSTGRES_SERVER: str
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_DB: str
    POSTGRES_PORT: str
    SQLALCHEMY_DATABASE_URI: str | None = None

    # Kubernetes設定
    K8S_NAMESPACE: str = "default"
    K8S_IN_CLUSTER: bool = False

    # Artifact保存先
    ARTIFACTS_DIR: str = "/tmp/ui-recommender-artifacts"

    # Worker設定
    WORKER_IMAGE: str = "ui-recommender-worker:latest"
    WORKER_DEADLINE_SECONDS: int = 900
    MAX_PROPOSALS: int = 3

    # GitHub Token（PR作成用）
    GITHUB_TOKEN: str = ""

    # Anthropic API Key（K8s Secret経由でWorkerに渡す）
    ANTHROPIC_API_KEY: str = ""

    @field_validator("SQLALCHEMY_DATABASE_URI", mode="after")
    def assemble_db_connection(cls, v: str | None, values: ValidationInfo) -> Any:
        if isinstance(v, str):
            return v

        return str(
            PostgresDsn.build(
                scheme="postgresql",
                username=values.data.get("POSTGRES_USER"),
                password=values.data.get("POSTGRES_PASSWORD"),
                host=values.data.get("POSTGRES_SERVER"),
                port=int(values.data.get("POSTGRES_PORT", "5432")),
                path=f"{values.data.get('POSTGRES_DB') or ''}",
            )
        )


settings = Settings()
