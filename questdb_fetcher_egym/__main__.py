import datetime
import functools
import logging
import sys
from urllib.parse import quote_plus

import egym

from . import config, service
from .store import Store

LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


class RedactingFormatter(logging.Formatter):
    """Replaces each secret with *** in every formatted line, tracebacks included."""

    def __init__(self, secrets):
        super().__init__(LOG_FORMAT)
        self._secrets = [secret for secret in secrets if secret]

    def format(self, record):
        text = super().format(record)
        for secret in self._secrets:
            text = text.replace(secret, "***")
        return text


def log_secrets(settings: config.Settings) -> list:
    """The values the log must never show."""
    # A failed host discovery request shows its URL, which holds the email in query form.
    return [settings.egym_email, quote_plus(settings.egym_email), settings.egym_password]


def main() -> None:
    try:
        settings = config.load()
    except config.ConfigError as error:
        raise SystemExit(str(error)) from None
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(RedactingFormatter(log_secrets(settings)))
    logging.basicConfig(level=logging.INFO, handlers=[handler], force=True)
    store = Store(settings.questdb_host)
    api_factory = functools.partial(
        egym.Api, settings.egym_email, settings.egym_password, base_url=settings.egym_base_url
    )
    service.run(
        api_factory,
        store,
        datetime.timedelta(hours=settings.fetch_interval_hours),
        datetime.timedelta(days=settings.fetch_overlap_days),
        settings.fetch_reset,
    )


if __name__ == "__main__":
    main()
