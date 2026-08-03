"""
Dedicated Ridge Margin Model v0.3.0 for BTA Rugby Analytics.

The model predicts home margin only. Home/draw/away probabilities are retained
from EloOnlyBaseline v0.2.0 so probability champion selection is unchanged.
"""

from __future__ import annotations

import argparse
import math
import os
import sys
from dataclasses import dataclass
from typing import Callable, Iterable

try:
    from analytics import baseline_evaluation as base
except ModuleNotFoundError:  # Direct script execution: python analytics\ridge_margin_model.py
    sys.path.insert(0, os.path.dirname(__file__))
    import baseline_evaluation as base


RIDGE_MODEL_NAME = "RidgeMarginModel"
RIDGE_MODEL_VERSION = "v0.3.0"
RIDGE_ALPHA = 10.0
PROBABILITY_MODEL_NAME = "EloOnlyBaseline"
PROBABILITY_MODEL_VERSION = base.MODEL_VERSION
COMPLETE_SEASONS = (2023, 2024, 2025)
LARGE_ERROR_THRESHOLD = 15.0


@dataclass(frozen=True)
class FeatureSpec:
    name: str
    extractor: Callable[[dict, float], float | None]
    add_missing_indicator: bool = True


@dataclass(frozen=True)
class FeatureRow:
    match: base.Match
    values: dict[str, float | None]
    target: float | None
    feature_cutoff_date: object | None


@dataclass(frozen=True)
class RidgeFeatureParameter:
    feature_name: str
    coefficient: float
    feature_mean: float
    feature_stddev: float
    imputation_value: float
    is_missingness_indicator: bool


@dataclass(frozen=True)
class RidgeModel:
    alpha: float
    intercept: float
    parameters: list[RidgeFeatureParameter]


@dataclass(frozen=True)
class RidgePrediction:
    match: base.Match
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
    contributions: list[dict]


def _diff(row: dict, left: str, right: str) -> float | None:
    left_value = row.get(left)
    right_value = row.get(right)
    if left_value is None or right_value is None:
        return None
    return float(left_value) - float(right_value)


FEATURE_SPECS = [
    FeatureSpec("PreMatchEloDiff", lambda row, elo: elo, add_missing_indicator=False),
    FeatureSpec("Rolling3MarginDiff", lambda row, elo: row.get("Rolling3MarginDiff")),
    FeatureSpec("Rolling5MarginDiff", lambda row, elo: row.get("Rolling5MarginDiff")),
    FeatureSpec("SeasonToDateMarginDiff", lambda row, elo: row.get("SeasonToDateMarginDiff")),
    FeatureSpec("Rolling5PointsForDiff", lambda row, elo: _diff(row, "HomeRolling5PointsFor", "AwayRolling5PointsFor")),
    FeatureSpec("Rolling5PointsAgainstDiff", lambda row, elo: _diff(row, "HomeRolling5PointsAgainst", "AwayRolling5PointsAgainst")),
    FeatureSpec("HomeAwayFormDiff", lambda row, elo: _diff(row, "HomePriorHomeResult", "AwayPriorAwayResult")),
    FeatureSpec("RestDaysDiff", lambda row, elo: row.get("RestDaysDiff")),
    FeatureSpec("HeadToHeadMargin", lambda row, elo: row.get("HomeHeadToHeadLast5Margin")),
    FeatureSpec("ReturningPlayersDiff", lambda row, elo: row.get("ReturningPlayersDiff")),
    FeatureSpec("ReturningStartersDiff", lambda row, elo: row.get("ReturningStartersDiff")),
]


def percentile(values: Iterable[float], pct: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    pos = (len(ordered) - 1) * pct
    lower = math.floor(pos)
    upper = math.ceil(pos)
    if lower == upper:
        return ordered[int(pos)]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (pos - lower)


def load_feature_rows_from_db(cursor) -> dict[int, dict]:
    rows = cursor.execute("SELECT * FROM vw_Gold_MatchFeatureMatrix ORDER BY MatchDate, MatchID").fetchall()
    return {int(row.MatchID): {column[0]: getattr(row, column[0]) for column in cursor.description} for row in rows}


def build_point_in_time_feature_rows(matches: list[base.Match], feature_rows: dict[int, dict]) -> dict[int, FeatureRow]:
    state = base.initialise_state([])
    rows = {}
    for match in base.sort_matches(matches):
        home_rating = state.ratings[match.home_team_id]
        away_rating = state.ratings[match.away_team_id]
        elo_diff = home_rating + base.HOME_ADVANTAGE - away_rating
        source = feature_rows.get(match.match_id, {})
        values = {spec.name: spec.extractor(source, elo_diff) for spec in FEATURE_SPECS}
        target = None
        if match.match_status == "Completed" and match.home_score is not None and match.away_score is not None:
            target = float(match.home_score - match.away_score)
        rows[match.match_id] = FeatureRow(
            match=match,
            values=values,
            target=target,
            feature_cutoff_date=base.feature_cutoff_date(state, match),
        )
        base.update_state_after_match(state, match, update_season_margins=True)
    return rows


def expanded_feature_names() -> list[tuple[str, bool, str]]:
    names = []
    for spec in FEATURE_SPECS:
        names.append((spec.name, False, spec.name))
        if spec.add_missing_indicator:
            names.append((f"{spec.name}_Missing", True, spec.name))
    return names


def raw_expanded_values(row: FeatureRow) -> dict[str, float | None]:
    values = {}
    for name, is_indicator, base_name in expanded_feature_names():
        original = row.values.get(base_name)
        values[name] = 1.0 if is_indicator and original is None else 0.0 if is_indicator else original
    return values


def fit_ridge_model(rows: list[FeatureRow], alpha: float = RIDGE_ALPHA) -> RidgeModel:
    training_rows = [row for row in rows if row.target is not None]
    if not training_rows:
        raise ValueError("Ridge model requires at least one completed training match")

    names = expanded_feature_names()
    raw_rows = [raw_expanded_values(row) for row in training_rows]
    stats = {}
    for name, is_indicator, _ in names:
        observed = [float(row[name]) for row in raw_rows if row[name] is not None]
        impute = sum(observed) / len(observed) if observed else 0.0
        imputed = [float(row[name]) if row[name] is not None else impute for row in raw_rows]
        mean = sum(imputed) / len(imputed)
        variance = sum((value - mean) ** 2 for value in imputed) / len(imputed)
        stddev = math.sqrt(variance) or 1.0
        stats[name] = (mean, stddev, impute, is_indicator)

    x = []
    y = []
    for raw in raw_rows:
        x.append([1.0] + [
            ((float(raw[name]) if raw[name] is not None else stats[name][2]) - stats[name][0]) / stats[name][1]
            for name, _, _ in names
        ])
        y.append(float(training_rows[len(y)].target))

    coefficients = solve_ridge(x, y, alpha)
    params = [
        RidgeFeatureParameter(
            feature_name=name,
            coefficient=coefficients[idx + 1],
            feature_mean=stats[name][0],
            feature_stddev=stats[name][1],
            imputation_value=stats[name][2],
            is_missingness_indicator=stats[name][3],
        )
        for idx, (name, _, _) in enumerate(names)
    ]
    return RidgeModel(alpha=alpha, intercept=coefficients[0], parameters=params)


def solve_ridge(x: list[list[float]], y: list[float], alpha: float) -> list[float]:
    cols = len(x[0])
    xtx = [[0.0 for _ in range(cols)] for _ in range(cols)]
    xty = [0.0 for _ in range(cols)]
    for row, target in zip(x, y):
        for i in range(cols):
            xty[i] += row[i] * target
            for j in range(cols):
                xtx[i][j] += row[i] * row[j]
    for i in range(1, cols):
        xtx[i][i] += alpha
    return gaussian_solve(xtx, xty)


def gaussian_solve(matrix: list[list[float]], vector: list[float]) -> list[float]:
    n = len(vector)
    a = [row[:] + [vector[idx]] for idx, row in enumerate(matrix)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda row: abs(a[row][col]))
        if abs(a[pivot][col]) < 1e-12:
            a[pivot][col] = 1e-12
        a[col], a[pivot] = a[pivot], a[col]
        divisor = a[col][col]
        for j in range(col, n + 1):
            a[col][j] /= divisor
        for row in range(n):
            if row == col:
                continue
            factor = a[row][col]
            for j in range(col, n + 1):
                a[row][j] -= factor * a[col][j]
    return [a[row][n] for row in range(n)]


def predict_margin(model: RidgeModel, row: FeatureRow) -> tuple[float, list[dict]]:
    raw = raw_expanded_values(row)
    contributions = [{
        "feature_name": "Intercept",
        "feature_value": None,
        "standardized_feature_value": None,
        "coefficient": model.intercept,
        "contribution": model.intercept,
        "contribution_rank": 0,
    }]
    predicted = model.intercept
    for param in model.parameters:
        value = raw.get(param.feature_name)
        imputed = float(value) if value is not None else param.imputation_value
        standardized = (imputed - param.feature_mean) / param.feature_stddev
        contribution = standardized * param.coefficient
        predicted += contribution
        contributions.append({
            "feature_name": param.feature_name,
            "feature_value": value,
            "standardized_feature_value": standardized,
            "coefficient": param.coefficient,
            "contribution": contribution,
            "contribution_rank": None,
        })
    ranked = sorted(
        [c for c in contributions if c["feature_name"] != "Intercept"],
        key=lambda c: abs(c["contribution"]),
        reverse=True,
    )
    for rank, contribution in enumerate(ranked, start=1):
        contribution["contribution_rank"] = rank
    rank_by_feature = {c["feature_name"]: c["contribution_rank"] for c in ranked}
    contributions = [
        c if c["feature_name"] == "Intercept" else {**c, "contribution_rank": rank_by_feature[c["feature_name"]]}
        for c in contributions
    ]
    return predicted, contributions


def ridge_prediction_from_row(
    model: RidgeModel,
    row: FeatureRow,
    probability_prediction: base.Prediction,
    evaluation_season: int,
    summary: dict,
) -> RidgePrediction:
    predicted_margin, contributions = predict_margin(model, row)
    return RidgePrediction(
        match=row.match,
        model_name=RIDGE_MODEL_NAME,
        model_version=RIDGE_MODEL_VERSION,
        evaluation_season=evaluation_season,
        training_start=summary["training_start"],
        training_end=summary["training_end"],
        feature_cutoff_date=row.feature_cutoff_date,
        home_win_probability=probability_prediction.home_win_probability,
        draw_probability=probability_prediction.draw_probability,
        away_win_probability=probability_prediction.away_win_probability,
        predicted_margin=predicted_margin,
        contributions=contributions,
    )


def predicted_outcome(prediction: RidgePrediction) -> str:
    if prediction.home_win_probability >= prediction.draw_probability and prediction.home_win_probability >= prediction.away_win_probability:
        return "H"
    if prediction.away_win_probability >= prediction.home_win_probability and prediction.away_win_probability >= prediction.draw_probability:
        return "A"
    return "D"


def evaluate_ridge_prediction(prediction: RidgePrediction) -> dict | None:
    match = prediction.match
    if match.match_status != "Completed" or match.home_score is None or match.away_score is None:
        return None
    outcome = base.actual_outcome(match)
    home_result = base.actual_home_result(match)
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
        "home_probability_brier": base.brier_score(prediction.home_win_probability, home_result),
        "multiclass_brier": base.multiclass_brier(
            prediction.home_win_probability,
            prediction.draw_probability,
            prediction.away_win_probability,
            outcome,
        ),
        "log_loss": base.log_loss(
            prediction.home_win_probability,
            prediction.draw_probability,
            prediction.away_win_probability,
            outcome,
        ),
    }


def calculate_ridge_metrics(evaluations: list[dict]) -> dict:
    metrics = base.calculate_metrics(evaluations)
    if not evaluations:
        return metrics
    abs_errors = [e["absolute_margin_error"] for e in evaluations]
    metrics.update({
        "median_absolute_margin_error": percentile(abs_errors, 0.50),
        "pct_within_5_points": sum(1 for value in abs_errors if value <= 5.0) / len(abs_errors),
        "pct_within_10_points": sum(1 for value in abs_errors if value <= 10.0) / len(abs_errors),
        "pct_within_15_points": sum(1 for value in abs_errors if value <= 15.0) / len(abs_errors),
        "p75_absolute_margin_error": percentile(abs_errors, 0.75),
        "p90_absolute_margin_error": percentile(abs_errors, 0.90),
        "large_error_rate": sum(1 for value in abs_errors if value > LARGE_ERROR_THRESHOLD) / len(abs_errors),
    })
    return metrics


def run_ridge_for_season(
    matches: list[base.Match],
    feature_rows: dict[int, FeatureRow],
    evaluation_season: int,
    alpha: float = RIDGE_ALPHA,
) -> tuple[list[RidgePrediction], list[dict], list[dict], dict, RidgeModel]:
    sorted_all = base.sort_matches(matches)
    train_matches = base.training_matches_for_season(sorted_all, evaluation_season)
    eval_matches = base.sort_matches(base.evaluation_matches_for_season(sorted_all, evaluation_season))
    train_rows = [
        feature_rows[m.match_id]
        for m in train_matches
        if m.match_status == "Completed" and feature_rows.get(m.match_id) and feature_rows[m.match_id].target is not None
    ]
    summary = base.training_summary(train_matches)
    model = fit_ridge_model(train_rows, alpha)
    elo_predictions, _, _, _ = base.run_model_for_season(PROBABILITY_MODEL_NAME, matches, evaluation_season)
    elo_by_match = {prediction.match.match_id: prediction for prediction in elo_predictions}

    predictions = []
    evaluations = []
    for match in eval_matches:
        row = feature_rows[match.match_id]
        prediction = ridge_prediction_from_row(model, row, elo_by_match[match.match_id], evaluation_season, summary)
        predictions.append(prediction)
        evaluation = evaluate_ridge_prediction(prediction)
        if evaluation:
            evaluations.append(evaluation)
    return predictions, evaluations, base.calculate_calibration(evaluations), summary, model


def select_champion_status(ridge: dict[int, dict], benchmark: dict[int, dict]) -> dict:
    seasons = [season for season in COMPLETE_SEASONS if season in ridge and season in benchmark]
    ridge_count = sum(ridge[s]["matches_evaluated"] for s in seasons)
    bench_count = sum(benchmark[s]["matches_evaluated"] for s in seasons)
    ridge_mae = sum(ridge[s]["margin_mae"] * ridge[s]["matches_evaluated"] for s in seasons) / ridge_count if ridge_count else 0.0
    bench_mae = sum(benchmark[s]["margin_mae"] * benchmark[s]["matches_evaluated"] for s in seasons) / bench_count if bench_count else 0.0
    beaten = sum(1 for s in seasons if ridge[s]["margin_mae"] < benchmark[s]["margin_mae"])
    ridge_bias = sum(ridge[s]["mean_margin_error"] * ridge[s]["matches_evaluated"] for s in seasons) / ridge_count if ridge_count else 0.0
    bench_bias = sum(benchmark[s]["mean_margin_error"] * benchmark[s]["matches_evaluated"] for s in seasons) / bench_count if bench_count else 0.0
    ridge_large = sum(ridge[s]["large_error_rate"] * ridge[s]["matches_evaluated"] for s in seasons) / ridge_count if ridge_count else 0.0
    bench_large = sum(benchmark[s].get("large_error_rate", 0.0) * benchmark[s]["matches_evaluated"] for s in seasons) / bench_count if bench_count else 0.0

    criteria = [
        ridge_mae < bench_mae,
        beaten >= 2,
        abs(ridge_bias) <= abs(bench_bias),
        ridge_large <= bench_large,
    ]
    if all(criteria):
        status = "Champion"
    elif criteria[0] or criteria[1]:
        status = "Challenger"
    else:
        status = "Rejected"
    reason = (
        f"Complete seasons={len(seasons)}; weighted MAE ridge={ridge_mae:.3f}, elo={bench_mae:.3f}; "
        f"seasons beaten={beaten}/3; bias ridge={ridge_bias:.3f}, elo={bench_bias:.3f}; "
        f"large-error rate ridge={ridge_large:.3f}, elo={bench_large:.3f}."
    )
    return {
        "status": status,
        "weighted_margin_mae": ridge_mae,
        "benchmark_weighted_margin_mae": bench_mae,
        "complete_seasons_beaten": beaten,
        "overall_bias": ridge_bias,
        "benchmark_overall_bias": bench_bias,
        "large_error_rate": ridge_large,
        "benchmark_large_error_rate": bench_large,
        "reason": reason,
    }


def ensure_model_version(cursor, summary: dict, alpha: float) -> int:
    notes = (
        "Dedicated Ridge Margin Model v0.3.0; target=home margin; "
        f"fixed_alpha={alpha}; probabilities retained from EloOnlyBaseline v0.2.0; "
        "PreMatchEloDiff is generated point-in-time from model state."
    )
    cursor.execute(
        """
        MERGE Gold_ModelVersions AS t
        USING (SELECT ? AS ModelName, ? AS ModelVersion, ? AS TargetName) AS s
        ON t.ModelName = s.ModelName
           AND t.ModelVersion = s.ModelVersion
           AND t.TargetName = s.TargetName
        WHEN MATCHED THEN UPDATE SET TrainingStart = ?, TrainingEnd = ?, Notes = ?
        WHEN NOT MATCHED THEN INSERT (
            ModelName, ModelVersion, TargetName, TrainingStart, TrainingEnd, Notes
        ) VALUES (?, ?, ?, ?, ?, ?);
        """,
        (
            RIDGE_MODEL_NAME, RIDGE_MODEL_VERSION, base.TARGET_NAME,
            summary["training_start"], summary["training_end"], notes,
            RIDGE_MODEL_NAME, RIDGE_MODEL_VERSION, base.TARGET_NAME,
            summary["training_start"], summary["training_end"], notes,
        ),
    )
    return cursor.execute(
        """
        SELECT ModelVersionID FROM Gold_ModelVersions
        WHERE ModelName = ? AND ModelVersion = ? AND TargetName = ?
        """,
        RIDGE_MODEL_NAME,
        RIDGE_MODEL_VERSION,
        base.TARGET_NAME,
    ).fetchone()[0]


def clear_ridge_results(cursor, model_version_id: int, evaluation_season: int) -> None:
    cursor.execute(
        """
        DELETE c
        FROM Gold_PredictionFeatureContributions c
        JOIN Gold_MatchPredictions p ON p.PredictionID = c.PredictionID
        WHERE c.ModelVersionID = ? AND c.EvaluationName = ? AND c.EvaluationSeason = ?
        """,
        model_version_id,
        base.EVALUATION_NAME,
        evaluation_season,
    )
    base.clear_results(cursor, model_version_id, evaluation_season)
    cursor.execute(
        """
        DELETE FROM Gold_RidgeModelParameters
        WHERE ModelVersionID = ? AND EvaluationName = ? AND EvaluationSeason = ?
        """,
        model_version_id,
        base.EVALUATION_NAME,
        evaluation_season,
    )


def upsert_ridge_prediction(cursor, model_version_id: int, prediction: RidgePrediction) -> int:
    cursor.execute(
        """
        MERGE Gold_MatchPredictions AS t
        USING (SELECT ? AS MatchID, ? AS ModelVersionID) AS s
        ON t.MatchID = s.MatchID AND t.ModelVersionID = s.ModelVersionID
        WHEN MATCHED THEN UPDATE SET
            HomeWinProbability = ?,
            AwayWinProbability = ?,
            DrawProbability = ?,
            PredictedHomeScore = NULL,
            PredictedAwayScore = NULL,
            PredictedMargin = ?,
            PredictionMadeAt = SYSUTCDATETIME()
        WHEN NOT MATCHED THEN INSERT (
            MatchID, ModelVersionID, HomeWinProbability, AwayWinProbability,
            DrawProbability, PredictedHomeScore, PredictedAwayScore, PredictedMargin
        ) VALUES (?, ?, ?, ?, ?, NULL, NULL, ?);
        """,
        (
            prediction.match.match_id, model_version_id,
            base.to_decimal(prediction.home_win_probability),
            base.to_decimal(prediction.away_win_probability),
            base.to_decimal(prediction.draw_probability),
            base.to_decimal(prediction.predicted_margin, "0.001"),
            prediction.match.match_id, model_version_id,
            base.to_decimal(prediction.home_win_probability),
            base.to_decimal(prediction.away_win_probability),
            base.to_decimal(prediction.draw_probability),
            base.to_decimal(prediction.predicted_margin, "0.001"),
        ),
    )
    return cursor.execute(
        "SELECT PredictionID FROM Gold_MatchPredictions WHERE MatchID = ? AND ModelVersionID = ?",
        prediction.match.match_id,
        model_version_id,
    ).fetchone()[0]


def insert_ridge_parameters(cursor, model_version_id: int, evaluation_season: int, model: RidgeModel) -> None:
    cursor.execute(
        """
        INSERT INTO Gold_RidgeModelParameters (
            ModelVersionID, EvaluationName, EvaluationSeason, FeatureName, Coefficient,
            FeatureMean, FeatureStdDev, ImputationValue, RidgeAlpha, IsMissingnessIndicator
        ) VALUES (?, ?, ?, ?, ?, NULL, NULL, NULL, ?, 0)
        """,
        model_version_id,
        base.EVALUATION_NAME,
        evaluation_season,
        "Intercept",
        base.to_decimal(model.intercept, "0.000000001"),
        base.to_decimal(model.alpha, "0.000000001"),
    )
    for param in model.parameters:
        cursor.execute(
            """
            INSERT INTO Gold_RidgeModelParameters (
                ModelVersionID, EvaluationName, EvaluationSeason, FeatureName, Coefficient,
                FeatureMean, FeatureStdDev, ImputationValue, RidgeAlpha, IsMissingnessIndicator
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            model_version_id,
            base.EVALUATION_NAME,
            evaluation_season,
            param.feature_name,
            base.to_decimal(param.coefficient, "0.000000001"),
            base.to_decimal(param.feature_mean, "0.000000001"),
            base.to_decimal(param.feature_stddev, "0.000000001"),
            base.to_decimal(param.imputation_value, "0.000000001"),
            base.to_decimal(model.alpha, "0.000000001"),
            1 if param.is_missingness_indicator else 0,
        )


def insert_contributions(cursor, model_version_id: int, prediction_id: int, prediction: RidgePrediction) -> None:
    for contribution in prediction.contributions:
        cursor.execute(
            """
            INSERT INTO Gold_PredictionFeatureContributions (
                PredictionID, ModelVersionID, MatchID, EvaluationName, EvaluationSeason,
                FeatureName, FeatureValue, StandardizedFeatureValue, Coefficient,
                Contribution, ContributionRank
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            prediction_id,
            model_version_id,
            prediction.match.match_id,
            base.EVALUATION_NAME,
            prediction.evaluation_season,
            contribution["feature_name"],
            base.to_decimal(contribution["feature_value"], "0.000000001"),
            base.to_decimal(contribution["standardized_feature_value"], "0.000000001"),
            base.to_decimal(contribution["coefficient"], "0.000000001"),
            base.to_decimal(contribution["contribution"], "0.000000001"),
            contribution["contribution_rank"],
        )


def insert_champion_status(cursor, model_version_id: int, start_season: int, end_season: int, status: dict) -> None:
    cursor.execute(
        """
        MERGE Gold_MarginModelChampionStatus AS t
        USING (
            SELECT ? AS ModelVersionID, ? AS EvaluationName, ? AS EvaluationStartSeason, ? AS EvaluationEndSeason
        ) AS s
        ON t.ModelVersionID = s.ModelVersionID
           AND t.EvaluationName = s.EvaluationName
           AND t.EvaluationStartSeason = s.EvaluationStartSeason
           AND t.EvaluationEndSeason = s.EvaluationEndSeason
        WHEN MATCHED THEN UPDATE SET
            Status = ?, BenchmarkModelName = ?, BenchmarkModelVersion = ?,
            WeightedMarginMAE = ?, BenchmarkWeightedMarginMAE = ?,
            CompleteSeasonsBeaten = ?, OverallBias = ?, LargeErrorRate = ?,
            Reason = ?, CreatedAt = SYSUTCDATETIME()
        WHEN NOT MATCHED THEN INSERT (
            ModelVersionID, EvaluationName, EvaluationStartSeason, EvaluationEndSeason,
            Status, BenchmarkModelName, BenchmarkModelVersion, WeightedMarginMAE,
            BenchmarkWeightedMarginMAE, CompleteSeasonsBeaten, OverallBias,
            LargeErrorRate, Reason
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """,
        (
            model_version_id, base.EVALUATION_NAME, start_season, end_season,
            status["status"], PROBABILITY_MODEL_NAME, PROBABILITY_MODEL_VERSION,
            base.to_decimal(status["weighted_margin_mae"]),
            base.to_decimal(status["benchmark_weighted_margin_mae"]),
            status["complete_seasons_beaten"],
            base.to_decimal(status["overall_bias"]),
            base.to_decimal(status["large_error_rate"]),
            status["reason"],
            model_version_id, base.EVALUATION_NAME, start_season, end_season,
            status["status"], PROBABILITY_MODEL_NAME, PROBABILITY_MODEL_VERSION,
            base.to_decimal(status["weighted_margin_mae"]),
            base.to_decimal(status["benchmark_weighted_margin_mae"]),
            status["complete_seasons_beaten"],
            base.to_decimal(status["overall_bias"]),
            base.to_decimal(status["large_error_rate"]),
            status["reason"],
        ),
    )


def data_quality_checks(predictions: list[RidgePrediction], evaluations: list[dict]) -> list[str]:
    errors = []
    for prediction in predictions:
        if not base.validate_probability_sum(
            prediction.home_win_probability,
            prediction.draw_probability,
            prediction.away_win_probability,
        ):
            errors.append(f"Probabilities do not sum to 1 for match {prediction.match.match_id}")
        predicted_from_parts = sum(c["contribution"] for c in prediction.contributions)
        if abs(predicted_from_parts - prediction.predicted_margin) > 1e-7:
            errors.append(f"Contribution reconciliation failed for match {prediction.match.match_id}")
        if prediction.feature_cutoff_date is not None and prediction.feature_cutoff_date >= prediction.match.match_date:
            errors.append(f"Feature cutoff leaks target match for match {prediction.match.match_id}")
    for evaluation in evaluations:
        if evaluation["prediction"].match.match_status != "Completed":
            errors.append(f"Scheduled match included in evaluation: {evaluation['prediction'].match.match_id}")
    return errors


def metrics_by_season(evaluation_by_season: dict[int, list[dict]]) -> dict[int, dict]:
    return {season: calculate_ridge_metrics(evaluations) for season, evaluations in evaluation_by_season.items()}


def benchmark_metrics_from_db(cursor) -> dict[int, dict]:
    rows = cursor.execute(
        """
        SELECT
            pe.EvaluationSeason,
            COUNT(*) AS MatchesEvaluated,
            AVG(CAST(pe.AbsoluteMarginError AS FLOAT)) AS MarginMAE,
            AVG(CAST(pe.MarginError AS FLOAT)) AS MeanMarginError,
            AVG(CASE WHEN pe.AbsoluteMarginError > ? THEN 1.0 ELSE 0.0 END) AS LargeErrorRate
        FROM Gold_PredictionEvaluations pe
        JOIN Gold_ModelVersions mv ON mv.ModelVersionID = pe.ModelVersionID
        WHERE mv.ModelName = ? AND mv.ModelVersion = ?
          AND pe.EvaluationName = ?
          AND pe.EvaluationSeason IN (2023, 2024, 2025)
        GROUP BY pe.EvaluationSeason
        """,
        LARGE_ERROR_THRESHOLD,
        PROBABILITY_MODEL_NAME,
        PROBABILITY_MODEL_VERSION,
        base.EVALUATION_NAME,
    ).fetchall()
    return {
        int(row.EvaluationSeason): {
            "matches_evaluated": float(row.MatchesEvaluated),
            "margin_mae": float(row.MarginMAE),
            "mean_margin_error": float(row.MeanMarginError),
            "large_error_rate": float(row.LargeErrorRate),
        }
        for row in rows
    }


def print_coefficients(model: RidgeModel) -> None:
    ordered = sorted(model.parameters, key=lambda p: abs(p.coefficient), reverse=True)
    print("Top coefficients:")
    for param in ordered[:10]:
        direction = "positive" if param.coefficient >= 0 else "negative"
        print(f"  {param.feature_name}: {param.coefficient:.4f} ({direction})")


def run(args: argparse.Namespace) -> None:
    if base.pyodbc is None:
        raise RuntimeError("pyodbc is required for database execution")

    conn = base.pyodbc.connect(base.get_connection_string())
    cursor = conn.cursor()
    matches = base.load_matches_from_db(cursor)
    sql_features = load_feature_rows_from_db(cursor)
    feature_rows = build_point_in_time_feature_rows(matches, sql_features)
    eval_seasons = base.walk_forward_splits(matches, args.start_season, args.end_season)
    if args.evaluation_season != "all":
        eval_seasons = [s for s in eval_seasons if s == int(args.evaluation_season)]

    print(f"Model: {RIDGE_MODEL_NAME} {RIDGE_MODEL_VERSION}")
    print(f"Probability component: {PROBABILITY_MODEL_NAME} {PROBABILITY_MODEL_VERSION}")
    print(f"Evaluation seasons: {', '.join(str(s) for s in eval_seasons)}")
    if args.dry_run:
        print("Dry run: no database writes will be made.")

    evaluation_by_season = {}
    model_version_id = None
    last_model = None
    for season in eval_seasons:
        predictions, evaluations, calibration, summary, model = run_ridge_for_season(matches, feature_rows, season, args.alpha)
        last_model = model
        quality_errors = data_quality_checks(predictions, evaluations)
        if quality_errors:
            raise RuntimeError("\n".join(quality_errors))
        metrics = calculate_ridge_metrics(evaluations)
        evaluation_by_season[season] = evaluations
        print(
            f"{season}: predictions={len(predictions)} evaluated={len(evaluations)} "
            f"mae={metrics.get('margin_mae', 0):.3f} rmse={metrics.get('margin_rmse', 0):.3f} "
            f"median_abs={metrics.get('median_absolute_margin_error', 0):.3f} "
            f"bias={metrics.get('mean_margin_error', 0):.3f}"
        )
        print_coefficients(model)

        if args.dry_run:
            continue

        model_version_id = ensure_model_version(cursor, summary, args.alpha)
        existing = base.existing_results(cursor, model_version_id, season)
        if existing and not args.replace:
            raise RuntimeError(
                f"Stored results already exist for {RIDGE_MODEL_NAME} {RIDGE_MODEL_VERSION} season {season}. "
                "Rerun with --replace to overwrite this evaluation window."
            )
        if args.replace:
            clear_ridge_results(cursor, model_version_id, season)

        insert_ridge_parameters(cursor, model_version_id, season, model)
        prediction_id_by_match = {}
        for prediction in predictions:
            prediction_id = upsert_ridge_prediction(cursor, model_version_id, prediction)
            prediction_id_by_match[prediction.match.match_id] = prediction_id
            insert_contributions(cursor, model_version_id, prediction_id, prediction)
        for evaluation in evaluations:
            base.insert_evaluation(
                cursor,
                model_version_id,
                prediction_id_by_match[evaluation["prediction"].match.match_id],
                evaluation,
            )
        base.insert_metrics(cursor, model_version_id, RIDGE_MODEL_NAME, season, evaluations, metrics)
        base.insert_calibration(cursor, model_version_id, season, calibration)
        conn.commit()

    ridge_metrics = metrics_by_season(evaluation_by_season)
    if args.dry_run:
        benchmark = {
            season: {
                "matches_evaluated": metrics["matches_evaluated"],
                "margin_mae": metrics["margin_mae"] + 0.0,
                "mean_margin_error": metrics["mean_margin_error"],
                "large_error_rate": metrics["large_error_rate"],
            }
            for season, metrics in ridge_metrics.items()
        }
    else:
        benchmark = benchmark_metrics_from_db(cursor)
    status = select_champion_status(ridge_metrics, benchmark)
    print(f"Champion status: {status['status']} - {status['reason']}")
    if not args.dry_run and model_version_id is not None:
        insert_champion_status(cursor, model_version_id, min(eval_seasons), max(eval_seasons), status)
        conn.commit()

    if last_model is not None:
        print_coefficients(last_model)
    conn.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Dedicated Ridge Margin Model v0.3")
    parser.add_argument("--evaluation-season", default="all", help="Evaluation season or 'all'")
    parser.add_argument("--start-season", type=int, default=None, help="Optional first evaluation season")
    parser.add_argument("--end-season", type=int, default=None, help="Optional last evaluation season")
    parser.add_argument("--alpha", type=float, default=RIDGE_ALPHA, help="Fixed ridge penalty")
    parser.add_argument("--dry-run", action="store_true", help="Calculate without database writes")
    parser.add_argument("--replace", action="store_true", help="Replace stored results for this model/version/window")
    return parser


def main() -> None:
    run(build_parser().parse_args())


if __name__ == "__main__":
    main()
