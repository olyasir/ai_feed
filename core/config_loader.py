import os
from pathlib import Path
from typing import Any

import yaml


_config: dict[str, Any] | None = None


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    global _config
    if _config is not None:
        return _config

    if path is None:
        path = Path(__file__).parent.parent / "config.yaml"
    else:
        path = Path(path)

    with open(path) as f:
        _config = yaml.safe_load(f)

    # Environment variable overrides
    if client_id := os.environ.get("REDDIT_CLIENT_ID"):
        _config["reddit"]["client_id"] = client_id
    if client_secret := os.environ.get("REDDIT_CLIENT_SECRET"):
        _config["reddit"]["client_secret"] = client_secret
    if bearer := os.environ.get("TWITTER_BEARER_TOKEN"):
        _config["twitter"]["bearer_token"] = bearer
        _config["twitter"]["enabled"] = True

    return _config


def get_config() -> dict[str, Any]:
    if _config is None:
        return load_config()
    return _config
