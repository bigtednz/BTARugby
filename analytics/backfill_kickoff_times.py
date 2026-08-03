"""
Backfill kickoff times from existing RugbyPass Bronze fixture snapshots.

This is non-destructive: MatchDate is preserved and only nullable kickoff fields
are updated where RugbyPass supplied a real kickoff time.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import sys
from pathlib import Path

try:
    from analytics import baseline_evaluation as base
    from analytics.kickoff_times import parse_current_game_days
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    sys.path.insert(0, os.path.dirname(__file__))
    import baseline_evaluation as base
    from kickoff_times import parse_current_game_days


def ensure_columns(cursor) -> None:
    statements = [
        "IF COL_LENGTH('NPC_Matches', 'KickoffDateTimeLocal') IS NULL ALTER TABLE NPC_Matches ADD KickoffDateTimeLocal DATETIME2 NULL",
        "IF COL_LENGTH('NPC_Matches', 'KickoffDateTimeUTC') IS NULL ALTER TABLE NPC_Matches ADD KickoffDateTimeUTC DATETIME2 NULL",
        "IF COL_LENGTH('NPC_Matches', 'KickoffTimeKnownFlag') IS NULL ALTER TABLE NPC_Matches ADD KickoffTimeKnownFlag BIT NOT NULL DEFAULT 0",
        "IF COL_LENGTH('NPC_Matches', 'KickoffTimeSource') IS NULL ALTER TABLE NPC_Matches ADD KickoffTimeSource VARCHAR(200) NULL",
        "IF COL_LENGTH('NPC_Matches', 'KickoffTimeCapturedAt') IS NULL ALTER TABLE NPC_Matches ADD KickoffTimeCapturedAt DATETIME2 NULL",
        "IF COL_LENGTH('Silver_Matches', 'KickoffDateTimeLocal') IS NULL ALTER TABLE Silver_Matches ADD KickoffDateTimeLocal DATETIME2 NULL",
        "IF COL_LENGTH('Silver_Matches', 'KickoffDateTimeUTC') IS NULL ALTER TABLE Silver_Matches ADD KickoffDateTimeUTC DATETIME2 NULL",
        "IF COL_LENGTH('Silver_Matches', 'KickoffTimeKnownFlag') IS NULL ALTER TABLE Silver_Matches ADD KickoffTimeKnownFlag BIT NOT NULL DEFAULT 0",
        "IF COL_LENGTH('Silver_Matches', 'KickoffTimeSource') IS NULL ALTER TABLE Silver_Matches ADD KickoffTimeSource VARCHAR(200) NULL",
        "IF COL_LENGTH('Silver_Matches', 'KickoffTimeCapturedAt') IS NULL ALTER TABLE Silver_Matches ADD KickoffTimeCapturedAt DATETIME2 NULL",
    ]
    for statement in statements:
        cursor.execute(statement)


def kickoff_infos_from_snapshot(content: str) -> dict[int, object]:
    content = content or ""
    if "current-game-days" in content:
        return parse_current_game_days(content)
    try:
        payload = json.loads(content)
    except json.JSONDecodeError:
        return {}
    days = payload.get("currentGameDays") if isinstance(payload, dict) else None
    if not days:
        return {}
    wrapped = f'<div id="current-game-days">{html.escape(json.dumps(days))}</div>'
    return parse_current_game_days(wrapped)


def load_bronze_fixture_snapshots(cursor, season: int | None) -> list[tuple[str, str]]:
    sql = """
        SELECT SourceEntityID, ContentText
        FROM Bronze_SourceSnapshots
        WHERE SourceSystem = 'RugbyPass'
          AND CompetitionCode = 'NPC'
          AND SourceEntity = 'fixtures'
    """
    params = []
    if season is not None:
        sql += " AND Season = ?"
        params.append(season)
    sql += " ORDER BY CapturedAt"
    return [(row.SourceEntityID, row.ContentText) for row in cursor.execute(sql, *params).fetchall()]


def backfill(cursor, season: int | None = None, dry_run: bool = False) -> dict:
    snapshots = load_bronze_fixture_snapshots(cursor, season)
    latest_by_match = {}
    for _, content in snapshots:
        latest_by_match.update(kickoff_infos_from_snapshot(content))
    known = {match_id: info for match_id, info in latest_by_match.items() if info.kickoff_time_known}
    unknown = {match_id: info for match_id, info in latest_by_match.items() if not info.kickoff_time_known}
    if dry_run:
        return {"snapshots": len(snapshots), "known": len(known), "unknown": len(unknown), "updated": 0}

    updated = 0
    for match_id, info in known.items():
        cursor.execute(
            """
            UPDATE NPC_Matches
            SET KickoffDateTimeLocal = ?,
                KickoffDateTimeUTC = ?,
                KickoffTimeKnownFlag = 1,
                KickoffTimeSource = ?,
                KickoffTimeCapturedAt = SYSUTCDATETIME()
            WHERE MatchID = ?
              AND MatchDate = ?
            """,
            info.kickoff_datetime_local,
            info.kickoff_datetime_utc,
            info.kickoff_time_source[:200],
            match_id,
            info.match_date,
        )
        updated += cursor.rowcount if cursor.rowcount and cursor.rowcount > 0 else 0
        cursor.execute(
            """
            UPDATE Silver_Matches
            SET KickoffDateTimeLocal = ?,
                KickoffDateTimeUTC = ?,
                KickoffTimeKnownFlag = 1,
                KickoffTimeSource = ?,
                KickoffTimeCapturedAt = SYSUTCDATETIME()
            WHERE MatchID = ?
              AND MatchDate = ?
            """,
            info.kickoff_datetime_local,
            info.kickoff_datetime_utc,
            info.kickoff_time_source[:200],
            match_id,
            info.match_date,
        )
    return {"snapshots": len(snapshots), "known": len(known), "unknown": len(unknown), "updated": updated}


def run(args: argparse.Namespace) -> None:
    if base.pyodbc is None:
        raise RuntimeError("pyodbc is required for database execution")
    conn = base.pyodbc.connect(base.get_connection_string())
    cursor = conn.cursor()
    ensure_columns(cursor)
    result = backfill(cursor, args.season, args.dry_run)
    print(
        f"Bronze snapshots={result['snapshots']} known kickoff matches={result['known']} "
        f"unknown kickoff matches={result['unknown']} updated NPC rows={result['updated']}"
    )
    if args.dry_run:
        print("Dry run: no database writes will be committed.")
        conn.rollback()
    else:
        conn.commit()
    conn.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Backfill RugbyPass kickoff times from Bronze snapshots")
    parser.add_argument("--season", type=int, default=None, help="Optional season filter")
    parser.add_argument("--dry-run", action="store_true", help="Inspect without writing")
    return parser


def main() -> None:
    run(build_parser().parse_args())


if __name__ == "__main__":
    main()
