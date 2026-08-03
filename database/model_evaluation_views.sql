-- ============================================================
-- Gold model evaluation reporting views
-- Run after platform_schema.sql and analytics/baseline_evaluation.py
-- ============================================================

USE RugbyAnalytics;
GO

CREATE OR ALTER VIEW vw_Gold_ModelPerformanceComparison AS
SELECT
    mv.ModelVersionID,
    mv.ModelName,
    mv.ModelVersion,
    mv.TargetName,
    br.EvaluationName,
    br.EvaluationSeason,
    MIN(br.EvaluationStart) AS EvaluationStart,
    MAX(br.EvaluationEnd) AS EvaluationEnd,
    MAX(CASE WHEN br.MetricName = 'matches_evaluated' THEN br.MetricValue END) AS MatchesEvaluated,
    MAX(CASE WHEN br.MetricName = 'non_draw_matches_evaluated' THEN br.MetricValue END) AS NonDrawMatchesEvaluated,
    MAX(CASE WHEN br.MetricName = 'winner_accuracy' THEN br.MetricValue END) AS WinnerAccuracy,
    MAX(CASE WHEN br.MetricName = 'home_probability_brier' THEN br.MetricValue END) AS HomeProbabilityBrier,
    MAX(CASE WHEN br.MetricName = 'multiclass_brier' THEN br.MetricValue END) AS MulticlassBrier,
    MAX(CASE WHEN br.MetricName = 'log_loss' THEN br.MetricValue END) AS LogLoss,
    MAX(CASE WHEN br.MetricName = 'margin_mae' THEN br.MetricValue END) AS MarginMAE,
    MAX(CASE WHEN br.MetricName = 'margin_rmse' THEN br.MetricValue END) AS MarginRMSE,
    MAX(CASE WHEN br.MetricName = 'median_absolute_margin_error' THEN br.MetricValue END) AS MedianAbsoluteMarginError,
    MAX(CASE WHEN br.MetricName = 'mean_margin_error' THEN br.MetricValue END) AS MeanMarginError,
    MAX(CASE WHEN br.MetricName = 'pct_within_5_points' THEN br.MetricValue END) AS PctWithin5Points,
    MAX(CASE WHEN br.MetricName = 'pct_within_10_points' THEN br.MetricValue END) AS PctWithin10Points,
    MAX(CASE WHEN br.MetricName = 'pct_within_15_points' THEN br.MetricValue END) AS PctWithin15Points,
    MAX(CASE WHEN br.MetricName = 'p75_absolute_margin_error' THEN br.MetricValue END) AS P75AbsoluteMarginError,
    MAX(CASE WHEN br.MetricName = 'p90_absolute_margin_error' THEN br.MetricValue END) AS P90AbsoluteMarginError,
    MAX(CASE WHEN br.MetricName = 'large_error_rate' THEN br.MetricValue END) AS LargeErrorRate,
    MAX(CASE WHEN br.MetricName = 'actual_home_win_rate' THEN br.MetricValue END) AS ActualHomeWinRate,
    MAX(CASE WHEN br.MetricName = 'mean_predicted_home_win_probability' THEN br.MetricValue END) AS MeanPredictedHomeWinProbability
FROM Gold_BacktestResults br
JOIN Gold_ModelVersions mv ON mv.ModelVersionID = br.ModelVersionID
GROUP BY
    mv.ModelVersionID,
    mv.ModelName,
    mv.ModelVersion,
    mv.TargetName,
    br.EvaluationName,
    br.EvaluationSeason;
GO

CREATE OR ALTER VIEW vw_Gold_ModelCalibration AS
SELECT
    mv.ModelVersionID,
    mv.ModelName,
    mv.ModelVersion,
    c.EvaluationName,
    c.EvaluationSeason,
    c.ConfidenceBand,
    c.BandStart,
    c.BandEnd,
    c.PredictionCount,
    c.MeanHomeWinProbability,
    c.ActualHomeWinRate,
    c.CalibrationGap,
    c.WinnerAccuracy,
    c.MeanAbsoluteMarginError
FROM Gold_ModelCalibration c
JOIN Gold_ModelVersions mv ON mv.ModelVersionID = c.ModelVersionID;
GO

CREATE OR ALTER VIEW vw_Gold_ModelPerformanceByTeam AS
SELECT
    mv.ModelVersionID,
    mv.ModelName,
    mv.ModelVersion,
    pe.EvaluationName,
    pe.EvaluationSeason,
    pe.HomeTeamID AS TeamID,
    ht.TeamName,
    'H' AS HomeAway,
    COUNT(*) AS MatchesEvaluated,
    AVG(CAST(pe.CorrectWinner AS FLOAT)) AS WinnerAccuracy,
    AVG(CAST(pe.HomeProbabilityBrier AS FLOAT)) AS HomeProbabilityBrier,
    AVG(CAST(pe.AbsoluteMarginError AS FLOAT)) AS MarginMAE,
    AVG(CAST(pe.MarginError AS FLOAT)) AS MeanMarginError,
    AVG(CAST(CASE WHEN pe.ActualOutcome = 'H' THEN 1.0 ELSE 0.0 END AS FLOAT)) AS ActualWinRate,
    AVG(CAST(CASE WHEN pe.PredictedOutcome = 'H' THEN 1.0 ELSE 0.0 END AS FLOAT)) AS PredictedWinPickRate
FROM Gold_PredictionEvaluations pe
JOIN Gold_ModelVersions mv ON mv.ModelVersionID = pe.ModelVersionID
JOIN Silver_Teams ht ON ht.TeamID = pe.HomeTeamID
GROUP BY
    mv.ModelVersionID,
    mv.ModelName,
    mv.ModelVersion,
    pe.EvaluationName,
    pe.EvaluationSeason,
    pe.HomeTeamID,
    ht.TeamName
UNION ALL
SELECT
    mv.ModelVersionID,
    mv.ModelName,
    mv.ModelVersion,
    pe.EvaluationName,
    pe.EvaluationSeason,
    pe.AwayTeamID AS TeamID,
    at.TeamName,
    'A' AS HomeAway,
    COUNT(*) AS MatchesEvaluated,
    AVG(CAST(pe.CorrectWinner AS FLOAT)) AS WinnerAccuracy,
    AVG(CAST(pe.HomeProbabilityBrier AS FLOAT)) AS HomeProbabilityBrier,
    AVG(CAST(pe.AbsoluteMarginError AS FLOAT)) AS MarginMAE,
    AVG(CAST(-pe.MarginError AS FLOAT)) AS MeanMarginError,
    AVG(CAST(CASE WHEN pe.ActualOutcome = 'A' THEN 1.0 ELSE 0.0 END AS FLOAT)) AS ActualWinRate,
    AVG(CAST(CASE WHEN pe.PredictedOutcome = 'A' THEN 1.0 ELSE 0.0 END AS FLOAT)) AS PredictedWinPickRate
FROM Gold_PredictionEvaluations pe
JOIN Gold_ModelVersions mv ON mv.ModelVersionID = pe.ModelVersionID
JOIN Silver_Teams at ON at.TeamID = pe.AwayTeamID
GROUP BY
    mv.ModelVersionID,
    mv.ModelName,
    mv.ModelVersion,
    pe.EvaluationName,
    pe.EvaluationSeason,
    pe.AwayTeamID,
    at.TeamName;
GO

CREATE OR ALTER VIEW vw_Gold_ModelPerformanceByRoundBand AS
SELECT
    mv.ModelVersionID,
    mv.ModelName,
    mv.ModelVersion,
    pe.EvaluationName,
    pe.EvaluationSeason,
    pe.RoundBand,
    COUNT(*) AS MatchesEvaluated,
    AVG(CAST(pe.CorrectWinner AS FLOAT)) AS WinnerAccuracy,
    AVG(CAST(pe.HomeProbabilityBrier AS FLOAT)) AS HomeProbabilityBrier,
    AVG(CAST(pe.MulticlassBrier AS FLOAT)) AS MulticlassBrier,
    AVG(CAST(pe.LogLoss AS FLOAT)) AS LogLoss,
    AVG(CAST(pe.AbsoluteMarginError AS FLOAT)) AS MarginMAE,
    SQRT(AVG(CAST(pe.SquaredMarginError AS FLOAT))) AS MarginRMSE,
    AVG(CAST(pe.MarginError AS FLOAT)) AS MeanMarginError
FROM Gold_PredictionEvaluations pe
JOIN Gold_ModelVersions mv ON mv.ModelVersionID = pe.ModelVersionID
GROUP BY
    mv.ModelVersionID,
    mv.ModelName,
    mv.ModelVersion,
    pe.EvaluationName,
    pe.EvaluationSeason,
    pe.RoundBand;
GO

CREATE OR ALTER VIEW vw_Gold_RidgeModelParameters AS
SELECT
    mv.ModelVersionID,
    mv.ModelName,
    mv.ModelVersion,
    p.EvaluationName,
    p.EvaluationSeason,
    p.FeatureName,
    p.Coefficient,
    p.FeatureMean,
    p.FeatureStdDev,
    p.ImputationValue,
    p.RidgeAlpha,
    p.IsMissingnessIndicator,
    p.CreatedAt
FROM Gold_RidgeModelParameters p
JOIN Gold_ModelVersions mv ON mv.ModelVersionID = p.ModelVersionID;
GO

CREATE OR ALTER VIEW vw_Gold_RidgePredictionExplanation AS
SELECT
    mv.ModelVersionID,
    mv.ModelName,
    mv.ModelVersion,
    c.EvaluationName,
    c.EvaluationSeason,
    c.MatchID,
    m.MatchDate,
    ht.TeamName AS HomeTeam,
    at.TeamName AS AwayTeam,
    p.PredictedMargin,
    c.FeatureName,
    c.FeatureValue,
    c.StandardizedFeatureValue,
    c.Coefficient,
    c.Contribution,
    c.ContributionRank,
    CASE
        WHEN c.Contribution > 0 THEN 'Positive'
        WHEN c.Contribution < 0 THEN 'Negative'
        ELSE 'Neutral'
    END AS ContributionDirection
FROM Gold_PredictionFeatureContributions c
JOIN Gold_MatchPredictions p ON p.PredictionID = c.PredictionID
JOIN Gold_ModelVersions mv ON mv.ModelVersionID = c.ModelVersionID
JOIN Silver_Matches m ON m.MatchID = c.MatchID
JOIN Silver_Teams ht ON ht.TeamID = m.HomeTeamID
JOIN Silver_Teams at ON at.TeamID = m.AwayTeamID;
GO

CREATE OR ALTER VIEW vw_Gold_RidgeStrongestDrivers AS
SELECT *
FROM vw_Gold_RidgePredictionExplanation
WHERE ContributionRank BETWEEN 1 AND 3;
GO

CREATE OR ALTER VIEW vw_Gold_MarginModelComparison AS
SELECT
    ModelVersionID,
    ModelName,
    ModelVersion,
    EvaluationName,
    EvaluationSeason,
    MatchesEvaluated,
    MarginMAE,
    MarginRMSE,
    MedianAbsoluteMarginError,
    MeanMarginError,
    PctWithin5Points,
    PctWithin10Points,
    PctWithin15Points,
    P75AbsoluteMarginError,
    P90AbsoluteMarginError,
    LargeErrorRate
FROM vw_Gold_ModelPerformanceComparison
WHERE ModelVersion IN ('v0.2.0', 'v0.3.0')
  AND ModelName IN (
      'EloOnlyBaseline',
      'EloRollingMarginBaseline',
      'RollingMarginOnlyBaseline',
      'SeasonToDateMarginBaseline',
      'RidgeMarginModel'
  );
GO

CREATE OR ALTER VIEW vw_Gold_MarginChampionStatus AS
SELECT
    mv.ModelVersionID,
    mv.ModelName,
    mv.ModelVersion,
    s.EvaluationName,
    s.EvaluationStartSeason,
    s.EvaluationEndSeason,
    s.Status,
    s.BenchmarkModelName,
    s.BenchmarkModelVersion,
    s.WeightedMarginMAE,
    s.BenchmarkWeightedMarginMAE,
    s.CompleteSeasonsBeaten,
    s.OverallBias,
    s.LargeErrorRate,
    s.Reason,
    s.CreatedAt
FROM Gold_MarginModelChampionStatus s
JOIN Gold_ModelVersions mv ON mv.ModelVersionID = s.ModelVersionID;
GO

CREATE OR ALTER VIEW vw_Gold_CombinedUpcomingPredictions AS
SELECT
    c.CombinedForwardPredictionID,
    c.MatchID,
    s.Season,
    m.MatchDate,
    m.RoundName,
    ht.TeamName AS HomeTeam,
    at.TeamName AS AwayTeam,
    c.ProbabilityModelName,
    c.ProbabilityModelVersion,
    c.MarginModelName,
    c.MarginModelVersion,
    c.HomeWinProbability,
    c.DrawProbability,
    c.AwayWinProbability,
    c.PredictedMargin,
    c.ScorePredictionMethod,
    c.CreatedAt
FROM Gold_CombinedForwardPredictions c
JOIN Silver_Matches m ON m.MatchID = c.MatchID
JOIN Silver_Seasons s ON s.SeasonID = m.SeasonID
JOIN Silver_Teams ht ON ht.TeamID = m.HomeTeamID
JOIN Silver_Teams at ON at.TeamID = m.AwayTeamID
WHERE m.MatchStatus <> 'Completed';
GO

CREATE OR ALTER VIEW vw_Gold_ProductionUpcomingPredictions AS
SELECT
    pp.ProductionPredictionID,
    m.MatchID,
    m.MatchID AS SourceMatchID,
    c.CompetitionCode AS Competition,
    s.Season,
    m.RoundName AS Round,
    m.MatchDate,
    m.KickoffDateTimeLocal,
    m.KickoffDateTimeUTC,
    CAST(CASE WHEN m.KickoffTimeKnownFlag = 1 THEN m.KickoffDateTimeLocal ELSE NULL END AS DATETIME2) AS KickoffDateTime,
    m.KickoffTimeKnownFlag,
    CASE
        WHEN m.KickoffTimeKnownFlag = 1 THEN 'Confirmed'
        WHEN m.KickoffTimeSource IS NULL OR m.KickoffTimeSource = 'Not supplied by source' THEN 'Not supplied by source'
        ELSE 'Time TBC'
    END AS KickoffTimeStatus,
    m.KickoffTimeSource,
    v.VenueName AS Venue,
    ht.TeamID AS HomeTeamID,
    ht.TeamName AS HomeTeam,
    at.TeamID AS AwayTeamID,
    at.TeamName AS AwayTeam,
    m.MatchStatus,
    pp.HomeWinProbability,
    pp.DrawProbability,
    pp.AwayWinProbability,
    pp.PredictedHomeMargin,
    CASE pp.PredictedWinner WHEN 'H' THEN ht.TeamName WHEN 'A' THEN at.TeamName ELSE 'Draw' END AS PredictedWinner,
    pp.ConfidenceLevel,
    pm.ModelName AS ProbabilityModelName,
    pm.ModelVersion AS ProbabilityModelVersion,
    mm.ModelName AS MarginModelName,
    mm.ModelVersion AS MarginModelVersion,
    pp.PredictionGeneratedAt,
    pp.FeatureCutoffDate,
    pp.DataQualityStatus,
    pp.HomeTeamSheetAvailable,
    pp.AwayTeamSheetAvailable,
    pp.HomePriorMatches,
    pp.AwayPriorMatches
FROM Gold_ProductionPredictions pp
JOIN Silver_Matches m ON m.MatchID = pp.MatchID
JOIN Silver_Seasons s ON s.SeasonID = m.SeasonID
JOIN Silver_Competitions c ON c.CompetitionID = s.CompetitionID
JOIN Silver_Teams ht ON ht.TeamID = m.HomeTeamID
JOIN Silver_Teams at ON at.TeamID = m.AwayTeamID
LEFT JOIN Silver_Venues v ON v.VenueID = m.VenueID
JOIN Gold_ModelVersions pm ON pm.ModelVersionID = pp.ProbabilityModelVersionID
JOIN Gold_ModelVersions mm ON mm.ModelVersionID = pp.MarginModelVersionID
WHERE m.MatchStatus = 'Scheduled'
  AND pp.DataQualityStatus <> 'Critical';
GO

CREATE OR ALTER VIEW vw_Gold_ProductionHistoricalPredictions AS
SELECT
    pe.PredictionEvaluationID,
    pe.MatchID,
    pe.EvaluationSeason AS Season,
    pe.RoundName AS Round,
    pe.HomeTeamID,
    ht.TeamName AS HomeTeam,
    pe.AwayTeamID,
    at.TeamName AS AwayTeam,
    pe.HomeScore,
    pe.AwayScore,
    pe.ActualOutcome,
    pe.PredictedOutcome,
    pe.CorrectWinner,
    pe.HomeProbabilityError,
    pe.MarginError AS PredictedMarginError,
    pe.AbsoluteMarginError,
    pe.HomeProbabilityBrier,
    pe.MulticlassBrier,
    pe.LogLoss,
    mv.ModelName,
    mv.ModelVersion,
    pe.EvaluationName,
    pe.FeatureCutoffDate,
    pe.EvaluatedAt
FROM Gold_PredictionEvaluations pe
JOIN Gold_ModelVersions mv ON mv.ModelVersionID = pe.ModelVersionID
JOIN Silver_Teams ht ON ht.TeamID = pe.HomeTeamID
JOIN Silver_Teams at ON at.TeamID = pe.AwayTeamID;
GO

CREATE OR ALTER VIEW vw_Gold_ProductionMatchExplanation AS
SELECT
    pp.ProductionPredictionID,
    pp.MatchID,
    ht.TeamName AS HomeTeam,
    at.TeamName AS AwayTeam,
    pp.HomePreMatchElo,
    pp.AwayPreMatchElo,
    pp.RawEloDifference,
    pp.HomeAdvantageAdjustment,
    pp.AdjustedEloDifference,
    pp.ProbabilityContribution,
    pp.HomeWinProbability,
    pp.DrawProbability,
    pp.AwayWinProbability,
    pp.PredictedHomeMargin,
    pp.ConfidenceLevel,
    pp.HomeRollingMargin AS ContextHomeRollingMargin,
    pp.AwayRollingMargin AS ContextAwayRollingMargin,
    pp.RestDaysDiff AS ContextRestDaysDiff,
    pp.HeadToHeadContext AS ContextHeadToHeadMargin,
    pp.HomeTeamSheetAvailable AS ContextHomeTeamSheetAvailable,
    pp.AwayTeamSheetAvailable AS ContextAwayTeamSheetAvailable,
    CAST(
        CONCAT(
            'Used by Elo model: home Elo ', COALESCE(CAST(pp.HomePreMatchElo AS VARCHAR(30)), 'unknown'),
            ', away Elo ', COALESCE(CAST(pp.AwayPreMatchElo AS VARCHAR(30)), 'unknown'),
            ', home advantage ', COALESCE(CAST(pp.HomeAdvantageAdjustment AS VARCHAR(30)), 'unknown'),
            ', adjusted Elo difference ', COALESCE(CAST(pp.AdjustedEloDifference AS VARCHAR(30)), 'unknown'),
            '. Context only: recent margins, rest days, head-to-head and team sheets are shown but were not used by EloOnlyBaseline.'
        ) AS VARCHAR(1000)
    ) AS ExplanationSummary
FROM Gold_ProductionPredictions pp
JOIN Silver_Matches m ON m.MatchID = pp.MatchID
JOIN Silver_Teams ht ON ht.TeamID = m.HomeTeamID
JOIN Silver_Teams at ON at.TeamID = m.AwayTeamID;
GO

CREATE OR ALTER VIEW vw_Gold_ProductionModelSummary AS
SELECT
    ds.ModelDeploymentStatusID,
    ds.TargetType,
    mv.ModelVersionID,
    mv.ModelName,
    mv.ModelVersion,
    ds.DeploymentStatus,
    ds.IsActive,
    ds.EffectiveFrom,
    ds.EffectiveTo,
    ds.SelectedAt,
    ds.SelectionReason,
    ds.EvaluationEvidence
FROM Gold_ModelDeploymentStatus ds
JOIN Gold_ModelVersions mv ON mv.ModelVersionID = ds.ModelVersionID;
GO

CREATE OR ALTER VIEW vw_Gold_ProductionCalibration AS
SELECT *
FROM vw_Gold_ModelCalibration;
GO

CREATE OR ALTER VIEW vw_Gold_ProductionDataQuality AS
SELECT
    ProductionDataQualityIssueID,
    MatchID,
    Season,
    SourceSystem,
    ProcessName,
    IssueCode,
    Severity,
    IssueMessage,
    IsBlocking,
    DetectedAt
FROM Gold_ProductionDataQualityIssues;
GO

CREATE OR ALTER VIEW vw_Gold_ProductionPipelineRuns AS
SELECT
    PipelineRunID,
    ProcessName,
    StartedAt,
    CompletedAt,
    Status,
    RecordsRead,
    RecordsWritten,
    WarningCount,
    ErrorCount,
    ModelVersion,
    ErrorSummary
FROM Gold_PipelineRuns;
GO

PRINT 'Gold model evaluation views ready.';
GO
