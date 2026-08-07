"""Pure result lifecycle helpers shared by ingestion, SQL backfills, and tests."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Mapping, Sequence


RESULT_STATUSES = {"result", "completed", "complete", "full time", "full-time", "ft"}
LIVE_STATUSES = {"live", "in progress", "in-progress", "halftime", "half time"}
CANCELLED_STATUSES = {"cancelled", "canceled", "postponed", "abandoned"}


@dataclass(frozen=True)
class ResultLifecycle:
    match_status: str
    score_status: str
    result_ready: bool
    score_source: str | None
    validation_status: str


def normalise_status(value) -> str:
    return str(value or "").strip().lower()


def derive_result_lifecycle(
    *,
    home_score,
    away_score,
    source_status=None,
    played=False,
    score_source: str | None = None,
) -> ResultLifecycle:
    status = normalise_status(source_status)
    has_scores = home_score is not None and away_score is not None
    has_final_evidence = bool(played) or status in RESULT_STATUSES
    has_source = bool(score_source)

    if status in CANCELLED_STATUSES:
        return ResultLifecycle("Postponed", "Unavailable", False, score_source, "Not result eligible")
    if status in LIVE_STATUSES:
        return ResultLifecycle("Live", "Pending", False, score_source, "Awaiting source confirmation")
    if has_final_evidence:
        if has_scores and has_source:
            return ResultLifecycle("Completed", "Confirmed", True, score_source, "Valid")
        return ResultLifecycle("Completed", "Unavailable", False, score_source, "Final status without complete score evidence")
    if has_scores and has_source and status in RESULT_STATUSES:
        return ResultLifecycle("Completed", "Confirmed", True, score_source, "Valid")
    return ResultLifecycle("Scheduled", "Pending", False, score_source, "Awaiting source confirmation")


def actual_home_margin(home_score, away_score) -> int | None:
    if home_score is None or away_score is None:
        return None
    return int(home_score) - int(away_score)


def signed_margin_error(home_score, away_score, predicted_home_margin) -> float | None:
    margin = actual_home_margin(home_score, away_score)
    if margin is None or predicted_home_margin is None:
        return None
    return float(margin) - float(predicted_home_margin)


def absolute_margin_error(home_score, away_score, predicted_home_margin) -> float | None:
    error = signed_margin_error(home_score, away_score, predicted_home_margin)
    return None if error is None else abs(error)


def latest_pre_match_prediction(
    predictions: Sequence[Mapping],
    *,
    kickoff_datetime: datetime | None,
    match_date=None,
) -> Mapping | None:
    eligible = []
    for row in predictions:
        generated_at = row.get("PredictionGeneratedAt")
        if generated_at is None:
            continue
        if kickoff_datetime is not None:
            if generated_at < kickoff_datetime:
                eligible.append(row)
        elif match_date is not None:
            if getattr(generated_at, "date", lambda: None)() < match_date:
                eligible.append(row)
        else:
            eligible.append(row)
    if not eligible:
        return None
    return sorted(
        eligible,
        key=lambda row: (
            row.get("PredictionGeneratedAt"),
            row.get("ProductionPredictionID") or row.get("HistoryID") or 0,
        ),
        reverse=True,
    )[0]


def dense_rank_desc(rows: Iterable[Mapping], value_key: str) -> list[int]:
    values = sorted({row[value_key] for row in rows}, reverse=True)
    ranks = {value: index + 1 for index, value in enumerate(values)}
    return [ranks[row[value_key]] for row in rows]
