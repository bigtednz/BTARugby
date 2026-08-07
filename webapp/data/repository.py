"""Read-only SQL repository for BTA Rugby Gold reporting views."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Mapping

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from webapp.config import AppConfig


LOGGER = logging.getLogger(__name__)

FORBIDDEN_SQL = re.compile(r"\b(INSERT|UPDATE|DELETE|MERGE|DROP|ALTER|TRUNCATE|CREATE|EXEC)\b", re.IGNORECASE)


class RepositoryError(RuntimeError):
    """Safe repository error for application display."""


UPCOMING_COLUMNS = [
    "ProductionPredictionID",
    "MatchID",
    "SourceMatchID",
    "Competition",
    "Season",
    "Round",
    "MatchDate",
    "KickoffDateTimeLocal",
    "KickoffDateTimeUTC",
    "KickoffDateTime",
    "KickoffTimeKnownFlag",
    "KickoffTimeStatus",
    "KickoffTimeSource",
    "Venue",
    "HomeTeamID",
    "HomeTeam",
    "AwayTeamID",
    "AwayTeam",
    "MatchStatus",
    "ScoreStatus",
    "ResultReadyFlag",
    "ResultValidationStatus",
    "HomeWinProbability",
    "DrawProbability",
    "AwayWinProbability",
    "PredictedHomeMargin",
    "PredictedWinner",
    "ConfidenceLevel",
    "ProbabilityModelName",
    "ProbabilityModelVersion",
    "MarginModelName",
    "MarginModelVersion",
    "PredictionGeneratedAt",
    "FeatureCutoffDate",
    "DataQualityStatus",
    "HomeTeamSheetAvailable",
    "AwayTeamSheetAvailable",
    "HomePriorMatches",
    "AwayPriorMatches",
]

EXPLANATION_COLUMNS = [
    "ProductionPredictionID",
    "MatchID",
    "HomeTeam",
    "AwayTeam",
    "HomePreMatchElo",
    "AwayPreMatchElo",
    "RawEloDifference",
    "HomeAdvantageAdjustment",
    "AdjustedEloDifference",
    "ProbabilityContribution",
    "HomeWinProbability",
    "DrawProbability",
    "AwayWinProbability",
    "PredictedHomeMargin",
    "ConfidenceLevel",
    "ContextHomeRollingMargin",
    "ContextAwayRollingMargin",
    "ContextRestDaysDiff",
    "ContextHeadToHeadMargin",
    "ContextHomeTeamSheetAvailable",
    "ContextAwayTeamSheetAvailable",
    "ExplanationSummary",
]

RESULT_COLUMNS = [
    "CompetitionCode",
    "Season",
    "MatchID",
    "MatchDate",
    "Round",
    "HomeTeamID",
    "HomeTeam",
    "AwayTeamID",
    "AwayTeam",
    "HomeScore",
    "AwayScore",
    "MatchStatus",
    "ScoreStatus",
    "ResultReadyFlag",
    "ResultValidationStatus",
    "PredictionAvailableFlag",
    "FinalPredictionPredatesKickoffFlag",
    "ProductionEvaluationEligibleFlag",
    "RetrospectiveModelEvaluationEligibleFlag",
    "HomeMargin",
    "ActualOutcome",
    "MatchResult",
    "ProductionPredictionID",
    "PredictedOutcome",
    "CorrectWinner",
    "HomeWinProbability",
    "DrawProbability",
    "AwayWinProbability",
    "PredictedHomeMargin",
    "PredictedWinner",
    "PredictedMarginError",
    "AbsoluteMarginError",
    "PredictionModel",
    "PredictionGeneratedAt",
    "EvaluationStatus",
]

STANDINGS_COLUMNS = [
    "Season",
    "TeamID",
    "TeamName",
    "Played",
    "Won",
    "Drawn",
    "Lost",
    "PointsFor",
    "PointsAgainst",
    "PointsDifference",
    "TablePoints",
]

PLAYER_APPEARANCE_COLUMNS = [
    "Season",
    "MatchID",
    "MatchDate",
    "Round",
    "TeamName",
    "PlayerName",
    "JerseyNumber",
    "Role",
    "SubOnMinute",
    "SubOffMinute",
]

PLAYER_LEADERBOARD_COLUMNS = [
    "Season",
    "MatchID",
    "Team",
    "PlayerName",
    "StatCategory",
    "StatName",
    "Rank",
    "StatValueRaw",
    "StatValue",
    "ScrapedAt",
]

PLAYER_TOP10_COLUMNS = [
    "Season",
    "Competition",
    "Discipline",
    "CalculatedRank",
    "Team",
    "PlayerID",
    "PlayerName",
    "SeasonTotal",
    "Appearances",
    "PerAppearance",
]


def ensure_columns(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    result = frame.copy()
    for column in columns:
        if column not in result.columns:
            result[column] = None
    return result[columns + [column for column in result.columns if column not in columns]]


def assert_read_only(sql: str) -> None:
    if FORBIDDEN_SQL.search(sql):
        raise ValueError("Web application SQL must be read-only")


@dataclass
class MatchCentreRepository:
    config: AppConfig
    engine: Engine | None = None

    def __post_init__(self) -> None:
        if self.engine is None:
            self.engine = create_engine(self.config.sqlalchemy_url(), pool_pre_ping=True, connect_args={"timeout": 5})

    def _read_sql(self, sql: str, params: Mapping | None = None, columns: list[str] | None = None) -> pd.DataFrame:
        assert_read_only(sql)
        try:
            assert self.engine is not None
            with self.engine.connect() as connection:
                frame = pd.read_sql_query(text(sql), connection, params=params or {})
        except (SQLAlchemyError, OSError) as exc:
            LOGGER.exception("Database read failed")
            raise RepositoryError("Unable to read BTA Rugby reporting views") from exc
        except Exception as exc:
            LOGGER.exception("Unexpected repository failure")
            raise RepositoryError("Unable to read BTA Rugby reporting views") from exc
        if columns is not None:
            return ensure_columns(frame, columns)
        return frame

    def upcoming_predictions(self) -> pd.DataFrame:
        return self._read_sql(
            """
            SELECT *
            FROM dbo.vw_Gold_ProductionUpcomingPredictions
            ORDER BY MatchDate, KickoffDateTimeLocal, MatchID
            """,
            columns=UPCOMING_COLUMNS,
        )

    def completed_results(self) -> pd.DataFrame:
        return self._read_sql(
            """
            SELECT *
            FROM dbo.vw_Gold_ProductionResults
            ORDER BY MatchDate DESC, MatchID DESC
            """,
            columns=RESULT_COLUMNS,
        )

    def standings(self) -> pd.DataFrame:
        return self._read_sql(
            """
            SELECT
                Season,
                TeamID,
                TeamName,
                COUNT(*) AS Played,
                SUM(CASE WHEN PointsFor > PointsAgainst THEN 1 ELSE 0 END) AS Won,
                SUM(CASE WHEN PointsFor = PointsAgainst THEN 1 ELSE 0 END) AS Drawn,
                SUM(CASE WHEN PointsFor < PointsAgainst THEN 1 ELSE 0 END) AS Lost,
                SUM(PointsFor) AS PointsFor,
                SUM(PointsAgainst) AS PointsAgainst,
                SUM(Margin) AS PointsDifference,
                SUM(CASE WHEN PointsFor > PointsAgainst THEN 4 WHEN PointsFor = PointsAgainst THEN 2 ELSE 0 END) AS TablePoints
            FROM (
                SELECT
                    Season,
                    HomeTeamID AS TeamID,
                    HomeTeam AS TeamName,
                    HomeScore AS PointsFor,
                    AwayScore AS PointsAgainst,
                    HomeMargin AS Margin
                FROM dbo.vw_Gold_ProductionResults
                WHERE ResultReadyFlag = 1
                UNION ALL
                SELECT
                    Season,
                    AwayTeamID AS TeamID,
                    AwayTeam AS TeamName,
                    AwayScore AS PointsFor,
                    HomeScore AS PointsAgainst,
                    -HomeMargin AS Margin
                FROM dbo.vw_Gold_ProductionResults
                WHERE ResultReadyFlag = 1
            ) r
            GROUP BY Season, TeamID, TeamName
            ORDER BY Season DESC, TablePoints DESC, PointsDifference DESC, PointsFor DESC, TeamName
            """,
            columns=STANDINGS_COLUMNS,
        )

    def player_appearances(self) -> pd.DataFrame:
        return self._read_sql(
            """
            SELECT
                s.Season,
                a.MatchID,
                m.MatchDate,
                m.RoundName AS Round,
                t.TeamName,
                p.PlayerName,
                a.JerseyNumber,
                CASE
                    WHEN a.IsStarter = 1 THEN 'Starter'
                    WHEN a.IsSubstitute = 1 THEN 'Substitute'
                    ELSE 'Listed'
                END AS Role,
                a.SubOnMinute,
                a.SubOffMinute
            FROM dbo.Silver_PlayerAppearances a
            JOIN dbo.Silver_Players p ON p.PlayerID = a.PlayerID
            JOIN dbo.Silver_Teams t ON t.TeamID = a.TeamID
            JOIN dbo.Silver_Matches m ON m.MatchID = a.MatchID
            JOIN dbo.Silver_Seasons s ON s.SeasonID = m.SeasonID
            JOIN dbo.Silver_Competitions c ON c.CompetitionID = s.CompetitionID
            WHERE c.CompetitionCode = 'NPC'
            ORDER BY s.Season DESC, m.MatchDate DESC, a.MatchID DESC, t.TeamName, a.JerseyNumber, p.PlayerName
            """,
            columns=PLAYER_APPEARANCE_COLUMNS,
        )

    def player_leaderboards(self) -> pd.DataFrame:
        return self._read_sql(
            """
            SELECT
                Season,
                MatchID,
                Team,
                PlayerName,
                StatCategory,
                StatName,
                Rank,
                StatValueRaw,
                StatValue,
                ScrapedAt
            FROM dbo.NPC_PlayerStats
            ORDER BY Season DESC, MatchID DESC, StatName, Rank
            """,
            columns=PLAYER_LEADERBOARD_COLUMNS,
        )

    def player_top10_by_stat(self) -> pd.DataFrame:
        return self._read_sql(
            """
            SELECT *
            FROM dbo.vw_Gold_PlayerTop10ByDiscipline
            ORDER BY Season DESC, Discipline, CalculatedRank, PlayerName
            """,
            columns=PLAYER_TOP10_COLUMNS,
        )

    def upcoming_prediction(self, match_id: int) -> pd.DataFrame:
        return self._read_sql(
            """
            SELECT *
            FROM dbo.vw_Gold_ProductionUpcomingPredictions
            WHERE MatchID = :match_id
            """,
            {"match_id": int(match_id)},
            UPCOMING_COLUMNS,
        )

    def match_explanation(self, match_id: int) -> pd.DataFrame:
        return self._read_sql(
            """
            SELECT *
            FROM dbo.vw_Gold_ProductionMatchExplanation
            WHERE MatchID = :match_id
            """,
            {"match_id": int(match_id)},
            EXPLANATION_COLUMNS,
        )

    def model_summary(self) -> pd.DataFrame:
        return self._read_sql("SELECT * FROM dbo.vw_Gold_ProductionModelSummary ORDER BY TargetType, IsActive DESC")

    def model_performance(self) -> pd.DataFrame:
        return self._read_sql(
            """
            SELECT *
            FROM dbo.vw_Gold_ModelPerformanceComparison
            ORDER BY ModelName, ModelVersion, EvaluationSeason
            """
        )

    def calibration(self) -> pd.DataFrame:
        return self._read_sql("SELECT * FROM dbo.vw_Gold_ProductionCalibration ORDER BY ModelName, ModelVersion, EvaluationSeason, BandStart")

    def data_quality(self) -> pd.DataFrame:
        return self._read_sql("SELECT * FROM dbo.vw_Gold_ProductionDataQuality ORDER BY DetectedAt DESC")

    def pipeline_runs(self) -> pd.DataFrame:
        return self._read_sql("SELECT * FROM dbo.vw_Gold_ProductionPipelineRuns ORDER BY StartedAt DESC")
