# questdb-fetcher-egym

A service that copies the data of an EGYM Fitness account into QuestDB. On its first run it imports the whole history of the account; after that it fetches recent data at a fixed interval. Explore the data in QuestDB's web console with its notebooks, or in Grafana through the QuestDB data source.

It reads the data through [python-egym](https://github.com/marcelpoelstra/python-egym) and never writes anything to EGYM. It is not affiliated with or endorsed by EGYM.

Inspired by influxdb-fetcher-egym by bitstacker.

## Requirements

Docker to build and run the images. `compose.yaml` runs QuestDB 10.0.1 and the fetcher; the fetcher image is based on `python:3.14.7-alpine3.24` and builds for linux/amd64 and linux/arm64.

## Configuration

All settings are environment variables. An empty variable counts as not set.

| Variable | Required | Default | Meaning |
| --- | --- | --- | --- |
| `EGYM_EMAIL` | yes | | EGYM Fitness login email |
| `EGYM_PASSWORD` | yes | | EGYM Fitness password |
| `EGYM_BASE_URL` | no | found from the email | the gym's Netpulse address |
| `QUESTDB_HOST` | yes | | QuestDB's HTTP address with scheme and port; `compose.yaml` sets `http://questdb:9000` |
| `FETCH_INTERVAL_HOURS` | no | `24` | hours between the start of one run and the next |
| `FETCH_OVERLAP_DAYS` | no | `7` | days fetched again before the newest stored point |
| `FETCH_RESET` | no | | reset of the history at start-up: `reimport`, `delete-dated` or `delete-tables`, see [Resetting the history](#resetting-the-history). **Warning:** `delete-tables` permanently removes the muscle imbalance, activity level and ranking history, which cannot be fetched from EGYM again |

The two numbers accept positive decimal values, for example `0.5`. An invalid value stops the service at start-up with a message naming the variable.

## Running with Docker

`compose.yaml` runs two services: `questdb`, with its data in the volume `questdb-data`, and `questdb-fetcher-egym`, built from this repository. Both restart unless stopped. The fetcher takes the variables above from the shell or from a `.env` file next to `compose.yaml`; git ignores `.env`.

```bash
docker compose up -d --build
docker compose logs -f questdb-fetcher-egym
```

QuestDB's web console, with its notebooks, is at `http://localhost:9000`. QuestDB runs without authentication, and `compose.yaml` publishes port 9000 on the host.

## How it runs

Each run logs in, creates any missing table, fetches, writes and logs out, then waits until `FETCH_INTERVAL_HOURS` after the start of the run. A failed run is logged with its traceback, and the next run starts at the usual time. When QuestDB does not answer at start-up, the service logs the error and tries again every 60 seconds. The log shows `***` in place of the email address and the password.

When one of the tables `exercises`, `body_measurements`, `cardio_measurements`, `strength_measurements` or `bio_age` is empty, the service looks for the start of the history, once after each start of the service; later runs reuse the start it found. It steps back one calendar year at a time from the current year, asking for workouts, body measurements, cardio measurements, strength measurements and bio age, and stops after two consecutive years without any of them. Every empty table is then filled from 1 January of the oldest year with data.

A table that already holds data is fetched from its newest point minus `FETCH_OVERLAP_DAYS`. Every table deduplicates on its upsert keys, so a row fetched again replaces the stored one and the overlap creates no duplicates. Muscle imbalances, activity level, ranking and the metadata tables are fetched in every run.

## Resetting the history

**Warning:** `delete-tables` permanently removes the muscle imbalance, activity level and ranking history. The service fetches only the current values of these, so their history exists only in QuestDB and cannot be fetched again.

Set `FETCH_RESET` in the shell or in `.env` and run `docker compose up -d`: Compose recreates the container with the new value, while `docker compose restart` keeps the old one. The service applies the reset at start-up, before its first run:

| Value | Dropped before the first run |
| --- | --- |
| `reimport` | nothing |
| `delete-dated` | the tables `exercises`, `exercise_sets`, `body_measurements`, `cardio_measurements`, `strength_measurements` and `bio_age` |
| `delete-tables` | all 13 tables listed under [Tables](#tables) |

With every value, the service then looks for the start of the history again and fetches every dated table from there, replacing stored rows with the same upsert keys. With `reimport`, rows of records that EGYM no longer returns stay in QuestDB. When the run fails, the next runs do the same until one completes. The dropping happens once per start of the service, so a restart before a run completes drops again.

When a run after the reset completes, the service records the value in the table `meta_reset`. While `FETCH_RESET` keeps that value, later restarts skip the reset and log a warning that the variable can be removed. A different value runs its own reset. To remove the variable, delete it from the shell or `.env` and run `docker compose up -d` again. To run the same reset again later, start the service once without `FETCH_RESET`: that start removes `meta_reset`.

Drop the service's tables only through `FETCH_RESET`, or while the service is stopped.

## Tables

Column names are the API names in snake_case. Every table has the designated timestamp `timestamp` and is partitioned by month. Identifying and descriptive values are `SYMBOL` columns; measured values are `LONG`, `DOUBLE`, `VARCHAR` or `BOOLEAN`. A value the API does not give is `NULL`. Values are stored as the API returns them; units are not converted.

### Time series

| Table | One row per | Symbols | Values | Upsert keys |
| --- | --- | --- | --- | --- |
| `exercises` | exercise | `exercise_id`, `activity_id`, `activity` (English name), `category`, `source_type`, `source` | `points`, `kilocalories`, `total_duration`, `total_distance`, `vertical_distance`, `avg_pace`, `avg_heart_rate`, `max_heart_rate`, `avg_speed`, `avg_incline` | `timestamp`, `exercise_id` |
| `exercise_sets` | set | `exercise_id`, `activity_id`, `activity`, `category`, `set_type`, `set_number` (position in the exercise, starting at 1), `training_method`, `side_mode` | `reps`, `weight`, `duration`, `distance`, `heart_rate`, `speed`, `incline`, `recovery_time` | `timestamp`, `exercise_id`, `set_number` |
| `body_measurements` | metric of a measurement | `measurement_id`, `type`, `source` | `value`, `value_interpretation` | `timestamp`, `measurement_id`, `type` |
| `cardio_measurements` | metric of a measurement | `type` (for example RESTING_HEART_RATE, SYSTOLIC_PRESSURE, DIASTOLIC_PRESSURE, VO2MAX), `measurement_id`, `source` | `value` | `timestamp`, `measurement_id`, `type` |
| `strength_measurements` | measurement | `measurement_id`, `activity_id`, `activity` (label), `body_region`, `source` | `strength`, `set_reps`, `set_weight` | `timestamp`, `measurement_id` |
| `bio_age` | month per type | `type`: `total`, `muscle`, `metabolic`, `cardio` or `flexibility` | `value` | `timestamp`, `type` |
| `muscle_imbalances` | imbalance | `body_region`, `agonist_muscle`, `antagonist_muscle` | `position`, `optimal_range_start`, `optimal_range_end`, `range_size`, `agonist_strength`, `antagonist_strength`, `agonist_activity_id`, `antagonist_activity_id` | `timestamp`, `body_region`, `agonist_muscle`, `antagonist_muscle` |
| `activity_level` | run | `level` | `points`, `days_left`, `goal`, `maintain_points` | `timestamp` |
| `ranking` | run | | `rank`, `points`, `average_rank`, `total_users` | `timestamp` |

The body measurement types are the ones the account's latest body metrics list.

### Metadata

Each key keeps one row with the latest values.

| Table | Symbol | Values | Upsert keys |
| --- | --- | --- | --- |
| `meta_gym` | `gym_id` | `name`, `timezone`, `url` | `timestamp`, `gym_id` |
| `meta_profile` | `exerciser_id` | `first_name`, `last_name`, `birthday`, `gender` | `timestamp`, `exerciser_id` |
| `meta_activities` | `activity_id` | `name`, `category`, `favourite` (true while the activity is one of your favourites) | `timestamp`, `activity_id` |
| `meta_plans` | `plan_id` | `name`, `type`, `group_type` | `timestamp`, `plan_id` |

## Time rules

| Data | Stored time (UTC) |
| --- | --- |
| Exercises and sets | the exercise's completion time, read in the exercise's time zone |
| Body measurements, cardio and strength measurements | the time the measurement was created |
| Muscle imbalances | the time the imbalance was calculated |
| Bio age | the date of the value, at 00:00 |
| Activity level, ranking | the time the run wrote the row |
| Metadata tables and `meta_reset` | 1970-01-01T00:00:00Z |

## Upgrading from the 2021 version

`config.yml` is replaced by the environment variables above, and the InfluxDB 1.x measurement `egymdata` by the QuestDB tables above.
