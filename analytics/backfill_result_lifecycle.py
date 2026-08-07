"""Backfill match result lifecycle fields from Bronze RugbyPass fixture snapshots."""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

try:
    import pyodbc
except ImportError:  # pragma: no cover
    pyodbc = None

try:
    from analytics.result_lifecycle import derive_result_lifecycle
except ModuleNotFoundError:  # Direct script execution
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from analytics.result_lifecycle import derive_result_lifecycle


DEFAULT_CONNECTION_STRING = (
    "DRIVER={ODBC Driver 17 for SQL Server};"
    "SERVER=BIGTEDS;"
    "DATABASE=RugbyAnalytics;"
    "Trusted_Connection=yes;"
    "Encrypt=no;"
    "TrustServerCertificate=yes;"
)


def connection_string() -> str:
    return os.getenv("BTA_SQL_CONNECTION_STRING") or DEFAULT_CONNECTION_STRING


def nested_values(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from nested_values(child)
    elif isinstance(value, list):
        for child in value:
            yield from nested_values(child)


def current_game_days_payload(content: str):
    match = re.search(r'<div[^>]+id=["\']current-game-days["\'][^>]*>(.*?)</div>', content or "", re.DOTALL | re.IGNORECASE)
    if match:
        raw = html.unescape(match.group(1)).strip()
        if raw:
            return json.loads(raw)
    return json.loads(content)


def team_name(value):
    if isinstance(value, str):
        return value or None
    if isinstance(value, dict):
        return value.get("name") or value.get("fullName") or value.get("teamName") or value.get("shortName")
    return None


def safe_int(value):
    try:
        return int(str(value).replace(",", "").strip())
    except Exception:
        return None


def first_present(obj: dict, *keys):
    for key in keys:
        if key in obj and obj[key] is not None:
            return obj[key]
    return None


def game_rows_from_snapshot(content: str, captured_at: datetime):
    try:
        payload = current_game_days_payload(content)
    except Exception:
        return []
    rows = []
    for obj in nested_values(payload):
        if obj.get("tournamentUri") != "bunnings-npc":
            continue
        match_id = safe_int(first_present(obj, "id", "matchId", "gameId"))
        home = team_name(obj.get("homeTeam") or obj.get("home_team") or obj.get("home"))
        away = team_name(obj.get("awayTeam") or obj.get("away_team") or obj.get("away"))
        if not match_id or not home or not away:
            continue
        status = obj.get("status") or obj.get("matchStatus")
        played = bool(obj.get("played"))
        home_score = safe_int(first_present(obj, "homeScore", "home_score"))
        away_score = safe_int(first_present(obj, "awayScore", "away_score"))
        score_source = None
        if played or str(status or "").strip().lower() in {"result", "completed", "complete", "full time", "full-time", "ft"}:
            score_source = f"RugbyPass Bronze fixtures status={status or 'unknown'} played={played}"
        lifecycle = derive_result_lifecycle(
            home_score=home_score,
            away_score=away_score,
            source_status=status,
            played=played,
            score_source=score_source,
        )
        rows.append(
            {
                "match_id": match_id,
                "home_score": home_score,
                "away_score": away_score,
                "match_status": lifecycle.match_status,
                "score_status": lifecycle.score_status,
                "result_ready": 1 if lifecycle.result_ready else 0,
                "score_source": lifecycle.score_source,
                "score_captured_at": captured_at,
                "validation": lifecycle.validation_status,
            }
        )
    return rows


def add_columns(cursor) -> None:
    statements = [
        "IF COL_LENGTH('NPC_Matches', 'MatchStatus') IS NULL ALTER TABLE NPC_Matches ADD MatchStatus VARCHAR(30) NULL",
        "IF COL_LENGTH('NPC_Matches', 'ScoreStatus') IS NULL ALTER TABLE NPC_Matches ADD ScoreStatus VARCHAR(30) NULL",
        "IF COL_LENGTH('NPC_Matches', 'ResultReadyFlag') IS NULL ALTER TABLE NPC_Matches ADD ResultReadyFlag BIT NOT NULL DEFAULT 0",
        "IF COL_LENGTH('NPC_Matches', 'ScoreSource') IS NULL ALTER TABLE NPC_Matches ADD ScoreSource VARCHAR(200) NULL",
        "IF COL_LENGTH('NPC_Matches', 'ScoreCapturedAt') IS NULL ALTER TABLE NPC_Matches ADD ScoreCapturedAt DATETIME2 NULL",
        "IF COL_LENGTH('NPC_Matches', 'ResultValidationStatus') IS NULL ALTER TABLE NPC_Matches ADD ResultValidationStatus VARCHAR(50) NULL",
    ]
    for statement in statements:
        cursor.execute(statement)


def run(season: int | None = None) -> None:
    if pyodbc is None:
        raise RuntimeError("pyodbc is required for SQL Server access")
    conn = pyodbc.connect(connection_string())
    cursor = conn.cursor()
    add_columns(cursor)
    snapshot_rows = cursor.execute(
        """
        SELECT ContentText, CapturedAt
        FROM Bronze_SourceSnapshots
        WHERE SourceSystem = 'RugbyPass'
          AND CompetitionCode = 'NPC'
          AND SourceEntity = 'fixtures'
          AND (? IS NULL OR Season = ? OR SourceEntityID = CONCAT('NPC-', ?))
        ORDER BY CapturedAt
        """,
        season,
        season,
        season,
    ).fetchall()
    latest = {}
    for snapshot in snapshot_rows:
        for row in game_rows_from_snapshot(snapshot.ContentText, snapshot.CapturedAt):
            latest[row["match_id"]] = row
    updated = 0
    ready = 0
    for row in latest.values():
        cursor.execute(
            """
            UPDATE NPC_Matches
            SET HomeScore = CASE WHEN ? = 1 THEN ? ELSE HomeScore END,
                AwayScore = CASE WHEN ? = 1 THEN ? ELSE AwayScore END,
                MatchStatus = ?,
                ScoreStatus = ?,
                ResultReadyFlag = ?,
                ScoreSource = COALESCE(?, ScoreSource),
                ScoreCapturedAt = CASE WHEN ? = 1 THEN ? ELSE ScoreCapturedAt END,
                ResultValidationStatus = ?
            WHERE MatchID = ?
            """,
            row["result_ready"],
            row["home_score"],
            row["result_ready"],
            row["away_score"],
            row["match_status"],
            row["score_status"],
            row["result_ready"],
            row["score_source"],
            row["result_ready"],
            row["score_captured_at"],
            row["validation"],
            row["match_id"],
        )
        updated += cursor.rowcount if cursor.rowcount and cursor.rowcount > 0 else 0
        ready += row["result_ready"]
    conn.commit()
    conn.close()
    print(f"Snapshots read: {len(snapshot_rows)}")
    print(f"Fixture rows parsed: {len(latest)}")
    print(f"NPC_Matches updated: {updated}")
    print(f"Result-ready rows found: {ready}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill result readiness from Bronze RugbyPass fixture snapshots")
    parser.add_argument("--season", type=int, default=None, help="Limit to one NPC season")
    args = parser.parse_args()
    run(args.season)


if __name__ == "__main__":
    main()
