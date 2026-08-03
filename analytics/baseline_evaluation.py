"""
Baseline Evaluation v0.2 for BTA Rugby Analytics.

This module intentionally keeps the benchmark models transparent:
- HomeTeamBaseline
- EloOnlyBaseline
- RollingMarginOnlyBaseline
- SeasonToDateMarginBaseline
- EloRollingMarginBaseline

Point-in-time protections:
- Matches are processed in stable chronological order: MatchDate, MatchID.
- Predictions are made before the target match updates Elo or rolling state.
- Rolling and season-to-date features use only prior completed matches.
- Scheduled matches can receive predictions, but never update model state or metrics.
- Walk-forward parameters are derived from seasons before the evaluation season.
"""

from __future__ import annotations

import argparse
import math
import os
from collections import defaultdict, deque
from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable

try:
    import pyodbc
except ImportError:  # Tests that do not touch SQL Server can still import this module.
    pyodbc = None


TARGET_NAME = "home_margin_and_result"
EVALUATION_NAME = "walk_forward_by_season"
MODEL_VERSION = "v0.2.0"
BASE_ELO = 1500.0
HOME_ADVANTAGE = 55.0
K_FACTOR = 24.0
ELO_MARGIN_POINTS_SCALE = 0.035
MARGIN_ELO_SCALE = 10.0
ROLLING_MARGIN_WEIGHT = 0.35
DEFAULT_TOTAL_POINTS = 51.0
LOG_LOSS_EPSILON = 1e-6
PROBABILITY_TOLERANCE = 0.0005
MIN_SEASON_SAMPLE = 5


MODEL_NAMES = {
    "HomeTeamBaseline",
    "EloOnlyBaseline",
    "RollingMarginOnlyBaseline",
    "SeasonToDateMarginBaseline",
    "EloRollingMarginBaseline",
}


@dataclass(frozen=True)
class Match:
    competition_code: str
    season: int
    match_id: int
    match_date: object
    round_name: str | None
    home_team_id: int
    home_team: str
    away_team_id: int
    away_team: str
    home_score: int | None
    away_score: int | None
    match_status: str


@dataclass
class ModelState:
    ratings: defaultdict
    rolling_margins: defaultdict
    season_margins: defaultdict
    completed_totals: deque
    feature_cutoff_dates: defaultdict


@dataclass(frozen=True)
class Prediction:
    match: Match
    model_name: str
    model_version: str
    evaluation_season: int
    training_start: object | None
    training_end: object | None
    feature_cutoff_date: object | None
    home_win_probability: float
    draw_probability: float
    away_win_probability: float
    predicted_margin: float
    predicted_home_score: float
    predicted_away_score: float


def get_connection_string() -> str:
    return os.getenv(
        "RUGBY_ANALYTICS_SQL_CONNECTION",
        "DRIVER={ODBC Driver 17 for SQL Server};"
        "SERVER=BIGTEDS;"
        "DATABASE=RugbyAnalytics;"
        "Trusted_Connection=yes;"
        "Encrypt=no;"
        "TrustServerCertificate=yes;",
    )


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def average(values: Iterable[float]) -> float | None:
    values = list(values)
    return sum(values) / len(values) if values else None


def safe_divide(numerator: float, denominator: float, fallback: float = 0.0) -> float:
    return numerator / denominator if denominator else fallback


def expected_score(rating_a: float, rating_b: float) -> float:
    return 1.0 / (1.0 + math.pow(10.0, (rating_b - rating_a) / 400.0))


def margin_multiplier(margin: float) -> float:
    return math.log(abs(margin) + 1.0)


def clip_probability(value: float) -> float:
    return clamp(value, LOG_LOSS_EPSILON, 1.0 - LOG_LOSS_EPSILON)


def to_decimal(value: float | None, places: str = "0.000001") -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value)).quantize(Decimal(places))


def actual_home_result(match: Match) -> float | None:
    if match.home_score is None or match.away_score is None:
        return None
    if match.home_score > match.away_score:
        return 1.0
    if match.home_score == match.away_score:
        return 0.5
    return 0.0


def actual_outcome(match: Match) -> str | None:
    if match.home_score is None or match.away_score is None:
        return None
    if match.home_score > match.away_score:
        return "H"
    if match.home_score == match.away_score:
        return "D"
    return "A"


def predicted_outcome(prediction: Prediction) -> str:
    probs = {
        "H": prediction.home_win_probability,
        "D": prediction.draw_probability,
        "A": prediction.away_win_probability,
    }
    return max(probs.items(), key=lambda item: (item[1], item[0]))[0]


def probability_sum(prediction: Prediction) -> float:
    return (
        prediction.home_win_probability
        + prediction.draw_probability
        + prediction.away_win_probability
    )


def validate_probability_sum(home: float, draw: float, away: float) -> bool:
    return abs((home + draw + away) - 1.0) <= PROBABILITY_TOLERANCE


def confidence_band(home_probability: float) -> tuple[str, float, float]:
    value = clamp(home_probability, 0.0, 1.0)
    idx = 9 if value == 1.0 else int(value * 10)
    start = idx / 10.0
    end = (idx + 1) / 10.0
    return f"{start:.2f}-{end:.2f}", start, end


def brier_score(probability: float, actual: float) -> float:
    return (probability - actual) ** 2


def multiclass_brier(home_p: float, draw_p: float, away_p: float, outcome: str) -> float:
    return (
        (home_p - (1.0 if outcome == "H" else 0.0)) ** 2
        + (draw_p - (1.0 if outcome == "D" else 0.0)) ** 2
        + (away_p - (1.0 if outcome == "A" else 0.0)) ** 2
    )


def log_loss(home_p: float, draw_p: float, away_p: float, outcome: str) -> float:
    selected = {"H": home_p, "D": draw_p, "A": away_p}[outcome]
    return -math.log(clip_probability(selected))


def margin_errors(predicted: list[float], actual: list[float]) -> tuple[float, float, float]:
    errors = [p - a for p, a in zip(predicted, actual)]
    mae = average(abs(err) for err in errors) or 0.0
    rmse = math.sqrt(average(err * err for err in errors) or 0.0)
    bias = average(errors) or 0.0
    return mae, rmse, bias


def round_band(round_name: str | None) -> str:
    text = round_name or ""
    digits = "".join(ch for ch in text if ch.isdigit())
    if digits:
        number = int(digits)
        if number <= 3:
            return "Early"
        if number <= 7:
            return "Middle"
        return "Late"
    lowered = text.lower()
    if any(token in lowered for token in ("quarter", "semi", "final")):
        return "Late"
    return "Unknown"


def sort_matches(matches: Iterable[Match]) -> list[Match]:
    # Stable ordering prevents ambiguous same-day fixtures from leaking state.
    return sorted(matches, key=lambda m: (m.match_date, m.match_id))


def seasons_available(matches: Iterable[Match]) -> list[int]:
    return sorted({m.season for m in matches})


def walk_forward_splits(matches: list[Match], start_season: int | None, end_season: int | None) -> list[int]:
    seasons = seasons_available(matches)
    eval_seasons = [s for s in seasons if s >= 2023]
    if start_season is not None:
        eval_seasons = [s for s in eval_seasons if s >= start_season]
    if end_season is not None:
        eval_seasons = [s for s in eval_seasons if s <= end_season]
    return eval_seasons


def training_matches_for_season(matches: list[Match], evaluation_season: int) -> list[Match]:
    return [
        m for m in matches
        if m.season < evaluation_season and m.match_status == "Completed"
    ]


def evaluation_matches_for_season(matches: list[Match], evaluation_season: int) -> list[Match]:
    return [m for m in matches if m.season == evaluation_season]


def initialise_state(training_matches: list[Match]) -> ModelState:
    state = ModelState(
        ratings=defaultdict(lambda: BASE_ELO),
        rolling_margins=defaultdict(lambda: deque(maxlen=5)),
        season_margins=defaultdict(list),
        completed_totals=deque(maxlen=50),
        feature_cutoff_dates=defaultdict(lambda: None),
    )
    for match in sort_matches(training_matches):
        update_state_after_match(state, match, update_season_margins=False)
    return state


def update_state_after_match(state: ModelState, match: Match, update_season_margins: bool = True) -> None:
    if match.match_status != "Completed" or match.home_score is None or match.away_score is None:
        return
    result = actual_home_result(match)
    if result is None:
        return

    home_rating = state.ratings[match.home_team_id]
    away_rating = state.ratings[match.away_team_id]
    expected_home = expected_score(home_rating + HOME_ADVANTAGE, away_rating)
    margin = float(match.home_score - match.away_score)
    rating_delta = K_FACTOR * margin_multiplier(margin) * (result - expected_home)
    state.ratings[match.home_team_id] += rating_delta
    state.ratings[match.away_team_id] -= rating_delta
    state.rolling_margins[match.home_team_id].append(margin)
    state.rolling_margins[match.away_team_id].append(-margin)
    if update_season_margins:
        state.season_margins[match.home_team_id].append(margin)
        state.season_margins[match.away_team_id].append(-margin)
    state.completed_totals.append(float(match.home_score + match.away_score))
    state.feature_cutoff_dates[match.home_team_id] = match.match_date
    state.feature_cutoff_dates[match.away_team_id] = match.match_date


def training_summary(training_matches: list[Match]) -> dict:
    completed = [m for m in training_matches if m.home_score is not None and m.away_score is not None]
    total = len(completed)
    home_wins = sum(1 for m in completed if m.home_score > m.away_score)
    draws = sum(1 for m in completed if m.home_score == m.away_score)
    away_wins = sum(1 for m in completed if m.home_score < m.away_score)
    margins = [float(m.home_score - m.away_score) for m in completed]
    totals = [float(m.home_score + m.away_score) for m in completed]
    return {
        "training_start": min((m.match_date for m in completed), default=None),
        "training_end": max((m.match_date for m in completed), default=None),
        "home_win_rate": safe_divide(home_wins, total, 0.45),
        "draw_rate": safe_divide(draws, total, 0.04),
        "away_win_rate": safe_divide(away_wins, total, 0.51),
        "mean_home_margin": average(margins) or 0.0,
        "mean_total_points": average(totals) or DEFAULT_TOTAL_POINTS,
    }


def normalise_probabilities(home: float, draw: float, away: float) -> tuple[float, float, float]:
    home = clamp(home, 0.0, 1.0)
    draw = clamp(draw, 0.0, 1.0)
    away = clamp(away, 0.0, 1.0)
    total = home + draw + away
    if total == 0:
        return 0.45, 0.05, 0.50
    return home / total, draw / total, away / total


def score_prediction(match: Match, predicted_margin: float, expected_total: float) -> tuple[float, float]:
    home_score = clamp((expected_total + predicted_margin) / 2.0, 0.0, 80.0)
    away_score = clamp(expected_total - home_score, 0.0, 80.0)
    return home_score, away_score


def probability_from_margin(predicted_margin: float, draw_rate: float) -> tuple[float, float, float]:
    draw = clamp(draw_rate if abs(predicted_margin) < 2.0 else min(draw_rate, 0.04), 0.01, 0.12)
    home_raw = 1.0 / (1.0 + math.exp(-predicted_margin / 9.0))
    home = home_raw * (1.0 - draw)
    away = 1.0 - draw - home
    return normalise_probabilities(home, draw, away)


def feature_cutoff_date(state: ModelState, match: Match) -> object | None:
    dates = [
        state.feature_cutoff_dates[match.home_team_id],
        state.feature_cutoff_dates[match.away_team_id],
    ]
    dates = [d for d in dates if d is not None]
    return max(dates) if dates else None


def make_prediction(model_name: str, match: Match, state: ModelState, summary: dict, evaluation_season: int) -> Prediction:
    home_rating = state.ratings[match.home_team_id]
    away_rating = state.ratings[match.away_team_id]
    draw_rate = summary["draw_rate"]
    expected_total = average(state.completed_totals) or summary["mean_total_points"]

    if model_name == "HomeTeamBaseline":
        home_p, draw_p, away_p = normalise_probabilities(
            summary["home_win_rate"], summary["draw_rate"], summary["away_win_rate"]
        )
        predicted_margin = summary["mean_home_margin"]
    elif model_name == "EloOnlyBaseline":
        elo_diff = home_rating + HOME_ADVANTAGE - away_rating
        raw_home = expected_score(elo_diff, 0.0)
        draw_p = clamp(draw_rate if abs(elo_diff) < 35 else min(draw_rate, 0.04), 0.01, 0.12)
        home_p, draw_p, away_p = normalise_probabilities(raw_home * (1.0 - draw_p), draw_p, (1.0 - raw_home) * (1.0 - draw_p))
        predicted_margin = elo_diff * ELO_MARGIN_POINTS_SCALE
    elif model_name == "RollingMarginOnlyBaseline":
        home_roll = average(state.rolling_margins[match.home_team_id]) or 0.0
        away_roll = average(state.rolling_margins[match.away_team_id]) or 0.0
        # Fallback for insufficient history is zero rolling edge, i.e. neutral recent form.
        predicted_margin = (home_roll - away_roll) * ROLLING_MARGIN_WEIGHT
        home_p, draw_p, away_p = probability_from_margin(predicted_margin, draw_rate)
    elif model_name == "SeasonToDateMarginBaseline":
        home_std = average(state.season_margins[match.home_team_id])
        away_std = average(state.season_margins[match.away_team_id])
        # Early-season fallback uses the training-window average home margin only.
        if home_std is None or away_std is None:
            predicted_margin = summary["mean_home_margin"]
        else:
            predicted_margin = (home_std - away_std) * 0.45
        home_p, draw_p, away_p = probability_from_margin(predicted_margin, draw_rate)
    elif model_name == "EloRollingMarginBaseline":
        elo_diff = home_rating + HOME_ADVANTAGE - away_rating
        home_roll = average(state.rolling_margins[match.home_team_id]) or 0.0
        away_roll = average(state.rolling_margins[match.away_team_id]) or 0.0
        rolling_diff = home_roll - away_roll
        combined_rating_diff = elo_diff + rolling_diff * MARGIN_ELO_SCALE
        raw_home = expected_score(combined_rating_diff, 0.0)
        predicted_margin = elo_diff * ELO_MARGIN_POINTS_SCALE + rolling_diff * ROLLING_MARGIN_WEIGHT
        draw_p = clamp(draw_rate if abs(predicted_margin) < 2.0 else min(draw_rate, 0.04), 0.01, 0.12)
        home_p, draw_p, away_p = normalise_probabilities(raw_home * (1.0 - draw_p), draw_p, (1.0 - raw_home) * (1.0 - draw_p))
    else:
        raise ValueError(f"Unknown model: {model_name}")

    predicted_home, predicted_away = score_prediction(match, predicted_margin, expected_total)
    return Prediction(
        match=match,
        model_name=model_name,
        model_version=MODEL_VERSION,
        evaluation_season=evaluation_season,
        training_start=summary["training_start"],
        training_end=summary["training_end"],
        feature_cutoff_date=feature_cutoff_date(state, match),
        home_win_probability=home_p,
        draw_probability=draw_p,
        away_win_probability=away_p,
        predicted_margin=predicted_margin,
        predicted_home_score=predicted_home,
        predicted_away_score=predicted_away,
    )


def evaluate_prediction(prediction: Prediction) -> dict | None:
    match = prediction.match
    if match.match_status != "Completed" or match.home_score is None or match.away_score is None:
        return None
    outcome = actual_outcome(match)
    home_result = actual_home_result(match)
    if outcome is None or home_result is None:
        return None
    actual_margin = float(match.home_score - match.away_score)
    margin_error = prediction.predicted_margin - actual_margin
    pred_outcome = predicted_outcome(prediction)
    correct = None if outcome == "D" else 1 if pred_outcome == outcome else 0
    return {
        "prediction": prediction,
        "actual_home_result": home_result,
        "actual_outcome": outcome,
        "predicted_outcome": pred_outcome,
        "correct_winner": correct,
        "margin_error": margin_error,
        "absolute_margin_error": abs(margin_error),
        "squared_margin_error": margin_error * margin_error,
        "home_probability_error": prediction.home_win_probability - home_result,
        "home_probability_brier": brier_score(prediction.home_win_probability, home_result),
        "multiclass_brier": multiclass_brier(
            prediction.home_win_probability,
            prediction.draw_probability,
            prediction.away_win_probability,
            outcome,
        ),
        "log_loss": log_loss(
            prediction.home_win_probability,
            prediction.draw_probability,
            prediction.away_win_probability,
            outcome,
        ),
    }


def calculate_metrics(evaluations: list[dict]) -> dict:
    if not evaluations:
        return {}
    non_draw = [e for e in evaluations if e["actual_outcome"] != "D"]
    predicted_margins = [e["prediction"].predicted_margin for e in evaluations]
    actual_margins = [
        float(e["prediction"].match.home_score - e["prediction"].match.away_score)
        for e in evaluations
    ]
    mae, rmse, bias = margin_errors(predicted_margins, actual_margins)
    return {
        "matches_evaluated": float(len(evaluations)),
        "non_draw_matches_evaluated": float(len(non_draw)),
        "winner_accuracy": average(e["correct_winner"] for e in non_draw) or 0.0,
        "home_probability_brier": average(e["home_probability_brier"] for e in evaluations) or 0.0,
        "multiclass_brier": average(e["multiclass_brier"] for e in evaluations) or 0.0,
        "log_loss": average(e["log_loss"] for e in evaluations) or 0.0,
        "margin_mae": mae,
        "margin_rmse": rmse,
        "mean_margin_error": bias,
        "actual_home_win_rate": average(1.0 if e["actual_outcome"] == "H" else 0.0 for e in evaluations) or 0.0,
        "mean_predicted_home_win_probability": average(e["prediction"].home_win_probability for e in evaluations) or 0.0,
    }


def calculate_calibration(evaluations: list[dict]) -> list[dict]:
    rows = []
    for idx in range(10):
        start = idx / 10.0
        end = (idx + 1) / 10.0
        label = f"{start:.2f}-{end:.2f}"
        band_rows = [
            e for e in evaluations
            if confidence_band(e["prediction"].home_win_probability)[0] == label
        ]
        if not band_rows:
            continue
        non_draw = [e for e in band_rows if e["actual_outcome"] != "D"]
        mean_pred = average(e["prediction"].home_win_probability for e in band_rows) or 0.0
        actual_home = average(1.0 if e["actual_outcome"] == "H" else 0.0 for e in band_rows) or 0.0
        rows.append({
            "confidence_band": label,
            "band_start": start,
            "band_end": end,
            "prediction_count": len(band_rows),
            "mean_home_win_probability": mean_pred,
            "actual_home_win_rate": actual_home,
            "calibration_gap": mean_pred - actual_home,
            "winner_accuracy": average(e["correct_winner"] for e in non_draw) if non_draw else None,
            "mean_absolute_margin_error": average(e["absolute_margin_error"] for e in band_rows) or 0.0,
        })
    return rows


def run_model_for_season(model_name: str, matches: list[Match], evaluation_season: int) -> tuple[list[Prediction], list[dict], list[dict], dict]:
    sorted_all = sort_matches(matches)
    train = training_matches_for_season(sorted_all, evaluation_season)
    eval_matches = sort_matches(evaluation_matches_for_season(sorted_all, evaluation_season))
    summary = training_summary(train)
    state = initialise_state(train)
    predictions = []
    evaluations = []

    for match in eval_matches:
        prediction = make_prediction(model_name, match, state, summary, evaluation_season)
        predictions.append(prediction)
        evaluation = evaluate_prediction(prediction)
        if evaluation:
            evaluations.append(evaluation)
        # For point-in-time evaluation, same-season completed matches become
        # available only after their prediction has been made.
        update_state_after_match(state, match, update_season_margins=True)

    return predictions, evaluations, calculate_calibration(evaluations), summary


def load_matches_from_db(cursor) -> list[Match]:
    rows = cursor.execute(
        """
        SELECT
            c.CompetitionCode,
            s.Season,
            m.MatchID,
            m.MatchDate,
            m.RoundName,
            m.HomeTeamID,
            ht.TeamName AS HomeTeam,
            m.AwayTeamID,
            at.TeamName AS AwayTeam,
            m.HomeScore,
            m.AwayScore,
            m.MatchStatus
        FROM Silver_Matches m
        JOIN Silver_Seasons s ON s.SeasonID = m.SeasonID
        JOIN Silver_Competitions c ON c.CompetitionID = s.CompetitionID
        JOIN Silver_Teams ht ON ht.TeamID = m.HomeTeamID
        JOIN Silver_Teams at ON at.TeamID = m.AwayTeamID
        WHERE c.CompetitionCode = 'NPC'
        ORDER BY m.MatchDate, m.MatchID
        """
    ).fetchall()
    return [
        Match(
            competition_code=row.CompetitionCode,
            season=row.Season,
            match_id=row.MatchID,
            match_date=row.MatchDate,
            round_name=row.RoundName,
            home_team_id=row.HomeTeamID,
            home_team=row.HomeTeam,
            away_team_id=row.AwayTeamID,
            away_team=row.AwayTeam,
            home_score=row.HomeScore,
            away_score=row.AwayScore,
            match_status=row.MatchStatus,
        )
        for row in rows
    ]


def ensure_model_version(cursor, model_name: str, summary: dict) -> int:
    notes = (
        "Baseline Evaluation v0.2; walk-forward by season; "
        "predictions are made before same-match state updates; "
        f"BASE_ELO={BASE_ELO}; HOME_ADVANTAGE={HOME_ADVANTAGE}; K_FACTOR={K_FACTOR}"
    )
    cursor.execute(
        """
        MERGE Gold_ModelVersions AS t
        USING (SELECT ? AS ModelName, ? AS ModelVersion, ? AS TargetName) AS s
        ON t.ModelName = s.ModelName
           AND t.ModelVersion = s.ModelVersion
           AND t.TargetName = s.TargetName
        WHEN MATCHED THEN UPDATE SET
            TrainingStart = ?,
            TrainingEnd = ?,
            Notes = ?
        WHEN NOT MATCHED THEN INSERT (
            ModelName, ModelVersion, TargetName, TrainingStart, TrainingEnd, Notes
        ) VALUES (?, ?, ?, ?, ?, ?);
        """,
        (
            model_name, MODEL_VERSION, TARGET_NAME,
            summary["training_start"], summary["training_end"], notes,
            model_name, MODEL_VERSION, TARGET_NAME,
            summary["training_start"], summary["training_end"], notes,
        ),
    )
    return cursor.execute(
        """
        SELECT ModelVersionID
        FROM Gold_ModelVersions
        WHERE ModelName = ? AND ModelVersion = ? AND TargetName = ?
        """,
        model_name, MODEL_VERSION, TARGET_NAME,
    ).fetchone()[0]


def existing_results(cursor, model_version_id: int, evaluation_season: int) -> int:
    return cursor.execute(
        """
        SELECT COUNT(*)
        FROM Gold_BacktestResults
        WHERE ModelVersionID = ?
          AND EvaluationName = ?
          AND EvaluationSeason = ?
        """,
        model_version_id,
        EVALUATION_NAME,
        evaluation_season,
    ).fetchone()[0]


def clear_results(cursor, model_version_id: int, evaluation_season: int) -> None:
    cursor.execute(
        """
        DELETE pe
        FROM Gold_PredictionEvaluations pe
        JOIN Gold_MatchPredictions p ON p.PredictionID = pe.PredictionID
        WHERE pe.ModelVersionID = ?
          AND pe.EvaluationName = ?
          AND pe.EvaluationSeason = ?
        """,
        model_version_id,
        EVALUATION_NAME,
        evaluation_season,
    )
    cursor.execute(
        """
        DELETE FROM Gold_ModelCalibration
        WHERE ModelVersionID = ? AND EvaluationName = ? AND EvaluationSeason = ?
        """,
        model_version_id,
        EVALUATION_NAME,
        evaluation_season,
    )
    cursor.execute(
        """
        DELETE FROM Gold_BacktestResults
        WHERE ModelVersionID = ? AND EvaluationName = ? AND EvaluationSeason = ?
        """,
        model_version_id,
        EVALUATION_NAME,
        evaluation_season,
    )
    cursor.execute(
        """
        DELETE p
        FROM Gold_MatchPredictions p
        JOIN Silver_Matches m ON m.MatchID = p.MatchID
        JOIN Silver_Seasons s ON s.SeasonID = m.SeasonID
        WHERE p.ModelVersionID = ? AND s.Season = ?
        """,
        model_version_id,
        evaluation_season,
    )


def upsert_prediction(cursor, model_version_id: int, prediction: Prediction) -> int:
    cursor.execute(
        """
        MERGE Gold_MatchPredictions AS t
        USING (SELECT ? AS MatchID, ? AS ModelVersionID) AS s
        ON t.MatchID = s.MatchID AND t.ModelVersionID = s.ModelVersionID
        WHEN MATCHED THEN UPDATE SET
            HomeWinProbability = ?,
            AwayWinProbability = ?,
            DrawProbability = ?,
            PredictedHomeScore = ?,
            PredictedAwayScore = ?,
            PredictedMargin = ?,
            PredictionMadeAt = SYSUTCDATETIME()
        WHEN NOT MATCHED THEN INSERT (
            MatchID, ModelVersionID, HomeWinProbability, AwayWinProbability,
            DrawProbability, PredictedHomeScore, PredictedAwayScore, PredictedMargin
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
        """,
        (
            prediction.match.match_id, model_version_id,
            to_decimal(prediction.home_win_probability),
            to_decimal(prediction.away_win_probability),
            to_decimal(prediction.draw_probability),
            to_decimal(prediction.predicted_home_score, "0.001"),
            to_decimal(prediction.predicted_away_score, "0.001"),
            to_decimal(prediction.predicted_margin, "0.001"),
            prediction.match.match_id, model_version_id,
            to_decimal(prediction.home_win_probability),
            to_decimal(prediction.away_win_probability),
            to_decimal(prediction.draw_probability),
            to_decimal(prediction.predicted_home_score, "0.001"),
            to_decimal(prediction.predicted_away_score, "0.001"),
            to_decimal(prediction.predicted_margin, "0.001"),
        ),
    )
    return cursor.execute(
        "SELECT PredictionID FROM Gold_MatchPredictions WHERE MatchID = ? AND ModelVersionID = ?",
        prediction.match.match_id,
        model_version_id,
    ).fetchone()[0]


def insert_evaluation(cursor, model_version_id: int, prediction_id: int, evaluation: dict) -> None:
    prediction = evaluation["prediction"]
    match = prediction.match
    cursor.execute(
        """
        INSERT INTO Gold_PredictionEvaluations (
            PredictionID, ModelVersionID, MatchID, EvaluationName, EvaluationSeason,
            FeatureCutoffDate, HomeTeamID, AwayTeamID, RoundName, RoundBand,
            HomeScore, AwayScore, ActualHomeResult, ActualOutcome, PredictedOutcome,
            CorrectWinner, MarginError, AbsoluteMarginError, SquaredMarginError,
            HomeProbabilityError, HomeProbabilityBrier, MulticlassBrier, LogLoss
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            prediction_id,
            model_version_id,
            match.match_id,
            EVALUATION_NAME,
            prediction.evaluation_season,
            prediction.feature_cutoff_date,
            match.home_team_id,
            match.away_team_id,
            match.round_name,
            round_band(match.round_name),
            match.home_score,
            match.away_score,
            to_decimal(evaluation["actual_home_result"]),
            evaluation["actual_outcome"],
            evaluation["predicted_outcome"],
            evaluation["correct_winner"],
            to_decimal(evaluation["margin_error"]),
            to_decimal(evaluation["absolute_margin_error"]),
            to_decimal(evaluation["squared_margin_error"]),
            to_decimal(evaluation["home_probability_error"]),
            to_decimal(evaluation["home_probability_brier"]),
            to_decimal(evaluation["multiclass_brier"]),
            to_decimal(evaluation["log_loss"]),
        ),
    )


def insert_metrics(cursor, model_version_id: int, model_name: str, evaluation_season: int, evaluations: list[dict], metrics: dict) -> None:
    start = min(e["prediction"].match.match_date for e in evaluations)
    end = max(e["prediction"].match.match_date for e in evaluations)
    for name, value in metrics.items():
        cursor.execute(
            """
            INSERT INTO Gold_BacktestResults (
                ModelVersionID, EvaluationStart, EvaluationEnd, MetricName, MetricValue,
                BaselineName, EvaluationName, EvaluationSeason
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                model_version_id,
                start,
                end,
                name,
                to_decimal(value),
                model_name,
                EVALUATION_NAME,
                evaluation_season,
            ),
        )


def insert_calibration(cursor, model_version_id: int, evaluation_season: int, rows: list[dict]) -> None:
    for row in rows:
        cursor.execute(
            """
            INSERT INTO Gold_ModelCalibration (
                ModelVersionID, EvaluationName, EvaluationSeason, ConfidenceBand,
                BandStart, BandEnd, PredictionCount, MeanHomeWinProbability,
                ActualHomeWinRate, CalibrationGap, WinnerAccuracy, MeanAbsoluteMarginError
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                model_version_id,
                EVALUATION_NAME,
                evaluation_season,
                row["confidence_band"],
                to_decimal(row["band_start"], "0.01"),
                to_decimal(row["band_end"], "0.01"),
                row["prediction_count"],
                to_decimal(row["mean_home_win_probability"]),
                to_decimal(row["actual_home_win_rate"]),
                to_decimal(row["calibration_gap"]),
                to_decimal(row["winner_accuracy"]) if row["winner_accuracy"] is not None else None,
                to_decimal(row["mean_absolute_margin_error"]),
            ),
        )


def data_quality_checks(predictions: list[Prediction], evaluations: list[dict]) -> list[str]:
    errors = []
    seen = set()
    for prediction in predictions:
        key = (prediction.model_name, prediction.evaluation_season, prediction.match.match_id)
        if key in seen:
            errors.append(f"Duplicate in-memory prediction for {key}")
        seen.add(key)
        if not validate_probability_sum(
            prediction.home_win_probability,
            prediction.draw_probability,
            prediction.away_win_probability,
        ):
            errors.append(f"Probabilities do not sum to 1 for match {prediction.match.match_id}")
        if any(
            value < 0.0 or value > 1.0
            for value in (
                prediction.home_win_probability,
                prediction.draw_probability,
                prediction.away_win_probability,
            )
        ):
            errors.append(f"Probability outside 0-1 for match {prediction.match.match_id}")
        if prediction.feature_cutoff_date is not None and prediction.feature_cutoff_date >= prediction.match.match_date:
            errors.append(f"Feature cutoff leaks target match for match {prediction.match.match_id}")
    for evaluation in evaluations:
        match = evaluation["prediction"].match
        if match.match_status != "Completed":
            errors.append(f"Scheduled match included in evaluation: {match.match_id}")
        if match.home_score is None or match.away_score is None:
            errors.append(f"Completed match missing score: {match.match_id}")
        if match.home_score == 0 and match.away_score == 0:
            errors.append(f"Suspicious completed 0-0 match: {match.match_id}")
    if 0 < len(evaluations) < MIN_SEASON_SAMPLE:
        errors.append(f"Unexpectedly small evaluation sample: {len(evaluations)}")
    return errors


def db_quality_checks(cursor, model_version_id: int, evaluation_season: int) -> list[str]:
    checks = [
        (
            "Duplicate predictions for same match/model",
            """
            SELECT COUNT(*) FROM (
                SELECT MatchID, ModelVersionID
                FROM Gold_MatchPredictions
                WHERE ModelVersionID = ?
                GROUP BY MatchID, ModelVersionID
                HAVING COUNT(*) > 1
            ) d
            """,
            (model_version_id,),
        ),
        (
            "Probabilities outside 0-1",
            """
            SELECT COUNT(*)
            FROM Gold_MatchPredictions
            WHERE ModelVersionID = ?
              AND (
                  HomeWinProbability < 0 OR HomeWinProbability > 1
                  OR DrawProbability < 0 OR DrawProbability > 1
                  OR AwayWinProbability < 0 OR AwayWinProbability > 1
              )
            """,
            (model_version_id,),
        ),
        (
            "Probabilities do not sum to approximately 1",
            """
            SELECT COUNT(*)
            FROM Gold_MatchPredictions
            WHERE ModelVersionID = ?
              AND ABS(HomeWinProbability + DrawProbability + AwayWinProbability - 1.0) > 0.001
            """,
            (model_version_id,),
        ),
        (
            "Completed evaluation-season matches without predictions",
            """
            SELECT COUNT(*)
            FROM Silver_Matches m
            JOIN Silver_Seasons s ON s.SeasonID = m.SeasonID
            LEFT JOIN Gold_MatchPredictions p
                ON p.MatchID = m.MatchID AND p.ModelVersionID = ?
            WHERE s.Season = ?
              AND m.MatchStatus = 'Completed'
              AND p.PredictionID IS NULL
            """,
            (model_version_id, evaluation_season),
        ),
    ]
    errors = []
    for label, sql, params in checks:
        count = cursor.execute(sql, *params).fetchone()[0]
        if count:
            errors.append(f"{label}: {count}")
    return errors


def selected_models(model_name: str) -> list[str]:
    if model_name == "all":
        return sorted(MODEL_NAMES)
    if model_name not in MODEL_NAMES:
        raise ValueError(f"Unknown model '{model_name}'. Use one of: all, {', '.join(sorted(MODEL_NAMES))}")
    return [model_name]


def run(args: argparse.Namespace) -> None:
    if pyodbc is None:
        raise RuntimeError("pyodbc is required for database execution")

    conn = pyodbc.connect(get_connection_string())
    cursor = conn.cursor()
    matches = load_matches_from_db(cursor)
    eval_seasons = walk_forward_splits(matches, args.start_season, args.end_season)
    if args.evaluation_season != "all":
        eval_seasons = [s for s in eval_seasons if s == int(args.evaluation_season)]
    models = selected_models(args.model)

    print(f"Models: {', '.join(models)}")
    print(f"Evaluation seasons: {', '.join(str(s) for s in eval_seasons)}")
    if args.dry_run:
        print("Dry run: no database writes will be made.")

    for model_name in models:
        for season in eval_seasons:
            predictions, evaluations, calibration, summary = run_model_for_season(model_name, matches, season)
            quality_errors = data_quality_checks(predictions, evaluations)
            if quality_errors:
                raise RuntimeError("\n".join(quality_errors))

            metrics = calculate_metrics(evaluations)
            print(
                f"{model_name} {season}: predictions={len(predictions)} "
                f"evaluated={len(evaluations)} accuracy={metrics.get('winner_accuracy', 0):.3f} "
                f"mae={metrics.get('margin_mae', 0):.3f}"
            )

            if args.dry_run:
                continue

            model_version_id = ensure_model_version(cursor, model_name, summary)
            existing = existing_results(cursor, model_version_id, season)
            if existing and not args.replace:
                raise RuntimeError(
                    f"Stored results already exist for {model_name} {MODEL_VERSION} season {season}. "
                    "Rerun with --replace to overwrite this evaluation window."
                )
            if args.replace:
                clear_results(cursor, model_version_id, season)

            prediction_id_by_match = {}
            for prediction in predictions:
                prediction_id_by_match[prediction.match.match_id] = upsert_prediction(cursor, model_version_id, prediction)
            for evaluation in evaluations:
                insert_evaluation(
                    cursor,
                    model_version_id,
                    prediction_id_by_match[evaluation["prediction"].match.match_id],
                    evaluation,
                )
            insert_metrics(cursor, model_version_id, model_name, season, evaluations, metrics)
            insert_calibration(cursor, model_version_id, season, calibration)

            db_errors = db_quality_checks(cursor, model_version_id, season)
            if db_errors:
                raise RuntimeError("\n".join(db_errors))
            conn.commit()

    conn.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Baseline Evaluation v0.2")
    parser.add_argument("--model", default="all", help="Model name or 'all'")
    parser.add_argument("--evaluation-season", default="all", help="Evaluation season or 'all'")
    parser.add_argument("--start-season", type=int, default=None, help="Optional first evaluation season")
    parser.add_argument("--end-season", type=int, default=None, help="Optional last evaluation season")
    parser.add_argument("--dry-run", action="store_true", help="Calculate without database writes")
    parser.add_argument("--replace", action="store_true", help="Replace stored results for the same model/version/window")
    return parser


def main() -> None:
    run(build_parser().parse_args())


if __name__ == "__main__":
    main()
