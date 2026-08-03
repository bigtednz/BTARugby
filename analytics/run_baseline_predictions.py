"""
Run the first transparent NPC prediction baseline.

The model combines:
- pre-match Elo rating difference
- fixed home advantage
- rolling five-match margin difference

It writes one prediction per Silver match and stores backtest metrics for
completed matches in Gold_BacktestResults.
"""

from __future__ import annotations

import math
from collections import defaultdict, deque
from decimal import Decimal

import pyodbc


SQL_CONNECTION_STRING = (
    "DRIVER={ODBC Driver 17 for SQL Server};"
    "SERVER=BIGTEDS;"
    "DATABASE=RugbyAnalytics;"
    "Trusted_Connection=yes;"
    "Encrypt=no;"
    "TrustServerCertificate=yes;"
)

MODEL_NAME = "EloRollingMarginBaseline"
MODEL_VERSION = "v0.1.0"
TARGET_NAME = "home_margin_and_result"
BASE_ELO = 1500.0
HOME_ADVANTAGE = 55.0
K_FACTOR = 24.0
MARGIN_ELO_SCALE = 10.0
ELO_MARGIN_POINTS_SCALE = 0.035
ROLLING_MARGIN_WEIGHT = 0.35
DEFAULT_TOTAL_POINTS = 51.0


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def avg(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def to_decimal(value: float | None, places: str = "0.000001") -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value)).quantize(Decimal(places))


def expected_score(rating_a: float, rating_b: float) -> float:
    return 1.0 / (1.0 + math.pow(10.0, (rating_b - rating_a) / 400.0))


def margin_multiplier(margin: float) -> float:
    # Keeps blowouts meaningful without letting them dominate future ratings.
    return math.log(abs(margin) + 1.0)


def load_matches(cursor) -> list[dict]:
    rows = cursor.execute(
        """
        SELECT
            c.CompetitionCode,
            s.Season,
            m.MatchID,
            m.MatchDate,
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

    columns = [col[0] for col in cursor.description]
    return [dict(zip(columns, row)) for row in rows]


def upsert_model_version(cursor, matches: list[dict]) -> int:
    completed_dates = [
        m["MatchDate"]
        for m in matches
        if m["MatchStatus"] == "Completed" and m["MatchDate"] is not None
    ]
    training_start = min(completed_dates) if completed_dates else None
    training_end = max(completed_dates) if completed_dates else None
    notes = (
        f"BASE_ELO={BASE_ELO}; HOME_ADVANTAGE={HOME_ADVANTAGE}; "
        f"K_FACTOR={K_FACTOR}; MARGIN_ELO_SCALE={MARGIN_ELO_SCALE}; "
        f"ELO_MARGIN_POINTS_SCALE={ELO_MARGIN_POINTS_SCALE}; "
        f"ROLLING_MARGIN_WEIGHT={ROLLING_MARGIN_WEIGHT}"
    )

    cursor.execute(
        """
        MERGE Gold_ModelVersions AS t
        USING (
            SELECT ? AS ModelName, ? AS ModelVersion, ? AS TargetName
        ) AS s
        ON t.ModelName = s.ModelName
           AND t.ModelVersion = s.ModelVersion
           AND t.TargetName = s.TargetName
        WHEN MATCHED THEN UPDATE SET
            TrainingStart = ?,
            TrainingEnd = ?,
            Notes = ?
        WHEN NOT MATCHED THEN INSERT (
            ModelName, ModelVersion, TargetName, TrainingStart, TrainingEnd, Notes
        ) VALUES (
            ?, ?, ?, ?, ?, ?
        );
        """,
        (
            MODEL_NAME,
            MODEL_VERSION,
            TARGET_NAME,
            training_start,
            training_end,
            notes,
            MODEL_NAME,
            MODEL_VERSION,
            TARGET_NAME,
            training_start,
            training_end,
            notes,
        ),
    )
    return cursor.execute(
        """
        SELECT ModelVersionID
        FROM Gold_ModelVersions
        WHERE ModelName = ? AND ModelVersion = ? AND TargetName = ?
        """,
        MODEL_NAME,
        MODEL_VERSION,
        TARGET_NAME,
    ).fetchone()[0]


def upsert_prediction(cursor, model_version_id: int, prediction: dict) -> None:
    cursor.execute(
        """
        MERGE Gold_MatchPredictions AS t
        USING (
            SELECT ? AS MatchID, ? AS ModelVersionID
        ) AS s
        ON t.MatchID = s.MatchID
           AND t.ModelVersionID = s.ModelVersionID
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
            DrawProbability, PredictedHomeScore, PredictedAwayScore,
            PredictedMargin
        ) VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?
        );
        """,
        (
            prediction["match_id"],
            model_version_id,
            to_decimal(prediction["home_win_probability"]),
            to_decimal(prediction["away_win_probability"]),
            to_decimal(prediction["draw_probability"]),
            to_decimal(prediction["predicted_home_score"], "0.001"),
            to_decimal(prediction["predicted_away_score"], "0.001"),
            to_decimal(prediction["predicted_margin"], "0.001"),
            prediction["match_id"],
            model_version_id,
            to_decimal(prediction["home_win_probability"]),
            to_decimal(prediction["away_win_probability"]),
            to_decimal(prediction["draw_probability"]),
            to_decimal(prediction["predicted_home_score"], "0.001"),
            to_decimal(prediction["predicted_away_score"], "0.001"),
            to_decimal(prediction["predicted_margin"], "0.001"),
        ),
    )


def insert_backtest_metrics(cursor, model_version_id: int, metrics: dict) -> None:
    cursor.execute(
        "DELETE FROM Gold_BacktestResults WHERE ModelVersionID = ?",
        model_version_id,
    )
    evaluation_start = metrics.pop("evaluation_start")
    evaluation_end = metrics.pop("evaluation_end")
    for name, value in metrics.items():
        cursor.execute(
            """
            INSERT INTO Gold_BacktestResults (
                ModelVersionID, EvaluationStart, EvaluationEnd,
                MetricName, MetricValue, BaselineName
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                model_version_id,
                evaluation_start,
                evaluation_end,
                name,
                to_decimal(value) if isinstance(value, float) else value,
                MODEL_NAME,
            ),
        )


def run() -> None:
    conn = pyodbc.connect(SQL_CONNECTION_STRING)
    cursor = conn.cursor()
    matches = load_matches(cursor)
    model_version_id = upsert_model_version(cursor, matches)

    ratings = defaultdict(lambda: BASE_ELO)
    margins = defaultdict(lambda: deque(maxlen=5))
    completed_totals = deque(maxlen=50)
    backtest = []

    for match in matches:
        home_team_id = match["HomeTeamID"]
        away_team_id = match["AwayTeamID"]
        home_rating = ratings[home_team_id]
        away_rating = ratings[away_team_id]
        home_recent_margin = avg(list(margins[home_team_id])) or 0.0
        away_recent_margin = avg(list(margins[away_team_id])) or 0.0
        rolling_margin_diff = home_recent_margin - away_recent_margin

        elo_diff = home_rating + HOME_ADVANTAGE - away_rating
        combined_rating_diff = elo_diff + (rolling_margin_diff * MARGIN_ELO_SCALE)
        raw_home_probability = expected_score(combined_rating_diff, 0.0)
        predicted_margin = (
            elo_diff * ELO_MARGIN_POINTS_SCALE
            + rolling_margin_diff * ROLLING_MARGIN_WEIGHT
        )
        draw_probability = 0.06 if abs(predicted_margin) < 2.0 else 0.025
        home_win_probability = raw_home_probability * (1.0 - draw_probability)
        away_win_probability = 1.0 - draw_probability - home_win_probability

        expected_total = avg(list(completed_totals)) or DEFAULT_TOTAL_POINTS
        predicted_home_score = clamp((expected_total + predicted_margin) / 2.0, 0.0, 80.0)
        predicted_away_score = clamp(expected_total - predicted_home_score, 0.0, 80.0)

        prediction = {
            "match_id": match["MatchID"],
            "home_win_probability": home_win_probability,
            "away_win_probability": away_win_probability,
            "draw_probability": draw_probability,
            "predicted_home_score": predicted_home_score,
            "predicted_away_score": predicted_away_score,
            "predicted_margin": predicted_margin,
        }
        upsert_prediction(cursor, model_version_id, prediction)

        if match["MatchStatus"] == "Completed":
            home_score = match["HomeScore"]
            away_score = match["AwayScore"]
            if home_score is None or away_score is None:
                continue

            actual_margin = float(home_score - away_score)
            actual_home_result = 1.0 if actual_margin > 0 else 0.5 if actual_margin == 0 else 0.0
            predicted_home_win = home_win_probability >= away_win_probability
            actual_home_win = actual_home_result == 1.0
            backtest.append(
                {
                    "match_date": match["MatchDate"],
                    "margin_error": predicted_margin - actual_margin,
                    "correct_winner": 1.0 if predicted_home_win == actual_home_win else 0.0,
                    "home_probability": home_win_probability,
                    "actual_home_result": actual_home_result,
                }
            )

            expected_home = expected_score(home_rating + HOME_ADVANTAGE, away_rating)
            rating_delta = K_FACTOR * margin_multiplier(actual_margin) * (actual_home_result - expected_home)
            ratings[home_team_id] += rating_delta
            ratings[away_team_id] -= rating_delta
            margins[home_team_id].append(actual_margin)
            margins[away_team_id].append(-actual_margin)
            completed_totals.append(float(home_score + away_score))

    completed = [row for row in backtest if row["actual_home_result"] in (0.0, 1.0)]
    margin_errors = [row["margin_error"] for row in backtest]
    probability_errors = [
        row["home_probability"] - row["actual_home_result"]
        for row in backtest
    ]
    metrics = {
        "evaluation_start": min(row["match_date"] for row in backtest),
        "evaluation_end": max(row["match_date"] for row in backtest),
        "matches_evaluated": float(len(backtest)),
        "non_draw_matches_evaluated": float(len(completed)),
        "winner_accuracy": sum(row["correct_winner"] for row in completed) / len(completed),
        "margin_mae": sum(abs(err) for err in margin_errors) / len(margin_errors),
        "margin_rmse": math.sqrt(sum(err * err for err in margin_errors) / len(margin_errors)),
        "home_probability_brier": sum(err * err for err in probability_errors) / len(probability_errors),
    }
    insert_backtest_metrics(cursor, model_version_id, metrics)
    conn.commit()
    conn.close()

    print(f"ModelVersionID: {model_version_id}")
    print(f"Predictions written: {len(matches)}")
    print(f"Completed matches evaluated: {len(backtest)}")
    print(f"Winner accuracy: {metrics['winner_accuracy']:.3f}")
    print(f"Margin MAE: {metrics['margin_mae']:.3f}")
    print(f"Margin RMSE: {metrics['margin_rmse']:.3f}")
    print(f"Home probability Brier: {metrics['home_probability_brier']:.3f}")


if __name__ == "__main__":
    run()
