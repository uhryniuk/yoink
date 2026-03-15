"""Unit tests for config.py."""

import os
import tomllib
from pathlib import Path

import pytest

from yoink.config import Config, LogConfig, RateLimitConfig, ServiceConfig, WorkerConfig, load_config


class TestDefaults:
    def test_worker_config_defaults(self):
        import multiprocessing
        cfg = WorkerConfig()
        assert cfg.count == multiprocessing.cpu_count()
        assert cfg.pages_per_worker == 5
        assert cfg.idle_timeout_secs == 300
        assert cfg.headless is True
        assert cfg.user_agent is None

    def test_rate_limit_defaults(self):
        cfg = RateLimitConfig()
        assert cfg.default_delay_ms == 0
        assert cfg.per_domain == {}

    def test_service_defaults(self):
        cfg = ServiceConfig()
        assert cfg.host == "0.0.0.0"
        assert cfg.port == 8000
        assert cfg.api_key is None

    def test_log_defaults(self):
        cfg = LogConfig()
        assert cfg.level == "INFO"
        assert cfg.minimal is False

    def test_config_defaults(self):
        cfg = Config()
        assert isinstance(cfg.workers, WorkerConfig)
        assert isinstance(cfg.rate_limit, RateLimitConfig)
        assert isinstance(cfg.service, ServiceConfig)
        assert isinstance(cfg.log, LogConfig)


class TestTomlLoading:
    def test_load_partial_toml(self, tmp_path):
        toml = tmp_path / "cfg.toml"
        toml.write_bytes(b"""
[workers]
count = 2
headless = false

[service]
port = 9000
api_key = "secret"
""")
        cfg = load_config(toml)
        assert cfg.workers.count == 2
        assert cfg.workers.headless is False
        assert cfg.service.port == 9000
        assert cfg.service.api_key == "secret"
        # unset fields keep defaults
        assert cfg.workers.pages_per_worker == 5

    def test_load_rate_limit_per_domain(self, tmp_path):
        toml = tmp_path / "cfg.toml"
        toml.write_bytes(b"""
[rate_limit]
default_delay_ms = 100

[rate_limit.per_domain]
"example.com" = 500
""")
        cfg = load_config(toml)
        assert cfg.rate_limit.default_delay_ms == 100
        assert cfg.rate_limit.per_domain == {"example.com": 500}

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_config(tmp_path / "nonexistent.toml")


class TestEnvVarOverrides:
    def test_int_coercion(self, monkeypatch):
        monkeypatch.setenv("YK_WORKERS__COUNT", "8")
        cfg = load_config()
        assert cfg.workers.count == 8

    def test_bool_coercion_true(self, monkeypatch):
        monkeypatch.setenv("YK_WORKERS__HEADLESS", "false")
        cfg = load_config()
        assert cfg.workers.headless is False

    def test_bool_coercion_variants(self, monkeypatch):
        for val in ("true", "1", "yes"):
            monkeypatch.setenv("YK_WORKERS__HEADLESS", val)
            cfg = load_config()
            assert cfg.workers.headless is True

    def test_str_passthrough(self, monkeypatch):
        monkeypatch.setenv("YK_SERVICE__API_KEY", "my-key")
        cfg = load_config()
        assert cfg.service.api_key == "my-key"

    def test_env_wins_over_toml(self, monkeypatch, tmp_path):
        toml = tmp_path / "cfg.toml"
        toml.write_bytes(b"[workers]\ncount = 2\n")
        monkeypatch.setenv("YK_WORKERS__COUNT", "16")
        cfg = load_config(toml)
        assert cfg.workers.count == 16

    def test_unknown_section_ignored(self, monkeypatch):
        monkeypatch.setenv("YK_BOGUS__KEY", "value")
        cfg = load_config()  # should not raise
        assert cfg is not None

    def test_unknown_field_ignored(self, monkeypatch):
        monkeypatch.setenv("YK_WORKERS__NONEXISTENT", "value")
        cfg = load_config()  # should not raise
        assert cfg is not None
