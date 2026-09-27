import datetime
import logging
import time

from . import records
from .store import MARKER_TABLE

logger = logging.getLogger(__name__)

CARDIO_METRICS = ("RESTING_HEART_RATE", "VO2MAX", "BLOOD_PRESSURE")
DATED_TABLES = ("exercises", "body_measurements", "cardio_measurements", "strength_measurements", "bio_age")
RESET_DATED_TABLES = ("exercises", "exercise_sets", "body_measurements", "cardio_measurements", "strength_measurements", "bio_age")
TABLES = RESET_DATED_TABLES + (
    "muscle_imbalances",
    "activity_level",
    "ranking",
    "meta_gym",
    "meta_profile",
    "meta_activities",
    "meta_plans",
)
RESET_DROPS = {"reimport": (), "delete-dated": RESET_DATED_TABLES, "delete-tables": TABLES}
START_RETRY_SECONDS = 60


def utc_now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _year_has_data(api, body_types, year, current_year):
    start, end = datetime.date(year, 1, 1), datetime.date(year, 12, 31)
    summary = api.get_bio_age_summary("year", current_year - year)
    found = [
        api.get_workouts(start, end),
        api.get_body_measurements(body_types, start, end),
        *(api.get_cardio_measurements(metric, start, end)["measurements"] for metric in CARDIO_METRICS),
        api.get_strength_measurements(start, end)["strengthMeasurements"],
        *(summary.get(key) for key in records.BIO_AGE_SERIES.values()),
    ]
    return any(found)


def history_start(api, body_types: list, today: datetime.date) -> datetime.date:
    """1 January of the oldest year with data, searched back until two consecutive years hold none."""
    year, oldest, empty_years = today.year, today.year, 0
    while empty_years < 2:
        if _year_has_data(api, body_types, year, today.year):
            oldest, empty_years = year, 0
        else:
            empty_years += 1
        year -= 1
    return datetime.date(oldest, 1, 1)


def start_reset(store, reset: str | None) -> bool:
    """Apply FETCH_RESET at start-up, following the reset marker; returns True when a reset is now pending."""
    if reset is None:
        store.drop_table(MARKER_TABLE)
        return False
    if store.reset_marker() == reset:
        logger.warning("FETCH_RESET=%s has already run; the variable can be removed", reset)
        return False
    logger.info("Reset %s", reset)
    for table in RESET_DROPS[reset]:
        store.drop_table(table)
        logger.info("Dropped table %s", table)
    return True


def _write(store, table, rows, start=None, end=None):
    store.write(rows)
    if start is None:
        logger.info("%s: %d rows", table, len(rows))
    else:
        logger.info("%s: %s to %s, %d rows", table, start.isoformat(), end.isoformat(), len(rows))


def run_cycle(api_factory, store, overlap: datetime.timedelta, state=None, clock=utc_now, reset_pending=False) -> None:
    """Run one cycle. `state["history"]` holds the history start known so far; a search stores its result at once.

    While a reset is pending, the cycle searches the history start and fetches every dated table from there.
    """
    state = {} if state is None else state
    api = api_factory()
    try:
        now = clock()
        store.create_tables()
        newest = {table: store.newest(table) for table in DATED_TABLES}
        body_types = [metric["type"] for metric in api.get_latest_body_metrics()]
        if reset_pending or (state.get("history") is None and None in newest.values()):
            state["history"] = history_start(api, body_types, now.date())
        history = state.get("history")
        start = {
            table: history if reset_pending or newest[table] is None else newest[table] - overlap
            for table in DATED_TABLES
        }

        workouts = api.get_workouts(start["exercises"], now)
        # The sets go first: their start follows the newest stored exercise.
        _write(store, "exercise_sets", records.exercise_sets(workouts), start["exercises"], now)
        _write(store, "exercises", records.exercises(workouts), start["exercises"], now)

        body = api.get_body_measurements(body_types, start["body_measurements"], now)
        _write(store, "body_measurements", records.body_measurements(body), start["body_measurements"], now)

        cardio = [api.get_cardio_measurements(metric, start["cardio_measurements"], now) for metric in CARDIO_METRICS]
        cardio_rows = records.cardio_measurements(
            {"measurements": [entry for response in cardio for entry in response["measurements"]]}
        )
        _write(store, "cardio_measurements", cardio_rows, start["cardio_measurements"], now)

        strength = api.get_strength_measurements(start["strength_measurements"], now)
        strength_rows = records.strength_measurements(strength)
        _write(store, "strength_measurements", strength_rows, start["strength_measurements"], now)

        years = range(start["bio_age"].year, now.year + 1)
        summaries = [api.get_bio_age_summary("year", now.year - year) for year in years]
        bio_age_rows = records.bio_age(
            {
                key: [item for summary in summaries for item in summary.get(key) or []]
                for key in records.BIO_AGE_SERIES.values()
            }
        )
        _write(store, "bio_age", bio_age_rows, start["bio_age"], now)

        _write(store, "muscle_imbalances", records.muscle_imbalances(api.get_muscle_imbalances()))
        _write(store, "activity_level", records.activity_level(api.get_activity_level(), clock()))
        _write(store, "ranking", records.ranking(api.get_ranking(), clock()))

        _write(store, "meta_gym", records.meta_gym(api.get_gyms()))
        _write(store, "meta_profile", records.meta_profile(api.get_profile()))
        favourites = api.get_favourite_activities()
        _write(store, "meta_activities", records.meta_activities(store.activities(), workouts, strength, favourites))
        _write(store, "meta_plans", records.meta_plans(api.get_available_plans()))
    finally:
        store.close()
        api.logout()


def run(api_factory, store, interval, overlap, reset=None, clock=utc_now, sleep=time.sleep) -> None:
    """Apply `reset`, then run a cycle every `interval`, measured from the start of each cycle, until the process stops."""
    while True:
        try:
            pending = start_reset(store, reset)
            break
        except Exception:
            logger.exception("Start-up failed, next try in %d seconds", START_RETRY_SECONDS)
            sleep(START_RETRY_SECONDS)
    state = {}
    while True:
        started = clock()
        try:
            run_cycle(api_factory, store, overlap, state, clock, pending)
            if pending:
                store.write(records.meta_reset(reset))
                store.close()
                pending = False
        except Exception:
            logger.exception("Cycle failed")
        next_start = started + interval
        logger.info("Cycle finished, next cycle at %s", next_start.isoformat(timespec="seconds"))
        sleep(max(0.0, (next_start - clock()).total_seconds()))
