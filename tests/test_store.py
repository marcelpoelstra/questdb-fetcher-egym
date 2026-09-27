import datetime

import pytest
import requests

from questdb_fetcher_egym import store as store_module
from questdb_fetcher_egym.records import EPOCH, Row
from questdb_fetcher_egym.store import UPSERT_KEYS, QueryError, Store, create_statement

UTC = datetime.timezone.utc


class FakeRest:
    """Answers GET /exec with the given bodies in turn and records the queries."""

    def __init__(self, *bodies):
        self.bodies = list(bodies)
        self.calls = []

    def __call__(self, url, params, timeout):
        self.calls.append((url, params["query"], timeout))
        body = self.bodies.pop(0) if self.bodies else {"ddl": "OK"}

        class Response:
            def json(self):
                return body

        return Response()


class FakeSender:
    confs = []
    calls = []

    @classmethod
    def from_conf(cls, conf):
        cls.confs.append(conf)
        return cls()

    def establish(self):
        FakeSender.calls.append("establish")

    def row(self, table, symbols, columns, at):
        FakeSender.calls.append((table, symbols, columns, at))

    def flush(self):
        FakeSender.calls.append("flush")

    def close(self, flush):
        FakeSender.calls.append(("close", flush))


def answer(names, *rows):
    return {"columns": [{"name": name, "type": "VARCHAR"} for name in names], "dataset": [list(row) for row in rows]}


@pytest.fixture
def rest(monkeypatch):
    def install(*bodies):
        fake = FakeRest(*bodies)
        monkeypatch.setattr(requests, "get", fake)
        return fake

    return install


def test_create_statement_with_keys():
    assert create_statement("exercise_sets", ("exercise_id", "set_number")) == (
        "CREATE TABLE IF NOT EXISTS exercise_sets (timestamp TIMESTAMP, exercise_id SYMBOL, set_number SYMBOL) "
        "TIMESTAMP(timestamp) PARTITION BY MONTH WAL DEDUP UPSERT KEYS(timestamp, exercise_id, set_number)"
    )


def test_create_statement_without_keys():
    assert create_statement("ranking", ()) == (
        "CREATE TABLE IF NOT EXISTS ranking (timestamp TIMESTAMP) "
        "TIMESTAMP(timestamp) PARTITION BY MONTH WAL DEDUP UPSERT KEYS(timestamp)"
    )


def test_create_statement_with_the_columns_read_back():
    assert create_statement("meta_activities", ("activity_id",), {"name": "VARCHAR", "favourite": "BOOLEAN"}) == (
        "CREATE TABLE IF NOT EXISTS meta_activities (timestamp TIMESTAMP, activity_id SYMBOL, name VARCHAR, favourite BOOLEAN) "
        "TIMESTAMP(timestamp) PARTITION BY MONTH WAL DEDUP UPSERT KEYS(timestamp, activity_id)"
    )


def test_create_tables_sends_one_statement_per_table(rest):
    fake = rest()
    Store("http://questdb:9000/").create_tables()
    assert [query for _, query, _ in fake.calls] == [
        create_statement(table, keys, store_module.READ_COLUMNS.get(table))
        for table, keys in store_module.UPSERT_KEYS.items()
    ]
    assert "meta_reset (timestamp TIMESTAMP, value VARCHAR)" in fake.calls[-1][1]
    assert (
        "CREATE TABLE IF NOT EXISTS meta_activities (timestamp TIMESTAMP, activity_id SYMBOL, name VARCHAR, "
        "category VARCHAR, favourite BOOLEAN) TIMESTAMP(timestamp) PARTITION BY MONTH WAL DEDUP UPSERT KEYS(timestamp, activity_id)"
    ) in [query for _, query, _ in fake.calls]
    assert {url for url, _, _ in fake.calls} == {"http://questdb:9000/exec"}
    assert {timeout for _, _, timeout in fake.calls} == {30}


def test_newest(rest):
    fake = rest(answer(["newest"], ["2026-09-26T21:59:59.250000Z"]))
    assert Store("http://questdb:9000").newest("exercises") == datetime.datetime(2026, 9, 26, 21, 59, 59, 250000, UTC)
    assert fake.calls[0][1] == "SELECT max(timestamp) AS newest FROM exercises"


@pytest.mark.parametrize(
    "body",
    [
        answer(["newest"]),
        answer(["newest"], [None]),
        {"query": "SELECT", "error": "table does not exist [table=exercises]", "position": 37},
    ],
)
def test_newest_of_an_empty_or_missing_table_is_none(rest, body):
    rest(body)
    assert Store("http://questdb:9000").newest("exercises") is None


def test_other_query_errors_are_raised(rest):
    rest({"query": "SELECT", "error": "unexpected token", "position": 7})
    with pytest.raises(QueryError, match="unexpected token"):
        Store("http://questdb:9000").newest("exercises")


def test_write_sends_every_row_through_one_sender(monkeypatch):
    FakeSender.confs, FakeSender.calls = [], []
    monkeypatch.setattr(store_module.questdb, "Sender", FakeSender)
    row = Row("meta_reset", {}, {"value": "reimport"}, EPOCH)
    store = Store("http://questdb:9000/")
    store.write([row, row])
    store.write([row])
    written = ("meta_reset", {}, {"value": "reimport"}, EPOCH)
    assert FakeSender.confs == ["http::addr=questdb:9000;"]
    assert FakeSender.calls == ["establish", written, written, "flush", written, "flush"]


def test_https_host_gives_an_https_sender(monkeypatch):
    FakeSender.confs, FakeSender.calls = [], []
    monkeypatch.setattr(store_module.questdb, "Sender", FakeSender)
    Store("https://questdb.example.com:9000").write([])
    assert FakeSender.confs == ["https::addr=questdb.example.com:9000;"]


def test_drop_table(rest):
    fake = rest()
    Store("http://questdb:9000").drop_table("exercises")
    assert fake.calls[0][1] == "DROP TABLE IF EXISTS exercises"


def test_reset_marker(rest):
    fake = rest(answer(["value"], ["delete-dated"]))
    assert Store("http://questdb:9000").reset_marker() == "delete-dated"
    assert fake.calls[0][1] == "SELECT value FROM meta_reset"


@pytest.mark.parametrize("body", [answer(["value"]), {"error": "table does not exist [table=meta_reset]"}])
def test_missing_reset_marker_gives_none(rest, body):
    rest(body)
    assert Store("http://questdb:9000").reset_marker() is None


def test_activities(rest):
    fake = rest(answer(["activity_id", "name", "category", "favourite"], ["581", "EGYM Leg Press", "EGYM_MACHINE", True]))
    assert Store("http://questdb:9000").activities() == [
        {"activity_id": "581", "name": "EGYM Leg Press", "category": "EGYM_MACHINE", "favourite": True}
    ]
    assert fake.calls[0][1] == "SELECT activity_id, name, category, favourite FROM meta_activities"


def test_missing_activities_table_gives_no_rows(rest):
    rest({"error": "table does not exist [table=meta_activities]"})
    assert Store("http://questdb:9000").activities() == []


@pytest.mark.parametrize("action", ["close", "drop_table"])
def test_close_and_drop_discard_the_sender(monkeypatch, rest, action):
    FakeSender.confs, FakeSender.calls = [], []
    monkeypatch.setattr(store_module.questdb, "Sender", FakeSender)
    rest()
    store = Store("http://questdb:9000")
    store.write([])
    store.drop_table("exercises") if action == "drop_table" else store.close()
    store.write([])
    assert FakeSender.confs == ["http::addr=questdb:9000;"] * 2
    assert FakeSender.calls == ["establish", "flush", ("close", False), "establish", "flush"]


def test_close_without_a_sender_does_nothing():
    Store("http://questdb:9000").close()


def test_a_failed_establish_leaves_no_sender(monkeypatch):
    class Unreachable(FakeSender):
        def establish(self):
            raise ConnectionError("refused")

    FakeSender.confs, FakeSender.calls = [], []
    monkeypatch.setattr(store_module.questdb, "Sender", Unreachable)
    store = Store("http://questdb:9000")
    with pytest.raises(ConnectionError):
        store.write([])
    monkeypatch.setattr(store_module.questdb, "Sender", FakeSender)
    store.write([])
    assert FakeSender.confs == ["http::addr=questdb:9000;"] * 2
    assert FakeSender.calls == ["establish", "flush"]


def test_upsert_keys_follow_the_design():
    assert UPSERT_KEYS == {
        "exercises": ("exercise_id",),
        "exercise_sets": ("exercise_id", "set_number"),
        "body_measurements": ("measurement_id", "type"),
        "cardio_measurements": ("measurement_id", "type"),
        "strength_measurements": ("measurement_id",),
        "bio_age": ("type",),
        "muscle_imbalances": ("body_region", "agonist_muscle", "antagonist_muscle"),
        "activity_level": (),
        "ranking": (),
        "meta_gym": ("gym_id",),
        "meta_profile": ("exerciser_id",),
        "meta_activities": ("activity_id",),
        "meta_plans": ("plan_id",),
        "meta_reset": (),
    }
