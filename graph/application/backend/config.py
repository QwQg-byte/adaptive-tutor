"""FastAPI 配置文件。"""

from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parents[2]


class Settings(BaseSettings):
    """应用配置"""

    model_config = SettingsConfigDict(
        # 根 .env 是合并项目的统一配置；服务目录 .env 只做本机覆盖。
        env_file=(PROJECT_ROOT / ".env", BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # 应用设置
    APP_NAME: str = "知识图谱可视化系统"
    APP_VERSION: str = "1.0.0"
    ENVIRONMENT: Literal["development", "test", "production"] = "development"
    DEBUG: bool = False
    RELOAD: bool = False

    # Neo4j配置
    NEO4J_URI: str = "bolt://localhost:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: SecretStr
    NEO4J_DATABASE: str = "neo4j"
    NEO4J_MAX_CONNECTION_POOL_SIZE: int = Field(default=50, ge=1, le=500)
    NEO4J_CONNECTION_TIMEOUT_SECONDS: float = Field(default=10.0, gt=0, le=120)
    NEO4J_CONNECTION_ACQUISITION_TIMEOUT_SECONDS: float = Field(default=30.0, gt=0, le=300)
    NEO4J_MAX_CONNECTION_LIFETIME_SECONDS: float = Field(default=3600.0, gt=0, le=86400)
    NEO4J_MAX_TRANSACTION_RETRY_TIME_SECONDS: float = Field(default=15.0, ge=0, le=300)
    NEO4J_QUERY_TIMEOUT_SECONDS: float = Field(default=30.0, gt=0, le=300)
    NEO4J_FETCH_SIZE: int = Field(default=1000, ge=1, le=10000)
    NEO4J_FULLTEXT_INDEX_NAME: str = Field(
        default="content_search_fulltext",
        pattern=r"^[A-Za-z_][A-Za-z0-9_]*$",
    )
    GRAPH_STATISTICS_CACHE_TTL_SECONDS: float = Field(default=30.0, ge=0, le=3600)
    HOME_DATA_CACHE_TTL_SECONDS: float = Field(default=60.0, ge=0, le=3600)

    # API设置
    API_PREFIX: str = "/api/v1"
    HOST: str = "127.0.0.1"
    PORT: int = Field(default=8000, ge=1, le=65535)

    # CORS设置
    CORS_ORIGINS: list[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
        "http://localhost:8600",
        "http://127.0.0.1:8600",
    ]
    CORS_ALLOW_CREDENTIALS: bool = False

    # 日志设置
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    LOG_FILE: str = "logs/app.log"
    SLOW_REQUEST_THRESHOLD_MS: float = Field(default=500.0, gt=0, le=60000)
    SLOW_QUERY_THRESHOLD_MS: float = Field(default=300.0, gt=0, le=60000)

    # 应用层限速（Nginx 之外的纵深防御；按单进程每客户端 IP 计数）
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_PER_MINUTE: int = Field(default=240, ge=1, le=100000)
    RATE_LIMIT_MAX_CLIENTS: int = Field(default=10000, ge=100, le=1000000)

    @field_validator("NEO4J_PASSWORD")
    @classmethod
    def validate_neo4j_password(cls, value: SecretStr) -> SecretStr:
        password = value.get_secret_value().strip()
        unsafe_values = {
            "",
            "neo4j",
            "password",
            "your_password",
            "change_me",
            "replace_with_a_strong_password",
        }
        if password.lower() in unsafe_values:
            raise ValueError("NEO4J_PASSWORD 必须通过环境变量设置为非默认密码")
        return value

    @field_validator("CORS_ORIGINS")
    @classmethod
    def validate_cors_origins(cls, origins: list[str]) -> list[str]:
        normalized = [origin.rstrip("/") for origin in origins]
        if not normalized or "*" in normalized:
            raise ValueError("CORS_ORIGINS 必须是明确的来源列表，不能使用通配符")
        if any(not origin.startswith(("http://", "https://")) for origin in normalized):
            raise ValueError("CORS_ORIGINS 仅支持 http:// 或 https:// 来源")
        return normalized

    @model_validator(mode="after")
    def validate_production_settings(self):
        if self.ENVIRONMENT == "production" and (self.DEBUG or self.RELOAD):
            raise ValueError("生产环境禁止启用 DEBUG 或 RELOAD")
        return self


# 全局配置实例
settings = Settings()
