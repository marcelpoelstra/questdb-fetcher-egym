import pytest

from questdb_fetcher_egym.config import ConfigError, load

REQUIRED = {
    "EGYM_EMAIL": "member@example.com",
    "EGYM_PASSWORD": "secret",
    "QUESTDB_HOST": "http://questdb:9000",
}


def test_required_values_and_defaults():
    settings = load(REQUIRED)
    assert (settings.egym_email, settings.egym_password) == ("member@example.com", "secret")
    assert settings.questdb_host == "http://questdb:9000"
    assert settings.egym_base_url is None
    assert (settings.fetch_interval_hours, settings.fetch_overlap_days) == (24.0, 7.0)
    assert settings.fetch_reset is None


def test_optional_values():
    settings = load(
        {
            **REQUIRED,
            "EGYM_BASE_URL": "https://gym.netpulse.com",
            "FETCH_INTERVAL_HOURS": "0.5",
            "FETCH_OVERLAP_DAYS": "1.5",
        }
    )
    assert settings.egym_base_url == "https://gym.netpulse.com"
    assert (settings.fetch_interval_hours, settings.fetch_overlap_days) == (0.5, 1.5)


def test_empty_value_counts_as_unset():
    settings = load({**REQUIRED, "EGYM_BASE_URL": "", "FETCH_INTERVAL_HOURS": "", "FETCH_RESET": ""})
    assert (settings.egym_base_url, settings.fetch_interval_hours, settings.fetch_reset) == (None, 24.0, None)


@pytest.mark.parametrize("name", sorted(REQUIRED))
def test_missing_required_variable_is_named(name):
    environ = {key: value for key, value in REQUIRED.items() if key != name}
    with pytest.raises(ConfigError, match=name):
        load(environ)


@pytest.mark.parametrize("value", ["0", "-1", "abc", "nan", "inf"])
def test_invalid_number_is_named(value):
    with pytest.raises(ConfigError, match="FETCH_OVERLAP_DAYS"):
        load({**REQUIRED, "FETCH_OVERLAP_DAYS": value})


@pytest.mark.parametrize("value", ["questdb:9000", "ftp://questdb:9000", "http://", "questdb"])
def test_invalid_questdb_host_is_named(value):
    with pytest.raises(ConfigError, match="QUESTDB_HOST"):
        load({**REQUIRED, "QUESTDB_HOST": value})


def test_https_questdb_host():
    assert load({**REQUIRED, "QUESTDB_HOST": "https://questdb.example.com:9000"}).questdb_host == (
        "https://questdb.example.com:9000"
    )


@pytest.mark.parametrize("value", ["reimport", "delete-dated", "delete-tables"])
def test_reset_values(value):
    assert load({**REQUIRED, "FETCH_RESET": value}).fetch_reset == value


@pytest.mark.parametrize("value", ["delete", "delete-database"])
def test_unknown_reset_value_is_named(value):
    with pytest.raises(ConfigError, match="FETCH_RESET"):
        load({**REQUIRED, "FETCH_RESET": value})


def test_password_is_left_out_of_repr():
    assert "secret" not in repr(load(REQUIRED))


@pytest.mark.parametrize("value", ["http://questdb", "http://questdb:abc"])
def test_questdb_host_needs_a_port(value):
    with pytest.raises(ConfigError, match="QUESTDB_HOST"):
        load({**REQUIRED, "QUESTDB_HOST": value})
