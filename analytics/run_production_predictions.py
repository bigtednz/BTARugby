"""
Production Predictions and Reporting Layer v0.4.0.

This command promotes the validated Elo-only champion into auditable production
predictions for scheduled NPC fixtures. It does not train or promote new models.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime

try:
    from analytics import baseline_evaluation as base
    from analytics.kickoff_times import auckland_date_from_utc, local_to_utc
except ModuleNotFoundError:  # Direct script execution: python analytics\run_production_predictions.py
    sys.path.insert(0, os.path.dirname(__file__))
    import baseline_evaluation as base
    from kickoff_times import auckland_date_from_utc, local_to_utc


PROCESS_NAME = "ProductionPredictions_v0.4.0"
PROBABILITY_TARGET = "win_probability"
MARGIN_TARGET = "margin"
CHAMPION_MODEL_NAME = "EloOnlyBaseline"
CHAMPION_MODEL_VERSION = "v0.2.0"
RIDGE_MODEL_NAME = "RidgeMarginModel"
RIDGE_MODEL_VERSION = "v0.3.0"
CONFIDENCE_BANDS = (
    ("Low", 0.0, 0.60),
    ("Moderate", 0.60, 0.70),
    ("High", 0.70, 0.80),
    ("Very High", 0.80, 1.01),
)


@dataclass(frozen=True)
class Champion:
    target_type: str
    model_version_id: int
    model_name: str
    model_version: str


@dataclass(frozen=True)
class ProductionMatch:
    match: base.Match
    venue: str | None
    source_system: str | None
    source_url: str | None
    kickoff_datetime_local: datetime | None = None
    kickoff_datetime_utc: datetime | None = None
    kickoff_time_known: bool = False
    kickoff_time_source: str | None = None


@dataclass(frozen=True)
class ProductionPrediction:
    match: ProductionMatch
    probability_champion: Champion
    margin_champion: Champion
    generated_at: datetime
    feature_cutoff_date: object | None
    home_win_probability: float
    draw_probability: float
    away_win_probability: float
    predicted_home_margin: float
    predicted_winner: str
    confidence_level: str
    home_pre_match_elo: float
    away_pre_match_elo: float
    raw_elo_difference: float
    home_advantage_adjustment: float
    adjusted_elo_difference: float
    probability_contribution: float
    home_prior_matches: int
    away_prior_matches: int
    home_rolling_margin: float | None
    away_rolling_margin: float | None
    rest_days_diff: int | None
    head_to_head_context: float | None
    home_team_sheet_available: bool
    away_team_sheet_available: bool
    data_quality_status: str
    issues: list[dict]


def confidence_level(home: float, draw: float, away: float) -> str:
    largest = max(home, draw, away)
    for label, low, high in CONFIDENCE_BANDS:
        if low <= largest < high:
            return label
    return "Very High"


def predicted_winner(home: float, draw: float, away: float) -> str:
    if home >= draw and home >= away:
        return "H"
    if away >= home and away >= draw:
        return "A"
    return "D"


def is_eligible_scheduled_match(
    match: base.Match,
    season: int | None = None,
    match_id: int | None = None,
    kickoff_datetime_utc: datetime | None = None,
    now_utc: datetime | None = None,
) -> bool:
    if season is not None and match.season != season:
        return False
    if match_id is not None and match.match_id != match_id:
        return False
    if match.match_status != "Scheduled":
        return False
    if match.home_team_id is None or match.away_team_id is None:
        return False
    now_utc = now_utc or datetime.now(UTC).replace(tzinfo=None)
    if kickoff_datetime_utc is not None:
        return kickoff_datetime_utc > now_utc
    # Unknown kickoff times remain eligible before the match date. On the match
    # date itself, skip conservatively because the true kickoff may have passed.
    if match.match_date is not None:
        today_auckland = auckland_date_from_utc(now_utc)
        return match.match_date > today_auckland
    return True


def validate_probability_sum(home: float, draw: float, away: float) -> bool:
    return all(0.0 <= value <= 1.0 for value in (home, draw, away)) and abs(home + draw + away - 1.0) <= 0.001


def champion_registry_issues(champions: list[Champion]) -> list[str]:
    counts = defaultdict(int)
    for champion in champions:
        counts[champion.target_type] += 1
    issues = []
    for target in (PROBABILITY_TARGET, MARGIN_TARGET):
        if counts[target] == 0:
            issues.append(f"Missing active champion for {target}")
        if counts[target] > 1:
            issues.append(f"Multiple active champions for {target}")
    return issues


def should_write_prediction(existing_count: int, replace: bool) -> bool:
    return existing_count == 0 or replace


def load_production_matches(cursor) -> list[ProductionMatch]:
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
            m.MatchStatus,
            m.KickoffDateTimeLocal,
            m.KickoffDateTimeUTC,
            m.KickoffTimeKnownFlag,
            m.KickoffTimeSource,
            v.VenueName,
            m.SourceSystem,
            m.SourceURL
        FROM Silver_Matches m
        JOIN Silver_Seasons s ON s.SeasonID = m.SeasonID
        JOIN Silver_Competitions c ON c.CompetitionID = s.CompetitionID
        JOIN Silver_Teams ht ON ht.TeamID = m.HomeTeamID
        JOIN Silver_Teams at ON at.TeamID = m.AwayTeamID
        LEFT JOIN Silver_Venues v ON v.VenueID = m.VenueID
        WHERE c.CompetitionCode = 'NPC'
        ORDER BY m.MatchDate, m.MatchID
        """
    ).fetchall()
    return [
        ProductionMatch(
            match=base.Match(
                competition_code=row.CompetitionCode,
                season=int(row.Season),
                match_id=int(row.MatchID),
                match_date=row.MatchDate,
                round_name=row.RoundName,
                home_team_id=int(row.HomeTeamID),
                home_team=row.HomeTeam,
                away_team_id=int(row.AwayTeamID),
                away_team=row.AwayTeam,
                home_score=row.HomeScore,
                away_score=row.AwayScore,
                match_status=row.MatchStatus,
            ),
            venue=row.VenueName,
            source_system=row.SourceSystem,
            source_url=row.SourceURL,
            kickoff_datetime_local=row.KickoffDateTimeLocal,
            kickoff_datetime_utc=row.KickoffDateTimeUTC,
            kickoff_time_known=bool(row.KickoffTimeKnownFlag),
            kickoff_time_source=row.KickoffTimeSource,
        )
        for row in rows
    ]


def model_version_id(cursor, model_name: str, model_version: str) -> int:
    row = cursor.execute(
        """
        SELECT ModelVersionID FROM Gold_ModelVersions
        WHERE ModelName = ? AND ModelVersion = ? AND TargetName = ?
        """,
        model_name,
        model_version,
        base.TARGET_NAME,
    ).fetchone()
    if row is None:
        raise RuntimeError(f"Model version not found: {model_name} {model_version}")
    return int(row.ModelVersionID)


def register_deployment(cursor, target_type: str, model_version_id_value: int, status: str, active: bool, reason: str, evidence: str) -> None:
    if active:
        cursor.execute(
            """
            UPDATE Gold_ModelDeploymentStatus
            SET IsActive = 0, EffectiveTo = COALESCE(EffectiveTo, SYSUTCDATETIME())
            WHERE TargetType = ? AND IsActive = 1 AND ModelVersionID <> ?
            """,
            target_type,
            model_version_id_value,
        )
    cursor.execute(
        """
        MERGE Gold_ModelDeploymentStatus AS t
        USING (SELECT ? AS TargetType, ? AS ModelVersionID, ? AS DeploymentStatus) AS s
        ON t.TargetType = s.TargetType
           AND t.ModelVersionID = s.ModelVersionID
           AND t.DeploymentStatus = s.DeploymentStatus
        WHEN MATCHED THEN UPDATE SET
            IsActive = ?,
            EffectiveTo = CASE WHEN ? = 1 THEN NULL ELSE COALESCE(t.EffectiveTo, SYSUTCDATETIME()) END,
            SelectionReason = ?,
            EvaluationEvidence = ?,
            SelectedAt = SYSUTCDATETIME()
        WHEN NOT MATCHED THEN INSERT (
            TargetType, ModelVersionID, DeploymentStatus, IsActive,
            SelectionReason, EvaluationEvidence
        ) VALUES (?, ?, ?, ?, ?, ?);
        """,
        (
            target_type,
            model_version_id_value,
            status,
            1 if active else 0,
            1 if active else 0,
            reason,
            evidence,
            target_type,
            model_version_id_value,
            status,
            1 if active else 0,
            reason,
            evidence,
        ),
    )


def register_default_champions(cursor) -> None:
    elo_id = model_version_id(cursor, CHAMPION_MODEL_NAME, CHAMPION_MODEL_VERSION)
    ridge_id = model_version_id(cursor, RIDGE_MODEL_NAME, RIDGE_MODEL_VERSION)
    register_deployment(
        cursor,
        PROBABILITY_TARGET,
        elo_id,
        "Champion",
        True,
        "EloOnlyBaseline v0.2.0 is the validated active champion for win probability.",
        "Best current probability benchmark across complete 2023-2025 walk-forward seasons.",
    )
    register_deployment(
        cursor,
        MARGIN_TARGET,
        elo_id,
        "Champion",
        True,
        "EloOnlyBaseline v0.2.0 remains the margin incumbent until a better model is validated.",
        "RidgeMarginModel v0.3.0 failed champion criteria; Elo-only weighted MAE 12.81 versus ridge 13.56.",
    )
    register_deployment(
        cursor,
        MARGIN_TARGET,
        ridge_id,
        "Rejected",
        False,
        "RidgeMarginModel v0.3.0 was rejected for margin champion promotion.",
        "Complete-season weighted MAE 13.56; beat Elo-only in 0/3 complete seasons.",
    )


def resolve_active_champions(cursor) -> dict[str, Champion]:
    rows = cursor.execute(
        """
        SELECT ds.TargetType, mv.ModelVersionID, mv.ModelName, mv.ModelVersion
        FROM Gold_ModelDeploymentStatus ds
        JOIN Gold_ModelVersions mv ON mv.ModelVersionID = ds.ModelVersionID
        WHERE ds.IsActive = 1 AND ds.DeploymentStatus = 'Champion'
        """
    ).fetchall()
    champions = {}
    for row in rows:
        if row.TargetType in champions:
            raise RuntimeError(f"Multiple active champions for {row.TargetType}")
        champions[row.TargetType] = Champion(row.TargetType, int(row.ModelVersionID), row.ModelName, row.ModelVersion)
    missing = [target for target in (PROBABILITY_TARGET, MARGIN_TARGET) if target not in champions]
    if missing:
        raise RuntimeError(f"Missing active champion(s): {', '.join(missing)}")
    return champions


def team_sheet_availability(cursor) -> set[tuple[int, int]]:
    rows = cursor.execute(
        """
        SELECT MatchID, TeamID
        FROM Silver_PlayerAppearances
        GROUP BY MatchID, TeamID
        """
    ).fetchall()
    return {(int(row.MatchID), int(row.TeamID)) for row in rows}


def head_to_head_context(matches: list[base.Match], target: base.Match) -> float | None:
    margins = []
    for match in reversed(base.sort_matches(matches)):
        if match.match_id == target.match_id:
            continue
        if match.match_status != "Completed" or match.home_score is None or match.away_score is None:
            continue
        if match.match_date is not None and target.match_date is not None and match.match_date >= target.match_date:
            continue
        home_is_target_home = match.home_team_id == target.home_team_id and match.away_team_id == target.away_team_id
        away_is_target_home = match.home_team_id == target.away_team_id and match.away_team_id == target.home_team_id
        if home_is_target_home:
            margins.append(float(match.home_score - match.away_score))
        elif away_is_target_home:
            margins.append(float(match.away_score - match.home_score))
        if len(margins) == 5:
            break
    return base.average(margins)


def build_state_before_match(matches: list[base.Match], target: base.Match) -> base.ModelState:
    state = base.initialise_state([])
    for match in base.sort_matches(matches):
        if match.match_id == target.match_id:
            break
        if target.match_date is not None and match.match_date is not None and match.match_date >= target.match_date:
            break
        base.update_state_after_match(state, match, update_season_margins=True)
    return state


def context_rest_days(matches: list[base.Match], target: base.Match) -> int | None:
    last_dates = {}
    for match in base.sort_matches(matches):
        if match.match_id == target.match_id:
            break
        if target.match_date is not None and match.match_date is not None and match.match_date >= target.match_date:
            break
        if match.match_status == "Completed":
            last_dates[match.home_team_id] = match.match_date
            last_dates[match.away_team_id] = match.match_date
    home_date = last_dates.get(target.home_team_id)
    away_date = last_dates.get(target.away_team_id)
    if home_date is None or away_date is None or target.match_date is None:
        return None
    return (target.match_date - home_date).days - (target.match_date - away_date).days


def quality_issue(match: ProductionMatch | None, code: str, severity: str, message: str, blocking: bool) -> dict:
    return {
        "match_id": match.match.match_id if match else None,
        "season": match.match.season if match else None,
        "source_system": match.source_system if match else None,
        "issue_code": code,
        "severity": severity,
        "message": message,
        "blocking": blocking,
    }


def build_prediction(
    production_match: ProductionMatch,
    all_matches: list[base.Match],
    champions: dict[str, Champion],
    sheets: set[tuple[int, int]],
    generated_at: datetime,
) -> ProductionPrediction:
    match = production_match.match
    state = build_state_before_match(all_matches, match)
    summary = base.training_summary([m for m in all_matches if m.match_status == "Completed" and m.match_date < match.match_date])
    prediction = base.make_prediction(CHAMPION_MODEL_NAME, match, state, summary, match.season)
    home_elo = state.ratings[match.home_team_id]
    away_elo = state.ratings[match.away_team_id]
    raw_diff = home_elo - away_elo
    adjusted_diff = raw_diff + base.HOME_ADVANTAGE
    home_roll = base.average(state.rolling_margins[match.home_team_id])
    away_roll = base.average(state.rolling_margins[match.away_team_id])
    cutoff = base.feature_cutoff_date(state, match)
    issues = data_quality_issues_for_prediction(production_match, prediction, cutoff, home_elo, away_elo)
    home_sheet = (match.match_id, match.home_team_id) in sheets
    away_sheet = (match.match_id, match.away_team_id) in sheets
    if not home_sheet or not away_sheet:
        issues.append(quality_issue(production_match, "MISSING_TEAM_SHEET", "Warning", "One or both team sheets are missing.", False))
    home_prior = len(state.rolling_margins[match.home_team_id])
    away_prior = len(state.rolling_margins[match.away_team_id])
    if home_prior < 3 or away_prior < 3:
        issues.append(quality_issue(production_match, "INSUFFICIENT_PRIOR_HISTORY", "Warning", "One or both teams have fewer than three rolling prior matches.", False))
    status = "Critical" if any(issue["severity"] == "Critical" for issue in issues) else "Warning" if issues else "OK"
    return ProductionPrediction(
        match=production_match,
        probability_champion=champions[PROBABILITY_TARGET],
        margin_champion=champions[MARGIN_TARGET],
        generated_at=generated_at,
        feature_cutoff_date=cutoff,
        home_win_probability=prediction.home_win_probability,
        draw_probability=prediction.draw_probability,
        away_win_probability=prediction.away_win_probability,
        predicted_home_margin=prediction.predicted_margin,
        predicted_winner=predicted_winner(prediction.home_win_probability, prediction.draw_probability, prediction.away_win_probability),
        confidence_level=confidence_level(prediction.home_win_probability, prediction.draw_probability, prediction.away_win_probability),
        home_pre_match_elo=home_elo,
        away_pre_match_elo=away_elo,
        raw_elo_difference=raw_diff,
        home_advantage_adjustment=base.HOME_ADVANTAGE,
        adjusted_elo_difference=adjusted_diff,
        probability_contribution=prediction.home_win_probability - 0.5,
        home_prior_matches=home_prior,
        away_prior_matches=away_prior,
        home_rolling_margin=home_roll,
        away_rolling_margin=away_roll,
        rest_days_diff=context_rest_days(all_matches, match),
        head_to_head_context=head_to_head_context(all_matches, match),
        home_team_sheet_available=home_sheet,
        away_team_sheet_available=away_sheet,
        data_quality_status=status,
        issues=issues,
    )


def data_quality_issues_for_prediction(production_match: ProductionMatch, prediction: base.Prediction, cutoff: object | None, home_elo: float, away_elo: float) -> list[dict]:
    match = production_match.match
    issues = []
    if match.match_status != "Scheduled":
        issues.append(quality_issue(production_match, "COMPLETED_INCLUDED_AS_UPCOMING", "Critical", "Only scheduled matches can receive production upcoming predictions.", True))
    if match.home_team_id is None or match.away_team_id is None:
        issues.append(quality_issue(production_match, "MISSING_TEAM_IDENTITY", "Critical", "Home or away team identity is missing.", True))
    if home_elo is None or away_elo is None:
        issues.append(quality_issue(production_match, "MISSING_ELO", "Critical", "Pre-match Elo is missing or invalid.", True))
    if not validate_probability_sum(prediction.home_win_probability, prediction.draw_probability, prediction.away_win_probability):
        issues.append(quality_issue(production_match, "INVALID_PROBABILITIES", "Critical", "Probabilities are outside 0-1 or do not sum to one.", True))
    if cutoff is not None and match.match_date is not None and cutoff >= match.match_date:
        issues.append(quality_issue(production_match, "FEATURE_CUTOFF_LEAKAGE", "Critical", "Feature cutoff is at or after kickoff date.", True))
    if production_match.kickoff_time_known and (
        production_match.kickoff_datetime_local is None or production_match.kickoff_datetime_utc is None
    ):
        issues.append(quality_issue(production_match, "KICKOFF_KNOWN_MISSING_DATETIME", "Critical", "Kickoff known flag is set but local or UTC datetime is missing.", True))
    if not production_match.kickoff_time_known and (
        production_match.kickoff_datetime_local is not None or production_match.kickoff_datetime_utc is not None
    ):
        issues.append(quality_issue(production_match, "KICKOFF_DATETIME_WITHOUT_KNOWN_FLAG", "Critical", "Kickoff datetime is populated but known flag is not set.", True))
    if production_match.kickoff_time_known and production_match.kickoff_datetime_local is not None:
        if production_match.kickoff_datetime_local.hour == 0 and production_match.kickoff_datetime_local.minute == 0:
            issues.append(quality_issue(production_match, "KICKOFF_MIDNIGHT_REQUIRES_EVIDENCE", "Warning", "Known kickoff is midnight; verify source evidence.", False))
        if match.match_date is not None and production_match.kickoff_datetime_local.date() != match.match_date:
            issues.append(quality_issue(production_match, "KICKOFF_DATE_MISMATCH", "Critical", "Local kickoff date differs from MatchDate.", True))
    if production_match.kickoff_time_known and production_match.kickoff_datetime_local is not None and production_match.kickoff_datetime_utc is not None:
        converted = local_to_utc(production_match.kickoff_datetime_local)
        if converted != production_match.kickoff_datetime_utc:
            issues.append(quality_issue(production_match, "KICKOFF_UTC_LOCAL_MISMATCH", "Critical", "Stored local and UTC kickoff datetimes are inconsistent.", True))
    if match.home_score == 0 and match.away_score == 0:
        issues.append(quality_issue(production_match, "SCHEDULED_ZERO_ZERO", "Information", "Scheduled fixture has 0-0 score placeholders.", False))
    return issues


def existing_prediction_count(cursor, prediction: ProductionPrediction) -> int:
    return int(cursor.execute(
        """
        SELECT COUNT(*)
        FROM Gold_ProductionPredictions
        WHERE MatchID = ? AND ProbabilityModelVersionID = ? AND MarginModelVersionID = ?
        """,
        prediction.match.match.match_id,
        prediction.probability_champion.model_version_id,
        prediction.margin_champion.model_version_id,
    ).fetchone()[0])


def clear_existing(cursor, prediction: ProductionPrediction) -> None:
    cursor.execute(
        """
        DELETE FROM Gold_ProductionDataQualityIssues
        WHERE ProcessName = ? AND MatchID = ?
        """,
        PROCESS_NAME,
        prediction.match.match.match_id,
    )
    cursor.execute(
        """
        DELETE FROM Gold_ProductionPredictions
        WHERE MatchID = ? AND ProbabilityModelVersionID = ? AND MarginModelVersionID = ?
        """,
        prediction.match.match.match_id,
        prediction.probability_champion.model_version_id,
        prediction.margin_champion.model_version_id,
    )


def insert_prediction(cursor, prediction: ProductionPrediction) -> None:
    cursor.execute(
        """
        INSERT INTO Gold_ProductionPredictions (
            MatchID, ProbabilityModelVersionID, MarginModelVersionID, PredictionGeneratedAt,
            FeatureCutoffDate, HomeWinProbability, DrawProbability, AwayWinProbability,
            PredictedHomeMargin, PredictedWinner, ConfidenceLevel, HomePreMatchElo,
            AwayPreMatchElo, RawEloDifference, HomeAdvantageAdjustment, AdjustedEloDifference,
            ProbabilityContribution, HomePriorMatches, AwayPriorMatches, HomeRollingMargin,
            AwayRollingMargin, RestDaysDiff, HeadToHeadContext, HomeTeamSheetAvailable,
            AwayTeamSheetAvailable, DataQualityStatus
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        prediction.match.match.match_id,
        prediction.probability_champion.model_version_id,
        prediction.margin_champion.model_version_id,
        prediction.generated_at,
        prediction.feature_cutoff_date,
        base.to_decimal(prediction.home_win_probability),
        base.to_decimal(prediction.draw_probability),
        base.to_decimal(prediction.away_win_probability),
        base.to_decimal(prediction.predicted_home_margin, "0.001"),
        prediction.predicted_winner,
        prediction.confidence_level,
        base.to_decimal(prediction.home_pre_match_elo, "0.001"),
        base.to_decimal(prediction.away_pre_match_elo, "0.001"),
        base.to_decimal(prediction.raw_elo_difference, "0.001"),
        base.to_decimal(prediction.home_advantage_adjustment, "0.001"),
        base.to_decimal(prediction.adjusted_elo_difference, "0.001"),
        base.to_decimal(prediction.probability_contribution),
        prediction.home_prior_matches,
        prediction.away_prior_matches,
        base.to_decimal(prediction.home_rolling_margin, "0.001"),
        base.to_decimal(prediction.away_rolling_margin, "0.001"),
        prediction.rest_days_diff,
        base.to_decimal(prediction.head_to_head_context, "0.001"),
        1 if prediction.home_team_sheet_available else 0,
        1 if prediction.away_team_sheet_available else 0,
        prediction.data_quality_status,
    )
    for issue in prediction.issues:
        insert_issue(cursor, issue)


def insert_issue(cursor, issue: dict) -> None:
    cursor.execute(
        """
        INSERT INTO Gold_ProductionDataQualityIssues (
            MatchID, Season, SourceSystem, ProcessName, IssueCode, Severity, IssueMessage, IsBlocking
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        issue["match_id"],
        issue["season"],
        issue["source_system"],
        PROCESS_NAME,
        issue["issue_code"],
        issue["severity"],
        issue["message"],
        1 if issue["blocking"] else 0,
    )


def start_pipeline_run(cursor) -> int:
    cursor.execute(
        """
        INSERT INTO Gold_PipelineRuns (ProcessName, Status, ModelVersion)
        OUTPUT INSERTED.PipelineRunID
        VALUES (?, 'Running', ?)
        """,
        PROCESS_NAME,
        f"{CHAMPION_MODEL_NAME} {CHAMPION_MODEL_VERSION}",
    )
    return int(cursor.fetchone()[0])


def finish_pipeline_run(cursor, run_id: int, status: str, records_read: int, records_written: int, warning_count: int, error_count: int, error_summary: str | None = None) -> None:
    cursor.execute(
        """
        UPDATE Gold_PipelineRuns
        SET CompletedAt = SYSUTCDATETIME(),
            Status = ?,
            RecordsRead = ?,
            RecordsWritten = ?,
            WarningCount = ?,
            ErrorCount = ?,
            ErrorSummary = ?
        WHERE PipelineRunID = ?
        """,
        status,
        records_read,
        records_written,
        warning_count,
        error_count,
        error_summary,
        run_id,
    )


def run(args: argparse.Namespace) -> None:
    if base.pyodbc is None:
        raise RuntimeError("pyodbc is required for database execution")
    conn = base.pyodbc.connect(base.get_connection_string())
    cursor = conn.cursor()
    generated_at = datetime.now(UTC).replace(tzinfo=None)
    run_id = None
    if not args.dry_run:
        run_id = start_pipeline_run(cursor)
        conn.commit()
    try:
        register_default_champions(cursor)
        champions = resolve_active_champions(cursor)
        production_matches = load_production_matches(cursor)
        all_matches = [m.match for m in production_matches]
        sheets = team_sheet_availability(cursor)
        eligible = [
            match for match in production_matches
            if is_eligible_scheduled_match(
                match.match,
                args.season,
                args.match_id,
                match.kickoff_datetime_utc if match.kickoff_time_known else None,
                generated_at,
            )
        ]
        predictions = [
            build_prediction(match, all_matches, champions, sheets, generated_at)
            for match in eligible
        ]
        warnings = sum(1 for prediction in predictions for issue in prediction.issues if issue["severity"] == "Warning")
        errors = sum(1 for prediction in predictions for issue in prediction.issues if issue["severity"] == "Critical")
        print(f"Active probability champion: {champions[PROBABILITY_TARGET].model_name} {champions[PROBABILITY_TARGET].model_version}")
        print(f"Active margin incumbent: {champions[MARGIN_TARGET].model_name} {champions[MARGIN_TARGET].model_version}")
        print(f"Eligible scheduled fixtures: {len(eligible)}")
        print(f"Warnings: {warnings}; critical errors: {errors}")
        if args.dry_run:
            print("Dry run: no database writes will be made.")
            conn.rollback()
            conn.close()
            return
        written = 0
        skipped = 0
        for prediction in predictions:
            existing = existing_prediction_count(cursor, prediction)
            if not should_write_prediction(existing, args.replace):
                skipped += 1
                continue
            if existing and args.replace:
                clear_existing(cursor, prediction)
            if any(issue["severity"] == "Critical" for issue in prediction.issues):
                for issue in prediction.issues:
                    insert_issue(cursor, issue)
                skipped += 1
                continue
            insert_prediction(cursor, prediction)
            written += 1
        if run_id is not None:
            finish_pipeline_run(cursor, run_id, "Succeeded" if errors == 0 else "SucceededWithWarnings", len(eligible), written, warnings, errors)
        conn.commit()
        print(f"Production predictions written: {written}")
        print(f"Excluded/skipped fixtures: {skipped}")
    except Exception as exc:
        if run_id is not None:
            finish_pipeline_run(cursor, run_id, "Failed", 0, 0, 0, 1, str(exc)[:1000])
            conn.commit()
        conn.close()
        raise
    conn.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run production NPC predictions v0.4.0")
    parser.add_argument("--dry-run", action="store_true", help="Calculate without database writes")
    parser.add_argument("--replace", action="store_true", help="Replace existing production predictions for the same match/champion versions")
    parser.add_argument("--season", type=int, default=None, help="Only predict scheduled matches in this season")
    parser.add_argument("--match-id", type=int, default=None, help="Only predict one scheduled match")
    return parser


def main() -> None:
    run(build_parser().parse_args())


if __name__ == "__main__":
    main()
