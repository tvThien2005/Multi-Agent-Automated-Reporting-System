import pytest

from src.config import get_model_config, get_safety_config


def test_safety_config_loads() -> None:
    config = get_safety_config()
    assert config.statement_timeout_ms == 10_000
    assert "pg_sleep" in config.blocked_functions


def test_model_config_requires_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BASELINE_API_KEY", "")
    with pytest.raises(ValueError, match="Required environment variable"):
        get_model_config()
