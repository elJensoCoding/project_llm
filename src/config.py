"""Zentrale Konfiguration: lädt pllm_config.yaml und stellt Werte bereit."""
from __future__ import annotations

import os
from pathlib import Path

import yaml

_DEFAULT_CONFIG_FILE = Path("pllm_config.yaml")

_DEFAULTS: dict = {
    "database": {
        "path":         None,           # None = in-memory + Parquet-Views
        "csv_dir":      "data/csv",
        "parquet_dir":  "data/parquet",
        "profiles_dir": "data/profiles",
    },
    "llm": {
        "model": "qwen2.5-coder:7b",
    },
    "app": {
        "port": 8080,
        "host": "127.0.0.1",
    },
    "prompt": {
        "system_role":  None,
        "extra_rules":  [],
        "examples":     [],
    },
}

_config: dict = {}


def load(path: Path | None = None) -> dict:
    """Lädt die Konfigurationsdatei. Env-Variablen überschreiben Datei-Werte."""
    global _config
    import copy
    _config = copy.deepcopy(_DEFAULTS)

    config_path = path or _DEFAULT_CONFIG_FILE
    if config_path.exists():
        with open(config_path, encoding="utf-8") as f:
            file_cfg = yaml.safe_load(f) or {}
        _deep_merge(_config, file_cfg)

    # Env-Variablen haben höchste Priorität
    if os.environ.get("PLLM_DB"):
        _config["database"]["path"] = os.environ["PLLM_DB"]
    if os.environ.get("PLLM_MODEL"):
        _config["llm"]["model"] = os.environ["PLLM_MODEL"]

    return _config


def get() -> dict:
    """Gibt die geladene Konfiguration zurück (leere Defaults wenn load() noch nicht aufgerufen)."""
    return _config or load()


def db_path() -> str | None:
    return get()["database"].get("path")


def csv_dir() -> Path:
    return Path(get()["database"]["csv_dir"])


def parquet_dir() -> Path:
    return Path(get()["database"]["parquet_dir"])


def profiles_dir() -> Path:
    return Path(get()["database"]["profiles_dir"])


def model() -> str:
    return get()["llm"]["model"]


def port() -> int:
    return int(get()["app"]["port"])


def host() -> str:
    return get()["app"]["host"]


def system_role() -> str | None:
    return get()["prompt"].get("system_role") or None


def extra_rules() -> list[str]:
    return get()["prompt"].get("extra_rules") or []


def value_inventories() -> list[dict]:
    """Liste von {label, sql, hint?} — zur Laufzeit aus der DB laden."""
    return get().get("value_inventories") or []


def prompt_examples() -> list[dict]:
    return get()["prompt"].get("examples") or []


def _deep_merge(base: dict, override: dict) -> None:
    """Merged override rekursiv in base (in-place)."""
    for key, val in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(val, dict):
            _deep_merge(base[key], val)
        else:
            base[key] = val
