import datetime
from typing import NamedTuple
from zoneinfo import ZoneInfo

UTC = datetime.timezone.utc
EPOCH = datetime.datetime(1970, 1, 1, tzinfo=UTC)
BIO_AGE_SERIES = {
    "total": "totalBioAge",
    "muscle": "muscleBioAge",
    "metabolic": "metabolicBioAge",
    "cardio": "cardioBioAge",
    "flexibility": "flexibilityBioAge",
}


class Row(NamedTuple):
    """One row for QuestDB: symbols are strings, columns hold LONG, DOUBLE, VARCHAR or BOOLEAN values."""

    table: str
    symbols: dict
    columns: dict
    at: datetime.datetime


def parse_time(value: str, zone: datetime.tzinfo = UTC) -> datetime.datetime:
    """Read an API timestamp as a time in `zone` and return it in UTC.

    Python 3.10 `fromisoformat` accepts neither a trailing `Z` nor fractions of other than 3 or 6 digits.
    """
    text = value.removesuffix("Z")
    if "." in text:
        whole, fraction = text.split(".")
        text = f"{whole}.{fraction.ljust(6, '0')}"
    return datetime.datetime.fromisoformat(text).replace(tzinfo=zone).astimezone(UTC)


def _int(value):
    return None if value is None else int(value)


def _float(value):
    return None if value is None else float(value)


def _row(table, time, symbols, columns):
    """A row without its null values; symbol values become strings."""
    return Row(
        table,
        {key: str(value) for key, value in symbols.items() if value is not None},
        {key: value for key, value in columns.items() if value is not None},
        time,
    )


def _exercise_tags(exercise):
    activity = exercise["activity"]
    return {
        "exercise_id": exercise["id"],
        "activity_id": activity["activityId"],
        "activity": activity["name"].get("en"),
        "category": activity.get("category"),
    }


def _exercise_time(exercise):
    return parse_time(exercise["completedAt"], ZoneInfo(exercise["timezone"]))


def _created(entry):
    return parse_time(entry["createdAt"])


# The dated tables come out oldest first. A write that fails part-way then leaves the newest stored
# time at a point up to which every older row is stored, and the next cycle fetches the rest.
def _exercises_oldest_first(workouts):
    return sorted((exercise for workout in workouts for exercise in workout["exercises"]), key=_exercise_time)


def exercises(workouts: list) -> list:
    rows = []
    for exercise in _exercises_oldest_first(workouts):
        summary = exercise.get("summary") or {}
        symbols = {
            **_exercise_tags(exercise),
            "source_type": exercise.get("sourceType"),
            "source": exercise.get("source"),
        }
        columns = {
            "points": _int(exercise.get("points")),
            "kilocalories": _float(exercise.get("kiloCalories")),
            "total_duration": _int(summary.get("totalDuration")),
            "total_distance": _float(summary.get("totalDistance")),
            "vertical_distance": _float(summary.get("verticalDistance")),
            "avg_pace": _float(summary.get("avgPace")),
            "avg_heart_rate": _float(summary.get("avgHeartRate")),
            "max_heart_rate": _float(summary.get("maxHeartRate")),
            "avg_speed": _float(summary.get("avgSpeed")),
            "avg_incline": _float(summary.get("avgIncline")),
        }
        rows.append(_row("exercises", _exercise_time(exercise), symbols, columns))
    return rows


def exercise_sets(workouts: list) -> list:
    rows = []
    for exercise in _exercises_oldest_first(workouts):
        time = _exercise_time(exercise)
        for number, item in enumerate(exercise.get("sets") or [], start=1):
            symbols = {
                **_exercise_tags(exercise),
                "set_type": item.get("setType"),
                "set_number": number,
                "training_method": item.get("trainingMethod"),
                "side_mode": item.get("sideMode"),
            }
            columns = {
                "reps": _int(item.get("numberOfReps")),
                "weight": _float(item.get("weight")),
                "duration": _int(item.get("duration")),
                "distance": _float(item.get("distance")),
                "heart_rate": _float(item.get("heartRate")),
                "speed": _float(item.get("speed")),
                "incline": _float(item.get("incline")),
                "recovery_time": _float(item.get("recoveryTime")),
            }
            rows.append(_row("exercise_sets", time, symbols, columns))
    return rows


def body_measurements(entries: list) -> list:
    return [
        _row(
            "body_measurements",
            _created(entry),
            {"measurement_id": entry["id"], "type": metric["type"], "source": entry.get("source")},
            {"value": _float(metric.get("value")), "value_interpretation": metric.get("valueInterpretation")},
        )
        for entry in sorted(entries, key=_created)
        for metric in entry["metrics"]
    ]


def cardio_measurements(response: dict) -> list:
    return [
        _row(
            "cardio_measurements",
            _created(entry),
            {"type": metric["type"], "measurement_id": entry["id"], "source": entry.get("source")},
            {"value": _float(metric.get("value"))},
        )
        for entry in sorted(response["measurements"], key=_created)
        for metric in entry["metrics"]
    ]


def strength_measurements(response: dict) -> list:
    rows = []
    for entry in sorted(response["strengthMeasurements"], key=_created):
        activity = entry["activity"]
        strength_set = entry.get("strengthSet") or {}
        symbols = {
            "measurement_id": entry["id"],
            "activity_id": activity["activityId"],
            "activity": activity.get("label"),
            "body_region": entry.get("bodyRegion"),
            "source": entry.get("source"),
        }
        columns = {
            "strength": _int((entry.get("strength") or {}).get("value")),
            "set_reps": _int(strength_set.get("reps")),
            "set_weight": _float(strength_set.get("weight")),
        }
        rows.append(_row("strength_measurements", _created(entry), symbols, columns))
    return rows


def bio_age(summary: dict) -> list:
    items = [(name, item) for name, key in BIO_AGE_SERIES.items() for item in summary.get(key) or []]
    return [
        _row("bio_age", parse_time(item["date"]), {"type": name}, {"value": _int(item.get("value"))})
        for name, item in sorted(items, key=lambda pair: pair[1]["date"])
    ]


def muscle_imbalances(response: dict) -> list:
    return [
        _row(
            "muscle_imbalances",
            parse_time(item["calculatedAt"]),
            {
                "body_region": item.get("bodyRegion"),
                "agonist_muscle": item.get("agonistMuscle"),
                "antagonist_muscle": item.get("antagonistMuscle"),
            },
            {
                "position": _float(item.get("position")),
                "optimal_range_start": _float(item.get("optimalRangeStartPosition")),
                "optimal_range_end": _float(item.get("optimalRangeEndPosition")),
                "range_size": _float(item.get("rangeSize")),
                "agonist_strength": _int(item.get("agonistStrengthValue")),
                "antagonist_strength": _int(item.get("antagonistStrengthValue")),
                "agonist_activity_id": _int(item.get("agonistActivityId")),
                "antagonist_activity_id": _int(item.get("antagonistActivityId")),
            },
        )
        for item in response.get("muscleImbalances") or []
    ]


def activity_level(response: dict, time: datetime.datetime) -> list:
    columns = {
        "points": _int(response.get("points")),
        "days_left": _int(response.get("daysLeft")),
        "goal": _int(response.get("goal")),
        "maintain_points": _int(response.get("maintainPoints")),
    }
    return [_row("activity_level", time, {"level": response.get("level")}, columns)]


def ranking(response: dict, time: datetime.datetime) -> list:
    user = response.get("rankOfUser") or {}
    columns = {
        "rank": _int((user.get("rank") or {}).get("value")),
        "points": _int((user.get("points") or {}).get("value")),
        "average_rank": _int(user.get("averageRank")),
        "total_users": _int((response.get("leaderBoard") or {}).get("totalNumberOfUsers")),
    }
    return [_row("ranking", time, {}, columns)]


def meta_gym(gyms: list) -> list:
    return [
        _row(
            "meta_gym",
            EPOCH,
            {"gym_id": gym["uuid"]},
            {"name": gym.get("name"), "timezone": gym.get("timezone"), "url": gym.get("url")},
        )
        for gym in gyms
    ]


def meta_profile(profile: dict) -> list:
    columns = {
        "first_name": profile.get("firstname"),
        "last_name": profile.get("lastname"),
        "birthday": profile.get("birthday"),
        "gender": profile.get("gender"),
    }
    return [_row("meta_profile", EPOCH, {"exerciser_id": profile["uuid"]}, columns)]


def _merge(activities, activity_id, values):
    current = activities.setdefault(int(activity_id), {"name": None, "category": None})
    current.update({key: value for key, value in values.items() if value is not None})


def meta_activities(stored: list, workouts: list, strength: dict, favourites: list) -> list:
    """All activities: the stored rows, overridden by this cycle's data; favourite as in this cycle.

    `stored` holds the stored rows as dicts with `activity_id`, `name`, `category` and `favourite`.
    A written row replaces the stored one completely, so every row is written complete.
    """
    activities = {}
    for row in stored:
        _merge(activities, row["activity_id"], {"name": row.get("name"), "category": row.get("category")})
    for entry in strength["strengthMeasurements"]:
        _merge(activities, entry["activity"]["activityId"], {"name": entry["activity"].get("label")})
    for activity in [exercise["activity"] for workout in workouts for exercise in workout["exercises"]] + favourites:
        _merge(activities, activity["activityId"], {"name": activity["name"].get("en"), "category": activity.get("category")})
    favourite_ids = {activity["activityId"] for activity in favourites}
    return [
        _row("meta_activities", EPOCH, {"activity_id": activity_id}, {**values, "favourite": activity_id in favourite_ids})
        for activity_id, values in activities.items()
    ]


def meta_reset(value: str) -> list:
    return [_row("meta_reset", EPOCH, {}, {"value": value})]


def meta_plans(plans: list) -> list:
    return [
        _row(
            "meta_plans",
            EPOCH,
            {"plan_id": plan["id"]},
            {"name": plan.get("name"), "type": plan.get("type"), "group_type": plan.get("groupType")},
        )
        for plan in plans
    ]
