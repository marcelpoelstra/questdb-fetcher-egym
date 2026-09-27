import datetime
import os
import time

import pytest
import requests

from questdb_fetcher_egym import records
from questdb_fetcher_egym.store import UPSERT_KEYS, Store
from samples import (
    ACTIVITY_LEVEL,
    BIO_AGE_SUMMARY,
    BODY_MEASUREMENTS,
    CARDIO_BLOOD_PRESSURE,
    EXERCISE_MACHINE,
    FAVOURITES,
    GYMS,
    MUSCLE_IMBALANCES,
    NOW,
    PLANS,
    PROFILE,
    RANKING,
    STRENGTH,
    WORKOUTS,
)

HOST = os.environ.get("QUESTDB_TEST_HOST")

pytestmark = pytest.mark.skipif(not HOST, reason="QUESTDB_TEST_HOST is not set")


def all_rows():
    return {
        "exercises": records.exercises(WORKOUTS),
        "exercise_sets": records.exercise_sets(WORKOUTS),
        "body_measurements": records.body_measurements(BODY_MEASUREMENTS),
        "cardio_measurements": records.cardio_measurements(CARDIO_BLOOD_PRESSURE),
        "strength_measurements": records.strength_measurements(STRENGTH),
        "bio_age": records.bio_age(BIO_AGE_SUMMARY),
        "muscle_imbalances": records.muscle_imbalances(MUSCLE_IMBALANCES),
        "activity_level": records.activity_level(ACTIVITY_LEVEL, NOW),
        "ranking": records.ranking(RANKING, NOW),
        "meta_gym": records.meta_gym(GYMS),
        "meta_profile": records.meta_profile(PROFILE),
        "meta_activities": records.meta_activities([], WORKOUTS, STRENGTH, FAVOURITES),
        "meta_plans": records.meta_plans(PLANS),
    }


def query(sql):
    return requests.get(f"{HOST}/exec", params={"query": sql}, timeout=30).json()["dataset"]


def count(table):
    return query(f"SELECT count() AS n FROM {table}")[0][0]


def wait_for(check, expected):
    """QuestDB applies writes asynchronously: wait up to 10 seconds for `check()` to give `expected`."""
    deadline = time.monotonic() + 10
    while True:
        value = check()
        if value == expected or time.monotonic() > deadline:
            return value
        time.sleep(0.2)


@pytest.fixture
def store():
    store = Store(HOST)
    for table in UPSERT_KEYS:
        store.drop_table(table)
    store.create_tables()
    yield store
    for table in UPSERT_KEYS:
        store.drop_table(table)


def test_every_table_is_written_and_read_back(store):
    tables = all_rows()
    for rows in tables.values():
        store.write(rows)
    for table, rows in tables.items():
        assert wait_for(lambda: count(table), len(rows)) == len(rows), table


def test_newest_time(store):
    assert store.newest("exercises") is None
    store.write(records.exercises(WORKOUTS))
    expected = datetime.datetime(2026, 7, 15, 16, 30, tzinfo=datetime.timezone.utc)
    assert wait_for(lambda: store.newest("exercises"), expected) == expected


def test_a_row_written_again_with_the_same_keys_replaces_the_stored_one(store):
    store.write(records.bio_age(BIO_AGE_SUMMARY))
    assert wait_for(lambda: count("bio_age"), 2) == 2
    store.write(records.bio_age({**BIO_AGE_SUMMARY, "totalBioAge": [{"date": "2026-01-01", "value": 44}]}))
    total = """SELECT value FROM bio_age WHERE "type" = 'total'"""
    assert wait_for(lambda: query(total), [[44]]) == [[44]]
    assert count("bio_age") == 2


def test_drop_table(store):
    store.write(records.exercises(WORKOUTS))
    assert wait_for(lambda: count("exercises"), 2) == 2
    store.drop_table("exercises")
    store.drop_table("never_created")
    assert store.newest("exercises") is None
    store.create_tables()
    assert count("exercises") == 0


def test_reset_marker(store):
    assert store.reset_marker() is None
    store.drop_table("meta_reset")
    assert store.reset_marker() is None
    store.create_tables()
    store.write(records.meta_reset("reimport"))
    assert wait_for(store.reset_marker, "reimport") == "reimport"
    store.write(records.meta_reset("delete-dated"))
    assert wait_for(store.reset_marker, "delete-dated") == "delete-dated"
    assert count("meta_reset") == 1
    store.drop_table("meta_reset")
    assert store.reset_marker() is None


def test_meta_activities_are_rebuilt_from_the_stored_rows(store):
    assert store.activities() == []
    store.write(records.meta_activities([], WORKOUTS, STRENGTH, FAVOURITES))
    assert wait_for(lambda: len(store.activities()), 4) == 4
    store.write(records.meta_activities(store.activities(), [], {"strengthMeasurements": []}, []))
    expected = {
        "997": ("EGYM Leg Curl", None, False),
        "581": ("EGYM Leg Press", "EGYM_MACHINE", False),
        "1120": ("Walking Outdoor", "CARDIO_OUTDOOR", False),
        "1286": ("Workout (General)", "SPORT", False),
    }

    def stored():
        return {row["activity_id"]: (row["name"], row["category"], row["favourite"]) for row in store.activities()}

    assert wait_for(stored, expected) == expected


def test_two_records_at_the_same_time_stay_two_rows(store):
    twin = {**EXERCISE_MACHINE, "id": 1003}
    workouts = [{"completedAt": twin["completedAt"], "timezone": twin["timezone"], "exercises": [EXERCISE_MACHINE, twin]}]
    store.write(records.exercises(workouts))
    store.write(records.body_measurements(BODY_MEASUREMENTS + [{**BODY_MEASUREMENTS[0], "id": 2002}]))
    assert wait_for(lambda: count("exercises"), 2) == 2
    assert wait_for(lambda: count("body_measurements"), 4) == 4
