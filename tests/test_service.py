import datetime
import logging

import pytest

from questdb_fetcher_egym import service
from questdb_fetcher_egym.records import EPOCH, Row
from samples import (
    ACTIVITY_LEVEL,
    BIO_AGE_SUMMARY,
    BODY_MEASUREMENTS,
    CARDIO_BLOOD_PRESSURE,
    CARDIO_RESTING_HEART_RATE,
    EMPTY_BIO_AGE_SUMMARY,
    FAVOURITES,
    GYMS,
    LATEST_BODY_METRICS,
    MUSCLE_IMBALANCES,
    NOW,
    PLANS,
    PROFILE,
    RANKING,
    STRENGTH,
    WORKOUTS,
)

UTC = datetime.timezone.utc
OVERLAP = datetime.timedelta(days=7)
INTERVAL = datetime.timedelta(hours=24)
ALL_TABLES = {
    "exercises",
    "exercise_sets",
    "body_measurements",
    "cardio_measurements",
    "strength_measurements",
    "bio_age",
    "muscle_imbalances",
    "activity_level",
    "ranking",
    "meta_gym",
    "meta_profile",
    "meta_activities",
    "meta_plans",
}
KINDS = ("workouts", "body", "cardio", "strength", "bio_age")


class FakeApi:
    """Answers with the samples for every range that touches a year listed for that kind of data."""

    def __init__(self, data_years):
        self.data_years = data_years
        self.calls = []

    def _has(self, kind, start, end):
        return any(start.year <= year <= end.year for year in self.data_years.get(kind, ()))

    def get_latest_body_metrics(self):
        self.calls.append(("get_latest_body_metrics",))
        return LATEST_BODY_METRICS

    def get_workouts(self, start, end):
        self.calls.append(("get_workouts", start, end))
        return WORKOUTS if self._has("workouts", start, end) else []

    def get_body_measurements(self, types, start, end):
        self.calls.append(("get_body_measurements", types, start, end))
        return BODY_MEASUREMENTS if self._has("body", start, end) else []

    def get_cardio_measurements(self, metric, start, end):
        self.calls.append(("get_cardio_measurements", metric, start, end))
        samples = {"BLOOD_PRESSURE": CARDIO_BLOOD_PRESSURE, "RESTING_HEART_RATE": CARDIO_RESTING_HEART_RATE}
        found = metric in samples and self._has("cardio", start, end)
        return samples[metric] if found else {"measurements": []}

    def get_strength_measurements(self, start, end):
        self.calls.append(("get_strength_measurements", start, end))
        return STRENGTH if self._has("strength", start, end) else {"strengthMeasurements": []}

    def get_bio_age_summary(self, period, shift):
        self.calls.append(("get_bio_age_summary", period, shift))
        return BIO_AGE_SUMMARY if NOW.year - shift in self.data_years.get("bio_age", ()) else EMPTY_BIO_AGE_SUMMARY

    def get_muscle_imbalances(self):
        return MUSCLE_IMBALANCES

    def get_activity_level(self):
        return ACTIVITY_LEVEL

    def get_ranking(self):
        return RANKING

    def get_gyms(self):
        return GYMS

    def get_profile(self):
        return PROFILE

    def get_favourite_activities(self):
        return FAVOURITES

    def get_available_plans(self):
        return PLANS

    def logout(self):
        self.calls.append(("logout",))

    def shifts(self):
        return [call[2] for call in self.calls if call[0] == "get_bio_age_summary"]


class FakeStore:
    def __init__(self, newest=None, marker=None, activities=()):
        self._newest = newest or {}
        self.marker = marker
        self.stored_activities = list(activities)
        self.rows = []
        self.dropped = []
        self.created = 0
        self.closed = 0
        self.events = []

    def create_tables(self):
        self.created += 1
        self.events.append("create")

    def close(self):
        self.closed += 1

    def newest(self, table):
        return self._newest.get(table)

    def reset_marker(self):
        return self.marker

    def activities(self):
        return list(self.stored_activities)

    def drop_table(self, table):
        self.dropped.append(table)

    def write(self, rows):
        self.rows += rows
        self.events.append("write")

    def tables(self):
        return {row.table for row in self.rows}

    def times(self, table):
        return [row.at for row in self.rows if row.table == table]


class StopLoop(Exception):
    pass


def test_history_search_continues_over_one_empty_year_and_stops_after_two():
    api = FakeApi({"workouts": {2026, 2024}})
    assert service.history_start(api, ["WEIGHT_KG"], NOW.date()) == datetime.date(2024, 1, 1)
    assert api.shifts() == [0, 1, 2, 3, 4]


@pytest.mark.parametrize("kind", KINDS)
def test_any_kind_of_data_starts_the_history(kind):
    api = FakeApi({kind: {2025}})
    assert service.history_start(api, ["WEIGHT_KG"], NOW.date()) == datetime.date(2025, 1, 1)


def test_history_without_any_data_starts_in_the_current_year():
    api = FakeApi({})
    assert service.history_start(api, ["WEIGHT_KG"], NOW.date()) == datetime.date(2026, 1, 1)
    assert api.shifts() == [0, 1]


def test_history_search_asks_every_kind_for_each_year():
    api = FakeApi({})
    service.history_start(api, ["WEIGHT_KG"], NOW.date())
    start, end = datetime.date(2026, 1, 1), datetime.date(2026, 12, 31)
    assert api.calls[:7] == [
        ("get_bio_age_summary", "year", 0),
        ("get_workouts", start, end),
        ("get_body_measurements", ["WEIGHT_KG"], start, end),
        ("get_cardio_measurements", "RESTING_HEART_RATE", start, end),
        ("get_cardio_measurements", "VO2MAX", start, end),
        ("get_cardio_measurements", "BLOOD_PRESSURE", start, end),
        ("get_strength_measurements", start, end),
    ]


def test_empty_store_imports_the_whole_history():
    api = FakeApi({kind: {2025, 2026} for kind in KINDS})
    store = FakeStore()
    service.run_cycle(lambda: api, store, OVERLAP, clock=lambda: NOW)
    history = datetime.date(2025, 1, 1)
    assert ("get_workouts", history, NOW) in api.calls
    assert ("get_body_measurements", ["WEIGHT_KG", "HEIGHT_CM"], history, NOW) in api.calls
    assert ("get_cardio_measurements", "BLOOD_PRESSURE", history, NOW) in api.calls
    assert ("get_strength_measurements", history, NOW) in api.calls
    assert api.shifts()[-2:] == [1, 0]
    assert store.tables() == ALL_TABLES
    assert api.calls[-1] == ("logout",)


def test_filled_store_fetches_from_the_newest_time_minus_the_overlap():
    newest = datetime.datetime(2026, 9, 20, 8, 0, tzinfo=UTC)
    api = FakeApi({kind: {2026} for kind in KINDS})
    service.run_cycle(lambda: api, FakeStore({table: newest for table in service.DATED_TABLES}), OVERLAP, clock=lambda: NOW)
    start = datetime.datetime(2026, 9, 13, 8, 0, tzinfo=UTC)
    assert [call for call in api.calls if call[0] == "get_workouts"] == [("get_workouts", start, NOW)]
    assert ("get_strength_measurements", start, NOW) in api.calls
    assert api.shifts() == [0]


def test_one_empty_table_starts_at_the_history_start_and_the_others_at_their_newest_time():
    newest = datetime.datetime(2026, 9, 20, 8, 0, tzinfo=UTC)
    filled = {table: newest for table in service.DATED_TABLES if table != "strength_measurements"}
    api = FakeApi({kind: {2025, 2026} for kind in KINDS})
    service.run_cycle(lambda: api, FakeStore(filled), OVERLAP, clock=lambda: NOW)
    assert ("get_strength_measurements", datetime.date(2025, 1, 1), NOW) in api.calls
    assert ("get_workouts", newest - OVERLAP, NOW) in api.calls


def test_snapshots_carry_the_write_time_and_metadata_the_fixed_time():
    store = FakeStore()
    service.run_cycle(lambda: FakeApi({}), store, OVERLAP, clock=lambda: NOW)
    assert store.times("activity_level") == [NOW]
    assert store.times("ranking") == [NOW]
    for table in ("meta_gym", "meta_profile", "meta_activities", "meta_plans"):
        assert set(store.times(table)) == {EPOCH}


def test_every_cycle_creates_the_tables_before_any_write():
    store = FakeStore()
    service.run_cycle(lambda: FakeApi({}), store, OVERLAP, clock=lambda: NOW)
    assert store.events[0] == "create"
    assert store.events.count("create") == 1
    assert "write" in store.events


def test_logout_follows_a_failed_cycle():
    api = FakeApi({})

    def broken(start, end):
        raise RuntimeError("boom")

    api.get_workouts = broken
    with pytest.raises(RuntimeError):
        service.run_cycle(lambda: api, FakeStore(), OVERLAP, clock=lambda: NOW)
    assert api.calls[-1] == ("logout",)


def test_run_logs_a_failed_cycle_and_runs_the_next(caplog):
    apis = []

    def factory():
        if not apis:
            apis.append(None)
            raise RuntimeError("login refused")
        apis.append(FakeApi({}))
        return apis[-1]

    sleeps = []

    def sleep(seconds):
        sleeps.append(seconds)
        if len(sleeps) == 2:
            raise StopLoop

    caplog.set_level(logging.INFO)
    with pytest.raises(StopLoop):
        service.run(factory, FakeStore(), INTERVAL, OVERLAP, clock=lambda: NOW, sleep=sleep)
    assert "Cycle failed" in caplog.text
    assert "RuntimeError: login refused" in caplog.text
    assert "Cycle finished, next cycle at 2026-09-28T06:00:00+00:00" in caplog.text
    assert apis[1].calls[-1] == ("logout",)
    assert sleeps == [86400.0, 86400.0]


def test_run_searches_the_history_once():
    apis = []

    def factory():
        apis.append(FakeApi({"workouts": {2025, 2026}}))
        return apis[-1]

    sleeps = []

    def sleep(seconds):
        sleeps.append(seconds)
        if len(sleeps) == 2:
            raise StopLoop

    with pytest.raises(StopLoop):
        service.run(factory, FakeStore(), INTERVAL, OVERLAP, clock=lambda: NOW, sleep=sleep)
    history = datetime.date(2025, 1, 1)
    assert ("get_workouts", datetime.date(2026, 1, 1), datetime.date(2026, 12, 31)) in apis[0].calls
    assert [call for call in apis[1].calls if call[0] == "get_workouts"] == [("get_workouts", history, NOW)]
    assert apis[1].shifts() == [1, 0]


@pytest.mark.parametrize("duration, expected", [(datetime.timedelta(hours=1), 82800.0), (datetime.timedelta(hours=25), 0.0)])
def test_run_sleeps_until_the_interval_after_the_cycle_start(duration, expected):
    current = [NOW]

    def factory():
        current[0] = NOW + duration
        return FakeApi({})

    sleeps = []

    def sleep(seconds):
        sleeps.append(seconds)
        raise StopLoop

    with pytest.raises(StopLoop):
        service.run(factory, FakeStore(), INTERVAL, OVERLAP, clock=lambda: current[0], sleep=sleep)
    assert sleeps == [expected]


DATED_SIX = ["exercises", "exercise_sets", "body_measurements", "cardio_measurements", "strength_measurements", "bio_age"]


@pytest.mark.parametrize(
    "reset, dropped",
    [
        ("reimport", []),
        ("delete-dated", DATED_SIX),
        ("delete-tables", sorted(ALL_TABLES)),
    ],
)
def test_reset_drops_what_its_value_names(reset, dropped):
    store = FakeStore()
    assert service.start_reset(store, reset) is True
    assert sorted(store.dropped) == sorted(dropped)


def test_start_without_reset_drops_the_marker():
    store = FakeStore(marker="delete-dated")
    assert service.start_reset(store, None) is False
    assert store.dropped == ["meta_reset"]


def test_reset_already_run_is_skipped_with_a_warning(caplog):
    store = FakeStore(marker="delete-dated")
    assert service.start_reset(store, "delete-dated") is False
    assert store.dropped == []
    assert "FETCH_RESET=delete-dated has already run; the variable can be removed" in caplog.text


def test_marker_with_another_value_lets_the_reset_run():
    store = FakeStore(marker="reimport")
    assert service.start_reset(store, "delete-dated") is True
    assert store.dropped == DATED_SIX


def test_every_table_the_reset_drops_has_upsert_keys():
    from questdb_fetcher_egym.store import MARKER_TABLE, UPSERT_KEYS

    assert set(UPSERT_KEYS) == set(service.TABLES) | {MARKER_TABLE}


def test_pending_reset_imports_every_dated_table_from_the_history_start():
    newest = datetime.datetime(2026, 9, 20, 8, 0, tzinfo=UTC)
    api = FakeApi({kind: {2025, 2026} for kind in KINDS})
    store = FakeStore({table: newest for table in service.DATED_TABLES})
    service.run_cycle(lambda: api, store, OVERLAP, clock=lambda: NOW, reset_pending=True)
    history = datetime.date(2025, 1, 1)
    assert ("get_workouts", history, NOW) in api.calls
    assert ("get_body_measurements", ["WEIGHT_KG", "HEIGHT_CM"], history, NOW) in api.calls
    assert ("get_cardio_measurements", "BLOOD_PRESSURE", history, NOW) in api.calls
    assert ("get_strength_measurements", history, NOW) in api.calls
    assert api.shifts()[-2:] == [1, 0]


def test_run_writes_the_marker_after_the_first_completed_cycle_only():
    apis = []

    def factory():
        if not apis:
            apis.append(None)
            raise RuntimeError("login refused")
        apis.append(FakeApi({"workouts": {2025, 2026}}))
        return apis[-1]

    sleeps = []

    def sleep(seconds):
        sleeps.append(seconds)
        if len(sleeps) == 3:
            raise StopLoop

    store = FakeStore({table: NOW for table in service.DATED_TABLES})
    with pytest.raises(StopLoop):
        service.run(factory, store, INTERVAL, OVERLAP, reset="delete-dated", clock=lambda: NOW, sleep=sleep)
    assert store.dropped == DATED_SIX
    assert store.rows.count(Row("meta_reset", {}, {"value": "delete-dated"}, EPOCH)) == 1
    assert ("get_workouts", datetime.date(2025, 1, 1), NOW) in apis[1].calls
    assert [call for call in apis[2].calls if call[0] == "get_workouts"] == [("get_workouts", NOW - OVERLAP, NOW)]


def test_a_failed_exercise_sets_write_leaves_exercises_unwritten():
    class FailingStore(FakeStore):
        def write(self, rows):
            if rows and rows[0].table == "exercise_sets":
                raise RuntimeError("write refused")
            super().write(rows)

    store = FailingStore()
    with pytest.raises(RuntimeError):
        service.run_cycle(lambda: FakeApi({"workouts": {2026}}), store, OVERLAP, clock=lambda: NOW)
    assert store.times("exercises") == []


def test_cardio_rows_are_written_oldest_first_across_metrics():
    store = FakeStore()
    service.run_cycle(lambda: FakeApi({"cardio": {2026}}), store, OVERLAP, clock=lambda: NOW)
    assert len(store.times("cardio_measurements")) == 3
    assert store.times("cardio_measurements") == sorted(store.times("cardio_measurements"))


def test_bio_age_rows_are_written_oldest_first_across_years():
    store = FakeStore()
    service.run_cycle(lambda: FakeApi({"bio_age": {2025, 2026}}), store, OVERLAP, clock=lambda: NOW)
    assert len(store.times("bio_age")) == 4
    assert store.times("bio_age") == sorted(store.times("bio_age"))


def test_meta_activities_are_rebuilt_from_the_stored_rows():
    stored = [{"activity_id": "999", "name": "Old Machine", "category": "EGYM_MACHINE", "favourite": True}]
    store = FakeStore(activities=stored)
    service.run_cycle(lambda: FakeApi({}), store, OVERLAP, clock=lambda: NOW)
    assert Row("meta_activities", {"activity_id": "999"}, {"name": "Old Machine", "category": "EGYM_MACHINE", "favourite": False}, EPOCH) in store.rows


def test_every_cycle_closes_the_store_also_after_a_failure():
    store = FakeStore()
    service.run_cycle(lambda: FakeApi({}), store, OVERLAP, clock=lambda: NOW)
    api = FakeApi({})

    def broken(start, end):
        raise RuntimeError("boom")

    api.get_workouts = broken
    with pytest.raises(RuntimeError):
        service.run_cycle(lambda: api, store, OVERLAP, clock=lambda: NOW)
    assert store.closed == 2


def test_start_up_retries_until_questdb_answers(caplog):
    store = FakeStore()
    failures = [ConnectionError("QuestDB not ready")]
    real_drop = store.drop_table

    def drop_table(table):
        if failures:
            raise failures.pop()
        real_drop(table)

    store.drop_table = drop_table
    sleeps = []

    def sleep(seconds):
        sleeps.append(seconds)
        if len(sleeps) == 2:
            raise StopLoop

    with pytest.raises(StopLoop):
        service.run(lambda: FakeApi({}), store, INTERVAL, OVERLAP, clock=lambda: NOW, sleep=sleep)
    assert sleeps == [60, 86400.0]
    assert "Start-up failed, next try in 60 seconds" in caplog.text
    assert store.dropped == ["meta_reset"]
    assert store.times("ranking") == [NOW]


def test_the_marker_write_is_followed_by_closing_the_store():
    sleeps = []

    def sleep(seconds):
        sleeps.append(seconds)
        raise StopLoop

    store = FakeStore()
    with pytest.raises(StopLoop):
        service.run(lambda: FakeApi({}), store, INTERVAL, OVERLAP, reset="reimport", clock=lambda: NOW, sleep=sleep)
    assert store.rows[-1] == Row("meta_reset", {}, {"value": "reimport"}, EPOCH)
    assert store.closed == 2


def test_a_history_start_found_by_a_failed_cycle_is_kept():
    apis = []

    def factory():
        api = FakeApi({"workouts": {2025, 2026}})
        if not apis:
            def broken():
                raise RuntimeError("ranking unavailable")

            api.get_ranking = broken
        apis.append(api)
        return api

    sleeps = []

    def sleep(seconds):
        sleeps.append(seconds)
        if len(sleeps) == 2:
            raise StopLoop

    with pytest.raises(StopLoop):
        service.run(factory, FakeStore(), INTERVAL, OVERLAP, clock=lambda: NOW, sleep=sleep)
    assert len(apis[0].shifts()) > 2
    assert apis[1].shifts() == [1, 0]
