import math
import os
from dataclasses import dataclass, field
from urllib.parse import urlsplit

REQUIRED = ("EGYM_EMAIL", "EGYM_PASSWORD", "QUESTDB_HOST")
RESET_VALUES = ("reimport", "delete-dated", "delete-tables")


class ConfigError(Exception):
    """A configuration variable is missing or invalid."""


@dataclass(frozen=True)
class Settings:
    egym_email: str
    egym_password: str = field(repr=False)
    egym_base_url: str | None
    questdb_host: str
    fetch_interval_hours: float
    fetch_overlap_days: float
    fetch_reset: str | None


def _positive(environ, name, default):
    text = environ.get(name) or default
    try:
        value = float(text)
    except ValueError:
        value = math.nan
    if not (math.isfinite(value) and value > 0):
        raise ConfigError(f"{name} must be a positive number, not {text!r}")
    return value


def _host(environ):
    value = environ["QUESTDB_HOST"]
    parts = urlsplit(value)
    try:
        port = parts.port
    except ValueError:
        port = None
    # The REST calls and the line protocol client pick different default ports, so the port is required.
    if parts.scheme not in ("http", "https") or not parts.hostname or port is None:
        raise ConfigError(f"QUESTDB_HOST must be an http or https address with a host and a port, not {value!r}")
    return value


def _reset(environ):
    value = environ.get("FETCH_RESET") or None
    if value is not None and value not in RESET_VALUES:
        raise ConfigError(f"FETCH_RESET must be one of {', '.join(RESET_VALUES)}, not {value!r}")
    return value


def load(environ=os.environ) -> Settings:
    """Read the settings; an unset or empty variable counts as not given."""
    missing = [name for name in REQUIRED if not environ.get(name)]
    if missing:
        raise ConfigError(f"Missing environment variable: {', '.join(missing)}")
    return Settings(
        egym_email=environ["EGYM_EMAIL"],
        egym_password=environ["EGYM_PASSWORD"],
        egym_base_url=environ.get("EGYM_BASE_URL") or None,
        questdb_host=_host(environ),
        fetch_interval_hours=_positive(environ, "FETCH_INTERVAL_HOURS", "24"),
        fetch_overlap_days=_positive(environ, "FETCH_OVERLAP_DAYS", "7"),
        fetch_reset=_reset(environ),
    )
