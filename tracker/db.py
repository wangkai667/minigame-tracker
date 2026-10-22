from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS games (
    game_id    TEXT PRIMARY KEY,
    name       TEXT NOT NULL,
    developer  TEXT,
    tags       TEXT,
    first_seen TEXT NOT NULL,
    last_seen  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS snapshots (
    date    TEXT NOT NULL,
    list    TEXT NOT NULL,
    rank    INTEGER NOT NULL,
    game_id TEXT NOT NULL REFERENCES games(game_id),
    PRIMARY KEY (date, list, rank)
);
CREATE INDEX IF NOT EXISTS idx_snap_list_date ON snapshots(list, date);
"""


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def save_snapshot(conn: sqlite3.Connection, date: str, list_key: str, items: list[dict]) -> None:
    """同一天重复运行会覆盖当天该榜单的快照。"""
    with conn:
        conn.execute("DELETE FROM snapshots WHERE date=? AND list=?", (date, list_key))
        for it in items:
            conn.execute(
                """INSERT INTO games(game_id, name, developer, tags, first_seen, last_seen)
                   VALUES(?,?,?,?,?,?)
                   ON CONFLICT(game_id) DO UPDATE SET
                     name=excluded.name,
                     developer=COALESCE(NULLIF(excluded.developer,''), games.developer),
                     tags=COALESCE(NULLIF(excluded.tags,''), games.tags),
                     first_seen=MIN(games.first_seen, excluded.first_seen),
                     last_seen=MAX(games.last_seen, excluded.last_seen)""",
                (it["game_id"], it["name"], it["developer"], it["tags"], date, date),
            )
            conn.execute(
                "INSERT INTO snapshots(date, list, rank, game_id) VALUES(?,?,?,?)",
                (date, list_key, it["rank"], it["game_id"]),
            )


def ranking(conn: sqlite3.Connection, list_key: str, date: str) -> list[sqlite3.Row]:
    return conn.execute(
        """SELECT s.rank, g.* FROM snapshots s JOIN games g USING(game_id)
           WHERE s.list=? AND s.date=? ORDER BY s.rank""",
        (list_key, date),
    ).fetchall()


def prev_date(conn: sqlite3.Connection, list_key: str, before: str) -> str | None:
    row = conn.execute(
        "SELECT MAX(date) FROM snapshots WHERE list=? AND date<?", (list_key, before)
    ).fetchone()
    return row[0]


def date_on_or_before(conn: sqlite3.Connection, list_key: str, date: str) -> str | None:
    row = conn.execute(
        "SELECT MAX(date) FROM snapshots WHERE list=? AND date<=?", (list_key, date)
    ).fetchone()
    return row[0]


def rank_history(conn: sqlite3.Connection, list_key: str, game_id: str, since: str) -> list[tuple[str, int]]:
    return [
        (r[0], r[1])
        for r in conn.execute(
            "SELECT date, rank FROM snapshots WHERE list=? AND game_id=? AND date>=? ORDER BY date",
            (list_key, game_id, since),
        )
    ]
