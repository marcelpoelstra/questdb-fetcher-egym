import datetime
from zoneinfo import ZoneInfo

import pytest

from questdb_fetcher_egym import records
from questdb_fetcher_egym.records import EPOCH, Row
from samples import (
    ACTIVITY_LEVEL,
    BIO_AGE_SUMMARY,
    BODY_MEASUREMENTS,
    CARDIO_BLOOD_PRESSURE,
    CARDIO_RESTING_HEART_RATE,
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

UTC = datetime.timezone.utc
MACHINE_TIME = datetime.datetime(2026, 1, 15, 17, 30, 0, 250000, UTC)
WALK_TIME = datetime.datetime(2026, 7, 15, 16, 30, tzinfo=UTC)
MACHINE_TAGS = {"exercise_id": "1001", "activity_id": "581", "activity": "EGYM Leg Press", "category": "EGYM_MACHINE"}
WALK_TAGS = {"exercise_id": "1002", "activity_id": "1120", "activity": "Walking Outdoor", "category": "CARDIO_OUTDOOR"}


@pytest.mark.parametrize(
    "value, zone, expected",
    [
        ("2026-01-15T18:30:00.25", "Europe/Berlin", datetime.datetime(2026, 1, 15, 17, 30, 0, 250000, UTC)),
        ("2026-07-15T18:30:00", "Europe/Amsterdam", datetime.datetime(2026, 7, 15, 16, 30, tzinfo=UTC)),
        ("2021-06-18T12:00:00", "CET", datetime.datetime(2021, 6, 18, 10, 0, tzinfo=UTC)),
        ("2026-09-27T09:21:02.464", None, datetime.datetime(2026, 9, 27, 9, 21, 2, 464000, UTC)),
        ("2026-03-02T05:28:53.12Z", None, datetime.datetime(2026, 3, 2, 5, 28, 53, 120000, UTC)),
        ("2020-02-24T15:02:26.7Z", None, datetime.datetime(2020, 2, 24, 15, 2, 26, 700000, UTC)),
        ("2026-08-25T05:53:49Z", None, datetime.datetime(2026, 8, 25, 5, 53, 49, tzinfo=UTC)),
        ("2026-01-01", None, datetime.datetime(2026, 1, 1, tzinfo=UTC)),
        ("2026-09-26T21:59:59.000000Z", None, datetime.datetime(2026, 9, 26, 21, 59, 59, tzinfo=UTC)),
    ],
)
def test_parse_time(value, zone, expected):
    parsed = records.parse_time(value, ZoneInfo(zone)) if zone else records.parse_time(value)
    assert parsed == expected
    assert parsed.tzinfo == UTC


def test_exercises():
    assert records.exercises(WORKOUTS) == [
        Row(
            "exercises",
            {**MACHINE_TAGS, "source_type": "FITNESS_MACHINE_SOURCE"},
            {"points": 12, "kilocalories": 15.0},
            MACHINE_TIME,
        ),
        Row(
            "exercises",
            {**WALK_TAGS, "source_type": "CONNECTED_APP", "source": "WITHINGS"},
            {"points": 70, "kilocalories": 88.5, "total_duration": 1800, "total_distance": 2500.0, "avg_speed": 1.4},
            WALK_TIME,
        ),
    ]


def test_values_keep_their_type():
    exercise = {**EXERCISE_MACHINE, "points": 12.0, "kiloCalories": 15}
    workouts = [{"completedAt": exercise["completedAt"], "timezone": exercise["timezone"], "exercises": [exercise]}]
    columns = records.exercises(workouts)[0].columns
    assert type(columns["points"]) is int
    assert type(columns["kilocalories"]) is float


def test_exercise_sets():
    rep_set = {"set_type": "REP_BASED", "training_method": "REGULAR_REPBASED", "side_mode": "BOTH"}
    assert records.exercise_sets(WORKOUTS) == [
        Row("exercise_sets", {**MACHINE_TAGS, **rep_set, "set_number": "1"}, {"reps": 12, "weight": 50.0, "duration": 60}, MACHINE_TIME),
        Row("exercise_sets", {**MACHINE_TAGS, **rep_set, "set_number": "2"}, {"reps": 10, "weight": 52.5, "duration": 55}, MACHINE_TIME),
        Row(
            "exercise_sets",
            {**WALK_TAGS, "set_type": "TIME_BASED", "set_number": "1"},
            {"duration": 1800, "distance": 2500.0, "speed": 1.4},
            WALK_TIME,
        ),
    ]


def test_body_measurements():
    time = datetime.datetime(2026, 2, 1, 7, 15, 30, 500000, UTC)
    assert records.body_measurements(BODY_MEASUREMENTS) == [
        Row(
            "body_measurements",
            {"measurement_id": "2001", "type": "WEIGHT_KG", "source": "MANUAL"},
            {"value": 80.5, "value_interpretation": "UNDEFINED"},
            time,
        ),
        Row("body_measurements", {"measurement_id": "2001", "type": "HEIGHT_CM", "source": "MANUAL"}, {"value": 180.0}, time),
    ]


def test_cardio_measurements():
    time = datetime.datetime(2026, 3, 1, 6, 30, tzinfo=UTC)
    tags = {"measurement_id": "3001", "source": "MANUAL"}
    assert records.cardio_measurements(CARDIO_BLOOD_PRESSURE) == [
        Row("cardio_measurements", {**tags, "type": "SYSTOLIC_PRESSURE"}, {"value": 125.0}, time),
        Row("cardio_measurements", {**tags, "type": "DIASTOLIC_PRESSURE"}, {"value": 80.0}, time),
    ]


def test_strength_measurements():
    assert records.strength_measurements(STRENGTH) == [
        Row(
            "strength_measurements",
            {"measurement_id": "4001", "activity_id": "997", "activity": "EGYM Leg Curl", "body_region": "LOWER", "source": "FITNESS_MACHINE"},
            {"strength": 70, "set_reps": 1, "set_weight": 70.5},
            datetime.datetime(2026, 4, 1, 16, 22, 53, 700000, UTC),
        )
    ]


def test_bio_age():
    assert records.bio_age(BIO_AGE_SUMMARY) == [
        Row("bio_age", {"type": "total"}, {"value": 45}, datetime.datetime(2026, 1, 1, tzinfo=UTC)),
        Row("bio_age", {"type": "muscle"}, {"value": 40}, datetime.datetime(2026, 2, 1, tzinfo=UTC)),
    ]


def test_muscle_imbalances():
    assert records.muscle_imbalances(MUSCLE_IMBALANCES) == [
        Row(
            "muscle_imbalances",
            {"body_region": "LOWER", "agonist_muscle": "QUADRICEPS", "antagonist_muscle": "HAMSTRING"},
            {
                "position": 3900.5,
                "optimal_range_start": 4000.0,
                "optimal_range_end": 6000.0,
                "range_size": 10000.0,
                "agonist_strength": 95,
                "antagonist_strength": 70,
                "agonist_activity_id": 994,
                "antagonist_activity_id": 997,
            },
            datetime.datetime(2026, 7, 1, 16, 21, 21, 48000, UTC),
        )
    ]


def test_activity_level_at_snapshot_time():
    assert records.activity_level(ACTIVITY_LEVEL, NOW) == [
        Row("activity_level", {"level": "gold"}, {"points": 1000, "days_left": 17, "goal": 3900, "maintain_points": 2300}, NOW)
    ]


def test_ranking_at_snapshot_time():
    assert records.ranking(RANKING, NOW) == [
        Row("ranking", {}, {"rank": 30, "points": 2500, "average_rank": 31, "total_users": 170}, NOW)
    ]


def test_meta_gym():
    assert records.meta_gym(GYMS) == [
        Row(
            "meta_gym",
            {"gym_id": "00000000-0000-0000-0000-00000000aaaa"},
            {"name": "Example Gym", "timezone": "Europe/Berlin", "url": "https://gym.example.com/"},
            EPOCH,
        )
    ]


def test_meta_profile():
    assert records.meta_profile(PROFILE) == [
        Row(
            "meta_profile",
            {"exerciser_id": "00000000-0000-0000-0000-000000000001"},
            {"first_name": "Alex", "last_name": "Example", "birthday": "05/01/1980", "gender": "M"},
            EPOCH,
        )
    ]


def test_meta_activities():
    assert records.meta_activities([], WORKOUTS, STRENGTH, FAVOURITES) == [
        Row("meta_activities", {"activity_id": "997"}, {"name": "EGYM Leg Curl", "favourite": False}, EPOCH),
        Row("meta_activities", {"activity_id": "581"}, {"name": "EGYM Leg Press", "category": "EGYM_MACHINE", "favourite": False}, EPOCH),
        Row("meta_activities", {"activity_id": "1120"}, {"name": "Walking Outdoor", "category": "CARDIO_OUTDOOR", "favourite": False}, EPOCH),
        Row("meta_activities", {"activity_id": "1286"}, {"name": "Workout (General)", "category": "SPORT", "favourite": True}, EPOCH),
    ]


def test_meta_activities_prefer_the_workout_name_over_the_strength_label():
    strength = {"strengthMeasurements": [{**STRENGTH["strengthMeasurements"][0], "activity": {"activityId": 581, "label": "Leg Press"}}]}
    assert records.meta_activities([], WORKOUTS, strength, []) == [
        Row("meta_activities", {"activity_id": "581"}, {"name": "EGYM Leg Press", "category": "EGYM_MACHINE", "favourite": False}, EPOCH),
        Row("meta_activities", {"activity_id": "1120"}, {"name": "Walking Outdoor", "category": "CARDIO_OUTDOOR", "favourite": False}, EPOCH),
    ]


def test_meta_activities_keep_stored_rows_and_follow_the_current_favourites():
    stored = [
        {"activity_id": "555", "name": "Old Machine", "category": "EGYM_MACHINE", "favourite": True},
        {"activity_id": "997", "name": "EGYM Leg Curl", "category": "EGYM_MACHINE", "favourite": False},
    ]
    assert records.meta_activities(stored, [], STRENGTH, [FAVOURITES[0]]) == [
        Row("meta_activities", {"activity_id": "555"}, {"name": "Old Machine", "category": "EGYM_MACHINE", "favourite": False}, EPOCH),
        Row("meta_activities", {"activity_id": "997"}, {"name": "EGYM Leg Curl", "category": "EGYM_MACHINE", "favourite": False}, EPOCH),
        Row("meta_activities", {"activity_id": "1286"}, {"name": "Workout (General)", "category": "SPORT", "favourite": True}, EPOCH),
    ]


def test_meta_reset():
    assert records.meta_reset("delete-dated") == [Row("meta_reset", {}, {"value": "delete-dated"}, EPOCH)]


def test_meta_plans():
    assert records.meta_plans(PLANS) == [
        Row("meta_plans", {"plan_id": "5001"}, {"name": "My training", "type": "USER_TRAINING_PLAN", "group_type": "USER_OWN"}, EPOCH)
    ]


NEWER_BODY = {**BODY_MEASUREMENTS[0], "id": 2002, "createdAt": "2026-03-01T07:00:00"}
NEWER_STRENGTH = {**STRENGTH["strengthMeasurements"][0], "id": 4002, "createdAt": "2026-05-01T16:00:00Z"}


@pytest.mark.parametrize(
    "rows",
    [
        records.exercises(list(reversed(WORKOUTS))),
        records.exercise_sets(list(reversed(WORKOUTS))),
        records.body_measurements([NEWER_BODY] + BODY_MEASUREMENTS),
        records.cardio_measurements(
            {"measurements": CARDIO_RESTING_HEART_RATE["measurements"] + CARDIO_BLOOD_PRESSURE["measurements"]}
        ),
        records.strength_measurements({"strengthMeasurements": [NEWER_STRENGTH] + STRENGTH["strengthMeasurements"]}),
        records.bio_age(
            {
                "totalBioAge": [{"date": "2026-02-01", "value": 44}, {"date": "2026-01-01", "value": 45}],
                "muscleBioAge": [{"date": "2025-11-01", "value": 40}],
            }
        ),
    ],
    ids=["exercises", "exercise_sets", "body_measurements", "cardio_measurements", "strength_measurements", "bio_age"],
)
def test_dated_rows_are_oldest_first(rows):
    times = [row.at for row in rows]
    assert len(set(times)) > 1
    assert times == sorted(times)
