"""Validated, central configuration for VietReport."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict


ROOT = Path(__file__).resolve().parents[1]


class SafetyConfig(BaseModel):
    statement_timeout_ms: int = Field(gt=0)
    max_rows: int = Field(gt=0)
    allowed_schema: str = "public"
    blocked_functions: set[str]


class DatabaseConfig(BaseModel):
    host: str
    port: int = Field(gt=0, le=65535)
    database: str
    reader_user: str
    reader_password: str


class ModelConfig(BaseModel):
    base_url: str
    api_key: str
    model: str
    temperature: float = Field(ge=0, le=2)
    max_tokens: int = Field(gt=0)
    timeout_seconds: int = Field(gt=0)


class _Environment(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "E-commerce"
    postgres_user: str = "vietreport_reader"
    postgres_password: str = ""
    baseline_base_url: str = ""
    baseline_api_key: str = ""
    baseline_model: str = ""


def _load_yaml(name: str) -> dict[str, Any]:
    path = ROOT / "configs" / name
    with path.open(encoding="utf-8") as handle:
        value = yaml.safe_load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a YAML object.")
    return value


def _required_env(name: str) -> str:
    load_dotenv(ROOT / ".env")
    value = os.getenv(name, "")
    if not value:
        raise ValueError(f"Required environment variable {name} is not set.")
    return value


@lru_cache(maxsize=1)
def get_safety_config() -> SafetyConfig:
    return SafetyConfig.model_validate(_load_yaml("safety.yaml"))


def get_database_config() -> DatabaseConfig:
    env = _Environment()
    if not env.postgres_password:
        raise ValueError("POSTGRES_PASSWORD is required.")
    return DatabaseConfig(
        host=env.postgres_host,
        port=env.postgres_port,
        database=env.postgres_db,
        reader_user=env.postgres_user,
        reader_password=env.postgres_password,
    )


def get_model_config(agent: str = "baseline_sql") -> ModelConfig:
    raw = _load_yaml("models.yaml")
    profile_name = raw.get("agents", {}).get(agent, "default")
    profile = raw.get(profile_name)
    if not isinstance(profile, dict):
        raise ValueError(f"Unknown model profile for agent '{agent}'.")
    return ModelConfig(
        base_url=profile["base_url"],
        api_key=_required_env(profile["api_key_env"]),
        model=profile["model"],
        temperature=profile["temperature"],
        max_tokens=profile["max_tokens"],
        timeout_seconds=profile["timeout_seconds"],
    )


__all__ = [
    "DatabaseConfig",
    "ModelConfig",
    "SafetyConfig",
    "ValidationError",
    "get_database_config",
    "get_model_config",
    "get_safety_config",
]
