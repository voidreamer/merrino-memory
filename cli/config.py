"""Shared configuration loader for agent-memory CLI tools."""

import os
import sys
from pathlib import Path

import yaml

DEFAULTS = {
    "agent_id": "default",
    "ollama_url": "http://localhost:11434/api/embeddings",
    "model": "nomic-embed-text",
    "schema": "agent_memory",
    "sources": [],
}


def load_config(cli_config_path: str | None = None) -> dict:
    """Load config from CLI arg, AGENT_MEMORY_CONFIG env var, or ./config.yaml."""
    path = (
        cli_config_path
        or os.environ.get("AGENT_MEMORY_CONFIG")
        or (str(Path("config.yaml")) if Path("config.yaml").exists() else None)
    )
    if not path:
        print("Error: No config found. Set AGENT_MEMORY_CONFIG, pass --config, or create config.yaml", file=sys.stderr)
        sys.exit(1)

    with open(path) as f:
        cfg = yaml.safe_load(f)

    for k, v in DEFAULTS.items():
        cfg.setdefault(k, v)

    if "db_url" not in cfg:
        print("Error: db_url is required in config", file=sys.stderr)
        sys.exit(1)

    return cfg


def parse_config_arg(args: list[str]) -> tuple[str | None, list[str]]:
    """Extract --config <path> from args, return (path, remaining_args)."""
    if "--config" in args:
        idx = args.index("--config")
        path = args[idx + 1]
        remaining = args[:idx] + args[idx + 2:]
        return path, remaining
    return None, args
