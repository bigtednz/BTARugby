"""Pure presentation helpers for the Match Centre."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Iterable

import pandas as pd


EVEN_MARGIN_THRESHOLD = 0.05
CONFIDENCE_ORDER = ["Low", "Moderate", "High", "Very High"]


def _is_missing(value) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and value.strip().lower() in {"", "nan", "none", "nat", "<na>", "null"}:
        return True
    return bool(pd.isna(value))


def format_percent(value) -> str:
    if _is_missing(value):
        return "Not available"
    return f"{float(value) * 100:.1f}%"


def highest_outcome_probability(row) -> float | None:
    values = [
        row.get("HomeWinProbability"),
        row.get("DrawProbability"),
        row.get("AwayWinProbability"),
    ]
    available = [float(value) for value in values if not _is_missing(value)]
    return max(available) if available else None


def average_prediction_confidence(rows: pd.DataFrame) -> float | None:
    if rows.empty:
        return None
    values = [highest_outcome_probability(row) for row in rows.to_dict("records")]
    values = [value for value in values if value is not None]
    return sum(values) / len(values) if values else None


def format_datetime(value, fmt: str) -> str:
    if _is_missing(value):
        return "Not available"
    if isinstance(value, str):
        parsed = pd.to_datetime(value, errors="coerce")
        if pd.isna(parsed):
            return "Not available"
        value = parsed.to_pydatetime()
    if isinstance(value, pd.Timestamp):
        value = value.to_pydatetime()
    if isinstance(value, datetime):
        return value.strftime(fmt).replace(" 0", " ")
    if isinstance(value, date):
        return value.strftime(fmt).replace(" 0", " ")
    return "Not available"


def _strip_leading_zeroes(text: str) -> str:
    return (
        text.replace(" 01 ", " 1 ")
        .replace(" 02 ", " 2 ")
        .replace(" 03 ", " 3 ")
        .replace(" 04 ", " 4 ")
        .replace(" 05 ", " 5 ")
        .replace(" 06 ", " 6 ")
        .replace(" 07 ", " 7 ")
        .replace(" 08 ", " 8 ")
        .replace(" 09 ", " 9 ")
        .replace(", 01:", ", 1:")
        .replace(", 02:", ", 2:")
        .replace(", 03:", ", 3:")
        .replace(", 04:", ", 4:")
        .replace(", 05:", ", 5:")
        .replace(", 06:", ", 6:")
        .replace(", 07:", ", 7:")
        .replace(", 08:", ", 8:")
        .replace(", 09:", ", 9:")
    )


def format_kickoff(row) -> str:
    known = bool(row.get("KickoffTimeKnownFlag"))
    local_value = row.get("KickoffDateTimeLocal")
    match_date = row.get("MatchDate")
    status = row.get("KickoffTimeStatus") or "time TBC"
    if known and not _is_missing(local_value):
        return _strip_leading_zeroes(format_datetime(local_value, "%a %d %b, %I:%M %p"))
    day = format_datetime(match_date, "%a %d %b")
    return f"{_strip_leading_zeroes(day)} - {status if status != 'Confirmed' else 'time TBC'}"


def format_margin(row) -> str:
    margin = row.get("PredictedHomeMargin")
    if _is_missing(margin):
        return "Not available"
    margin = float(margin)
    if abs(margin) < EVEN_MARGIN_THRESHOLD:
        return "Effectively even"
    team = row.get("HomeTeam") if margin > 0 else row.get("AwayTeam")
    if not team:
        return f"{abs(margin):.1f} points"
    return f"{team} by {abs(margin):.1f}"


def format_result(row) -> str:
    if row.get("ResultReadyFlag") in (0, False) or str(row.get("ScoreStatus") or "").lower() in {"pending", "unavailable"}:
        return "Awaiting result"
    home_score = row.get("HomeScore")
    away_score = row.get("AwayScore")
    if _is_missing(home_score) or _is_missing(away_score):
        return "Score not available"
    return f"{int(home_score)}-{int(away_score)}"


def format_result_winner(row) -> str:
    if row.get("ResultReadyFlag") in (0, False) or str(row.get("ScoreStatus") or "").lower() in {"pending", "unavailable"}:
        return row.get("EvaluationStatus") or "Awaiting confirmed result"
    home_score = row.get("HomeScore")
    away_score = row.get("AwayScore")
    if _is_missing(home_score) or _is_missing(away_score):
        return "Result not available"
    home_score = int(home_score)
    away_score = int(away_score)
    if home_score > away_score:
        return f"{row.get('HomeTeam') or 'Home'} won by {home_score - away_score}"
    if away_score > home_score:
        return f"{row.get('AwayTeam') or 'Away'} won by {away_score - home_score}"
    return "Draw"


def format_prediction_comparison(row) -> str:
    predicted = row.get("PredictedWinner")
    margin = row.get("PredictedHomeMargin")
    if _is_missing(predicted) or _is_missing(margin):
        return row.get("EvaluationStatus") or "Production prediction unavailable"
    if str(predicted) == "Draw":
        prediction = "Predicted draw"
    elif abs(float(margin)) < EVEN_MARGIN_THRESHOLD:
        prediction = "Predicted effectively even"
    else:
        prediction = f"Predicted {predicted} by {abs(float(margin)):.1f}"
    correct = row.get("CorrectWinner")
    if _is_missing(correct):
        return prediction
    return f"{prediction} - {'right winner' if bool(correct) else 'wrong winner'}"


def safe_value(value, suffix: str = "") -> str:
    if _is_missing(value):
        return "Not available"
    if isinstance(value, (float, Decimal)):
        return f"{float(value):.1f}{suffix}"
    return f"{value}{suffix}"


def fixture_url(match_id) -> str:
    if _is_missing(match_id):
        return "/"
    return f"/match/{int(match_id)}"


def sort_fixtures(rows: pd.DataFrame) -> pd.DataFrame:
    if rows.empty:
        return rows
    sorted_rows = rows.copy()
    for column in ("MatchDate", "KickoffDateTimeLocal"):
        if column in sorted_rows.columns:
            sorted_rows[column] = pd.to_datetime(sorted_rows[column], errors="coerce")
    sort_columns = [column for column in ("MatchDate", "KickoffDateTimeLocal", "MatchID") if column in sorted_rows.columns]
    return sorted_rows.sort_values(sort_columns, kind="mergesort").reset_index(drop=True)


def filter_fixtures(
    rows: pd.DataFrame,
    season=None,
    round_name=None,
    date_start=None,
    date_end=None,
    team=None,
    confidence=None,
) -> pd.DataFrame:
    if rows.empty:
        return rows
    filtered = rows.copy()
    if season not in (None, "", "All") and "Season" in filtered.columns:
        filtered = filtered[filtered["Season"].astype(str) == str(season)]
    if round_name not in (None, "", "All") and "Round" in filtered.columns:
        filtered = filtered[filtered["Round"].astype(str) == str(round_name)]
    if team not in (None, "", "All"):
        home = filtered.get("HomeTeam", pd.Series(dtype=object)).astype(str)
        away = filtered.get("AwayTeam", pd.Series(dtype=object)).astype(str)
        filtered = filtered[(home == str(team)) | (away == str(team))]
    if confidence not in (None, "", "All") and "ConfidenceLevel" in filtered.columns:
        filtered = filtered[filtered["ConfidenceLevel"].astype(str) == str(confidence)]
    if date_start and "MatchDate" in filtered.columns:
        start = pd.to_datetime(date_start, errors="coerce")
        dates = pd.to_datetime(filtered["MatchDate"], errors="coerce")
        filtered = filtered[dates >= start]
    if date_end and "MatchDate" in filtered.columns:
        end = pd.to_datetime(date_end, errors="coerce")
        dates = pd.to_datetime(filtered["MatchDate"], errors="coerce")
        filtered = filtered[dates <= end]
    return sort_fixtures(filtered)


def option_values(rows: pd.DataFrame, column: str) -> list[dict[str, str]]:
    if rows.empty or column not in rows.columns:
        return [{"label": "All", "value": "All"}]
    values = sorted({str(value) for value in rows[column].dropna().unique()})
    return [{"label": "All", "value": "All"}] + [{"label": value, "value": value} for value in values]


def team_options(rows: pd.DataFrame) -> list[dict[str, str]]:
    teams: set[str] = set()
    for column in ("HomeTeam", "AwayTeam"):
        if column in rows.columns:
            teams.update(str(value) for value in rows[column].dropna().unique())
    return [{"label": "All", "value": "All"}] + [{"label": value, "value": value} for value in sorted(teams)]


def safe_error_message(exc: Exception) -> str:
    text = str(exc)
    sensitive_tokens = ["DRIVER=", "SERVER=", "DATABASE=", "PWD=", "UID=", "Trusted_Connection"]
    database_tokens = sensitive_tokens + ["odbc", "sqlalchemy", "database", "server"]
    if any(token.lower() in text.lower() for token in database_tokens):
        return "The Match Centre could not connect to the local RugbyAnalytics database."
    return "The Match Centre could not load the requested data."


def records_from_frame(rows: pd.DataFrame) -> list[dict]:
    if rows.empty:
        return []
    return rows.where(pd.notna(rows), None).to_dict("records")


def rows_from_records(records: Iterable[dict]) -> pd.DataFrame:
    return pd.DataFrame(list(records))
