"""
Configuration management for TAi.
Loads from config/tai.yaml and environment variables.
"""

import os
from pathlib import Path
from typing import Optional, Dict, Any
import yaml
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator


class Neo4jConfig(BaseSettings):
    """Neo4j connection configuration."""
    uri: str = Field(default="bolt://localhost:7687", alias="NEO4J_URI")
    user: str = Field(default="neo4j", alias="NEO4J_USER")
    password: str = Field(default="changeme", alias="NEO4J_PASSWORD")
    max_connection_lifetime: int = Field(default=3600)
    max_connection_pool_size: int = Field(default=50)

    model_config = SettingsConfigDict(env_prefix="NEO4J_", extra="ignore")


class LLMConfig(BaseSettings):
    """LLM provider configuration."""
    provider: str = Field(default="openai")  # openai, anthropic
    openai_api_key: Optional[str] = Field(default=None, alias="OPENAI_API_KEY")
    anthropic_api_key: Optional[str] = Field(default=None, alias="ANTHROPIC_API_KEY")
    default_model: str = Field(default="gpt-4o-mini")
    extraction_model: str = Field(default="gpt-4o-mini")
    reasoning_model: str = Field(default="gpt-4-turbo")
    temperature: float = Field(default=0.0)
    max_tokens: int = Field(default=2000)

    model_config = SettingsConfigDict(env_prefix="LLM_", extra="ignore")


class EmbeddingConfig(BaseSettings):
    """Embedding model configuration."""
    provider: str = Field(default="openai")
    model: str = Field(default="text-embedding-3-small", alias="EMBEDDING_MODEL")
    batch_size: int = Field(default=100)
    dimension: int = Field(default=1536)

    model_config = SettingsConfigDict(env_prefix="EMBEDDING_", extra="ignore")


class IndexingConfig(BaseSettings):
    """Indexing pipeline configuration."""
    data_dir: Path = Field(default=Path("data/raw"))
    staging_dir: Path = Field(default=Path("data/staging"))
    processed_dir: Path = Field(default=Path("data/processed"))
    chunk_size: int = Field(default=512)
    chunk_overlap: int = Field(default=102)  # 20% of 512
    content_hash_algorithm: str = Field(default="sha256")

    model_config = SettingsConfigDict(env_prefix="INDEXING_", extra="ignore")


class RetrievalConfig(BaseSettings):
    """Retrieval configuration."""
    default_strategy: str = Field(default="local")
    max_context_tokens: int = Field(default=4000)
    top_k: int = Field(default=5)
    hybrid_graph_weight: float = Field(default=0.4)
    hybrid_vector_weight: float = Field(default=0.6)

    model_config = SettingsConfigDict(env_prefix="RETRIEVAL_", extra="ignore")


class SessionConfig(BaseSettings):
    """Session management configuration."""
    idle_timeout_minutes: int = Field(default=120, alias="SESSION_IDLE_TIMEOUT_MINUTES")
    max_tokens: int = Field(default=20000, alias="SESSION_MAX_TOKENS")
    reset_by_type: Dict[str, Dict[str, Any]] = Field(default_factory=dict)

    model_config = SettingsConfigDict(env_prefix="SESSION_", extra="ignore")


class ApiConfig(BaseSettings):
    """API server configuration."""
    host: str = Field(default="0.0.0.0", alias="API_HOST")
    port: int = Field(default=8000, alias="API_PORT")
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])
    rate_limit_requests_per_minute: int = Field(default=30, alias="API_RATE_LIMIT_RPM")

    model_config = SettingsConfigDict(env_prefix="API_", extra="ignore")


class SafetyConfig(BaseSettings):
    """Safety and compliance configuration."""
    ferpa_compliance_mode: str = Field(default="strict", alias="FERPA_COMPLIANCE_MODE")
    consent_required: bool = Field(default=True, alias="CONSENT_REQUIRED")
    data_retention_days: int = Field(default=365, alias="DATA_RETENTION_DAYS")
    executor_enabled: bool = Field(default=True)
    executor_allowlist: list[str] = Field(default_factory=lambda: [
        "go", "python3", "docker", "aws", "terraform", "locust"
    ])
    executor_denylist: list[str] = Field(default_factory=lambda: [
        "rm", "chmod", "chown", "dd", "nc", "netcat"
    ])

    model_config = SettingsConfigDict(env_prefix="SAFETY_", extra="ignore")


class TAiSettings(BaseSettings):
    """Main TAi configuration."""
    env: str = Field(default="dev", alias="TAI_ENV")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    log_file: Path = Field(default=Path("logs/tai.log"), alias="LOG_FILE")
    
    # Sub-configurations
    api: ApiConfig = Field(default_factory=ApiConfig)
    neo4j: Neo4jConfig = Field(default_factory=Neo4jConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    embedding: EmbeddingConfig = Field(default_factory=EmbeddingConfig)
    indexing: IndexingConfig = Field(default_factory=IndexingConfig)
    retrieval: RetrievalConfig = Field(default_factory=RetrievalConfig)
    session: SessionConfig = Field(default_factory=SessionConfig)
    safety: SafetyConfig = Field(default_factory=SafetyConfig)
    
    # WAL and Graph sync
    wal_path: Path = Field(default=Path("data/wal.sqlite"), alias="WAL_PATH")
    graph_checkpoint_path: Path = Field(
        default=Path("data/graph_checkpoint.json"),
        alias="GRAPH_CHECKPOINT_PATH"
    )
    circuit_breaker_failure_threshold: int = Field(
        default=3,
        alias="CIRCUIT_BREAKER_FAILURE_THRESHOLD"
    )
    circuit_breaker_reset_seconds: int = Field(
        default=60,
        alias="CIRCUIT_BREAKER_RESET_SECONDS"
    )
    
    # GraphRAG
    graph_resolution: float = Field(default=0.05, alias="GRAPH_RESOLUTION")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="allow"
    )

    @classmethod
    def load_from_yaml(cls, config_path: Optional[Path] = None) -> "TAiSettings":
        """Load settings from YAML file and merge with environment variables."""
        if config_path is None:
            config_path = Path("config/tai.yaml")
        
        config_dict: Dict[str, Any] = {}
        
        if config_path.exists():
            with open(config_path, "r", encoding="utf-8") as f:
                yaml_data = yaml.safe_load(f) or {}
                config_dict = yaml_data.get("tai", {})
        
        # Flatten api.rate_limit.requests_per_minute if present
        if "api" in config_dict and isinstance(config_dict["api"], dict):
            api_cfg = dict(config_dict["api"])
            rate_limit = api_cfg.get("rate_limit")
            if isinstance(rate_limit, dict) and "requests_per_minute" in rate_limit:
                api_cfg["rate_limit_requests_per_minute"] = rate_limit["requests_per_minute"]
            if "rate_limit" in api_cfg:
                del api_cfg["rate_limit"]
            config_dict["api"] = api_cfg
        
        # Create settings instance
        settings = cls(**config_dict)
        
        # Override with environment variables
        return settings


# Global settings instance
_settings: Optional[TAiSettings] = None


def get_settings() -> TAiSettings:
    """Get or create global settings instance."""
    global _settings
    if _settings is None:
        _settings = TAiSettings.load_from_yaml()
    return _settings


# Alias for convenience
settings = get_settings()
