import datetime
from urllib.parse import urlsplit

import questdb
import requests

from .records import parse_time

MARKER_TABLE = "meta_reset"
# The symbol columns that identify a row, besides `timestamp`; a row written again with the same keys replaces the stored one.
UPSERT_KEYS = {
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
    MARKER_TABLE: (),
}


# Columns the fetcher reads back, created with the table so that a query on a table without rows works.
READ_COLUMNS = {
    MARKER_TABLE: {"value": "VARCHAR"},
    "meta_activities": {"name": "VARCHAR", "category": "VARCHAR", "favourite": "BOOLEAN"},
}


class QueryError(Exception):
    """QuestDB answered a query with an error."""


def create_statement(table: str, keys: tuple, columns: dict | None = None) -> str:
    definitions = "".join(f", {key} SYMBOL" for key in keys)
    definitions += "".join(f", {name} {kind}" for name, kind in (columns or {}).items())
    upsert = ", ".join(("timestamp",) + keys)
    return (
        f"CREATE TABLE IF NOT EXISTS {table} (timestamp TIMESTAMP{definitions}) TIMESTAMP(timestamp) "
        f"PARTITION BY MONTH WAL DEDUP UPSERT KEYS({upsert})"
    )


class Store:
    """The QuestDB server the fetcher writes to over the line protocol and reads from over REST."""

    def __init__(self, host: str):
        self._base = host.rstrip("/")
        parts = urlsplit(self._base)
        self._conf = f"{parts.scheme}::addr={parts.netloc};"
        self._sender = None

    def _query(self, sql):
        body = requests.get(f"{self._base}/exec", params={"query": sql}, timeout=30).json()
        if "error" in body:
            raise QueryError(body["error"])
        return body

    def _rows(self, sql):
        """The rows of a query as dicts; a table that does not exist gives no rows."""
        try:
            body = self._query(sql)
        except QueryError as error:
            if str(error).startswith("table does not exist"):
                return []
            raise
        names = [column["name"] for column in body["columns"]]
        return [dict(zip(names, values)) for values in body["dataset"]]

    def create_tables(self) -> None:
        for table, keys in UPSERT_KEYS.items():
            self._query(create_statement(table, keys, READ_COLUMNS.get(table)))

    def newest(self, table: str) -> datetime.datetime | None:
        """The newest stored time of `table`, or None when it holds no rows or does not exist."""
        rows = self._rows(f"SELECT max(timestamp) AS newest FROM {table}")
        return parse_time(rows[0]["newest"]) if rows and rows[0]["newest"] else None

    def write(self, rows: list) -> None:
        # One sender until close(): the client warns about senders created in bursts, and a sender
        # that outlives a drop of its table loses rows (fetcher-findings.md, QuestDB checks).
        if self._sender is None:
            sender = questdb.Sender.from_conf(self._conf)
            sender.establish()
            self._sender = sender
        for row in rows:
            self._sender.row(row.table, symbols=row.symbols, columns=row.columns, at=row.at)
        self._sender.flush()

    def close(self) -> None:
        """Close the sender; the next write opens a new one."""
        if self._sender is not None:
            self._sender.close(flush=False)
            self._sender = None

    def drop_table(self, table: str) -> None:
        self.close()
        self._query(f"DROP TABLE IF EXISTS {table}")

    def reset_marker(self) -> str | None:
        """The FETCH_RESET value recorded by the last completed reset, or None."""
        rows = self._rows(f"SELECT value FROM {MARKER_TABLE}")
        return rows[0]["value"] if rows else None

    def activities(self) -> list:
        """The stored rows of meta_activities as dicts."""
        return self._rows("SELECT activity_id, name, category, favourite FROM meta_activities")
