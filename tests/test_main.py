import logging
import sys

import pytest

from questdb_fetcher_egym import __main__ as main_module
from questdb_fetcher_egym.__main__ import RedactingFormatter, log_secrets, main
from questdb_fetcher_egym.config import load

REQUIRED = ("EGYM_EMAIL", "EGYM_PASSWORD", "QUESTDB_HOST")


def test_formatter_hides_every_secret_in_message_and_traceback():
    formatter = RedactingFormatter(["member+gym@example.com", "member%2Bgym%40example.com", "secret", None])
    record = logging.LogRecord(
        "test", logging.ERROR, __file__, 1, "login as %s with %s", ("member+gym@example.com", "secret"), None
    )
    try:
        raise ConnectionError("Max retries exceeded with url: /np/egym/v1.0/users?email=member%2Bgym%40example.com")
    except ConnectionError:
        record.exc_info = sys.exc_info()
    text = formatter.format(record)
    assert "member" not in text
    assert "secret" not in text
    assert "email=***" in text


def test_log_secrets_cover_the_email_in_url_form_and_the_password():
    settings = load(
        {"EGYM_EMAIL": "member+gym@example.com", "EGYM_PASSWORD": "secret", "QUESTDB_HOST": "http://questdb:9000"}
    )
    message = "users?email=member%2Bgym%40example.com as member+gym@example.com with secret"
    text = RedactingFormatter(log_secrets(settings)).format(
        logging.LogRecord("test", logging.ERROR, __file__, 1, message, None, None)
    )
    assert "member" not in text
    assert "secret" not in text


def test_missing_configuration_stops_with_the_variable_names(monkeypatch):
    for name in REQUIRED:
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(SystemExit, match="EGYM_EMAIL, EGYM_PASSWORD, QUESTDB_HOST"):
        main()


def test_main_logs_through_the_redacting_formatter(monkeypatch, capsys):
    monkeypatch.setenv("EGYM_EMAIL", "member+gym@example.com")
    monkeypatch.setenv("EGYM_PASSWORD", "secret")
    monkeypatch.setenv("QUESTDB_HOST", "http://questdb:9000")
    for name in ("EGYM_BASE_URL", "FETCH_INTERVAL_HOURS", "FETCH_OVERLAP_DAYS", "FETCH_RESET"):
        monkeypatch.delenv(name, raising=False)

    def fake_run(*args):
        logging.getLogger("questdb_fetcher_egym.service").error(
            "users?email=member%2Bgym%40example.com as member+gym@example.com with secret"
        )

    monkeypatch.setattr(main_module.service, "run", fake_run)
    root = logging.getLogger()
    handlers, level = root.handlers[:], root.level
    try:
        main()
    finally:
        for handler in root.handlers[:]:
            root.removeHandler(handler)
        for handler in handlers:
            root.addHandler(handler)
        root.setLevel(level)
    output = capsys.readouterr().out
    assert "users?email=*** as *** with ***" in output
    assert "member" not in output
    assert "secret" not in output
