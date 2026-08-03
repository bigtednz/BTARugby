-- ============================================================
-- Reset BTA Rugby Analytics data
-- Deletes data from Bronze, Silver, Gold, and current NPC scraper tables.
-- Keeps schemas, tables, views, and stored scripts intact.
-- ============================================================

USE RugbyAnalytics;
GO

SET XACT_ABORT ON;
GO

BEGIN TRANSACTION;

-- Gold
DELETE FROM Gold_CombinedForwardPredictions;
DELETE FROM Gold_MarginModelChampionStatus;
DELETE FROM Gold_PredictionFeatureContributions;
DELETE FROM Gold_RidgeModelParameters;
DELETE FROM Gold_ModelCalibration;
DELETE FROM Gold_PredictionEvaluations;
DELETE FROM Gold_BacktestResults;
DELETE FROM Gold_MatchPredictions;
DELETE FROM Gold_TeamMatchFeatures;
DELETE FROM Gold_ModelVersions;

-- Silver
DELETE FROM Silver_PlayerMatchStats;
DELETE FROM Silver_PlayerAppearances;
DELETE FROM Silver_TeamMatchStats;
DELETE FROM Silver_Matches;
DELETE FROM Silver_Players;
DELETE FROM Silver_Venues;
DELETE FROM Silver_Teams;
DELETE FROM Silver_Seasons;
DELETE FROM Silver_Competitions;

-- Current scraper tables
DELETE FROM NPC_PlayerStats;
DELETE FROM NPC_PlayerAppearances;
DELETE FROM NPC_TeamStats;
DELETE FROM NPC_Matches;

-- Bronze
DELETE FROM Bronze_SourceSnapshots;

COMMIT TRANSACTION;
GO

-- Reset identities where present.
DBCC CHECKIDENT ('Gold_BacktestResults', RESEED, 0);
DBCC CHECKIDENT ('Gold_CombinedForwardPredictions', RESEED, 0);
DBCC CHECKIDENT ('Gold_MarginModelChampionStatus', RESEED, 0);
DBCC CHECKIDENT ('Gold_ModelCalibration', RESEED, 0);
DBCC CHECKIDENT ('Gold_PredictionEvaluations', RESEED, 0);
DBCC CHECKIDENT ('Gold_PredictionFeatureContributions', RESEED, 0);
DBCC CHECKIDENT ('Gold_MatchPredictions', RESEED, 0);
DBCC CHECKIDENT ('Gold_RidgeModelParameters', RESEED, 0);
DBCC CHECKIDENT ('Gold_TeamMatchFeatures', RESEED, 0);
DBCC CHECKIDENT ('Gold_ModelVersions', RESEED, 0);
DBCC CHECKIDENT ('Silver_PlayerMatchStats', RESEED, 0);
DBCC CHECKIDENT ('Silver_PlayerAppearances', RESEED, 0);
DBCC CHECKIDENT ('Silver_TeamMatchStats', RESEED, 0);
DBCC CHECKIDENT ('Silver_Players', RESEED, 0);
DBCC CHECKIDENT ('Silver_Venues', RESEED, 0);
DBCC CHECKIDENT ('Silver_Teams', RESEED, 0);
DBCC CHECKIDENT ('Silver_Seasons', RESEED, 0);
DBCC CHECKIDENT ('Silver_Competitions', RESEED, 0);
DBCC CHECKIDENT ('NPC_PlayerStats', RESEED, 0);
DBCC CHECKIDENT ('NPC_PlayerAppearances', RESEED, 0);
DBCC CHECKIDENT ('NPC_TeamStats', RESEED, 0);
DBCC CHECKIDENT ('Bronze_SourceSnapshots', RESEED, 0);
GO

PRINT 'Data reset complete.';
GO
