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
    MAX(CASE WHEN br.MetricName = 'mean_margin_error' THEN br.MetricValue END) AS MeanMarginError,
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

PRINT 'Gold model evaluation views ready.';
GO
