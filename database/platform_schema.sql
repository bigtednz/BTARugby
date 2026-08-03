-- ============================================================
-- BTA Rugby Analytics Platform Schema
-- Bronze / Silver / Gold foundation tables
-- ============================================================

IF NOT EXISTS (SELECT name FROM sys.databases WHERE name = 'RugbyAnalytics')
BEGIN
    CREATE DATABASE RugbyAnalytics;
END
GO

USE RugbyAnalytics;
GO

SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO

-- ============================================================
-- Bronze: source captures
-- ============================================================

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Bronze_SourceSnapshots')
CREATE TABLE Bronze_SourceSnapshots (
    SourceSnapshotID BIGINT IDENTITY PRIMARY KEY,
    SourceSystem     VARCHAR(50) NOT NULL,
    CompetitionCode  VARCHAR(20) NULL,
    Season           INT NULL,
    SourceEntity     VARCHAR(50) NOT NULL,
    SourceEntityID   VARCHAR(100) NULL,
    SourceURL        VARCHAR(500) NOT NULL,
    ContentType      VARCHAR(100) NULL,
    ContentHash      CHAR(64) NULL,
    ContentText      NVARCHAR(MAX) NULL,
    CapturedAt       DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME()
);
GO

IF NOT EXISTS (
    SELECT * FROM sys.indexes
    WHERE name = 'IX_Bronze_SourceSnapshots_Entity'
      AND object_id = OBJECT_ID('Bronze_SourceSnapshots')
)
CREATE INDEX IX_Bronze_SourceSnapshots_Entity
ON Bronze_SourceSnapshots (SourceSystem, CompetitionCode, Season, SourceEntity, SourceEntityID);
GO

-- ============================================================
-- Silver: normalised rugby model
-- ============================================================

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Silver_Competitions')
CREATE TABLE Silver_Competitions (
    CompetitionID   INT IDENTITY PRIMARY KEY,
    CompetitionCode VARCHAR(20) NOT NULL UNIQUE,
    CompetitionName VARCHAR(100) NOT NULL,
    SourceSystem    VARCHAR(50) NULL,
    SourceURI       VARCHAR(100) NULL,
    CreatedAt       DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME()
);
GO

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Silver_Seasons')
CREATE TABLE Silver_Seasons (
    SeasonID      INT IDENTITY PRIMARY KEY,
    CompetitionID INT NOT NULL REFERENCES Silver_Competitions(CompetitionID),
    Season        INT NOT NULL,
    SeasonName    VARCHAR(50) NULL,
    CreatedAt     DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
    CONSTRAINT UQ_Silver_Seasons UNIQUE (CompetitionID, Season)
);
GO

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Silver_Teams')
CREATE TABLE Silver_Teams (
    TeamID      INT IDENTITY PRIMARY KEY,
    TeamName    VARCHAR(100) NOT NULL,
    TeamSlug    VARCHAR(120) NULL,
    Country     VARCHAR(50) NULL,
    CreatedAt   DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
    CONSTRAINT UQ_Silver_Teams_Name UNIQUE (TeamName)
);
GO

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Silver_Players')
CREATE TABLE Silver_Players (
    PlayerID    INT IDENTITY PRIMARY KEY,
    PlayerName  VARCHAR(150) NOT NULL,
    CreatedAt   DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
    CONSTRAINT UQ_Silver_Players_Name UNIQUE (PlayerName)
);
GO

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Silver_Venues')
CREATE TABLE Silver_Venues (
    VenueID    INT IDENTITY PRIMARY KEY,
    VenueName  VARCHAR(150) NOT NULL,
    City       VARCHAR(100) NULL,
    Country    VARCHAR(50) NULL,
    CreatedAt  DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
    CONSTRAINT UQ_Silver_Venues_Name UNIQUE (VenueName)
);
GO

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Silver_Matches')
CREATE TABLE Silver_Matches (
    MatchID       INT PRIMARY KEY,
    SeasonID      INT NOT NULL REFERENCES Silver_Seasons(SeasonID),
    RoundName     VARCHAR(50) NULL,
    MatchDate     DATE NULL,
    VenueID       INT NULL REFERENCES Silver_Venues(VenueID),
    HomeTeamID    INT NOT NULL REFERENCES Silver_Teams(TeamID),
    AwayTeamID    INT NOT NULL REFERENCES Silver_Teams(TeamID),
    HomeScore     INT NULL,
    AwayScore     INT NULL,
    MatchStatus   VARCHAR(30) NULL,
    SourceSystem  VARCHAR(50) NULL,
    SourceURL     VARCHAR(500) NULL,
    UpdatedAt     DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME()
);
GO

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Silver_TeamMatchStats')
CREATE TABLE Silver_TeamMatchStats (
    TeamMatchStatID BIGINT IDENTITY PRIMARY KEY,
    MatchID         INT NOT NULL REFERENCES Silver_Matches(MatchID),
    TeamID          INT NOT NULL REFERENCES Silver_Teams(TeamID),
    OpponentTeamID  INT NOT NULL REFERENCES Silver_Teams(TeamID),
    HomeAway        CHAR(1) NOT NULL,
    StatName        VARCHAR(100) NOT NULL,
    StatValue       DECIMAL(12,4) NULL,
    StatValueRaw    VARCHAR(50) NULL,
    SourceSystem    VARCHAR(50) NULL,
    UpdatedAt       DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
    CONSTRAINT UQ_Silver_TeamMatchStats UNIQUE (MatchID, TeamID, StatName)
);
GO

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Silver_PlayerMatchStats')
CREATE TABLE Silver_PlayerMatchStats (
    PlayerMatchStatID BIGINT IDENTITY PRIMARY KEY,
    MatchID           INT NOT NULL REFERENCES Silver_Matches(MatchID),
    TeamID            INT NULL REFERENCES Silver_Teams(TeamID),
    PlayerID          INT NOT NULL REFERENCES Silver_Players(PlayerID),
    StatCategory      VARCHAR(50) NULL,
    StatName          VARCHAR(100) NOT NULL,
    Rank              INT NULL,
    StatValue         DECIMAL(12,4) NULL,
    StatValueRaw      VARCHAR(50) NULL,
    SourceSystem      VARCHAR(50) NULL,
    UpdatedAt         DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
    CONSTRAINT UQ_Silver_PlayerMatchStats UNIQUE (MatchID, PlayerID, StatName)
);
GO

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Silver_PlayerAppearances')
CREATE TABLE Silver_PlayerAppearances (
    PlayerAppearanceID BIGINT IDENTITY PRIMARY KEY,
    MatchID            INT NOT NULL REFERENCES Silver_Matches(MatchID),
    TeamID             INT NULL REFERENCES Silver_Teams(TeamID),
    PlayerID           INT NOT NULL REFERENCES Silver_Players(PlayerID),
    JerseyNumber       INT NULL,
    IsStarter          BIT NOT NULL,
    IsSubstitute       BIT NOT NULL,
    SubOnMinute        INT NULL,
    SubOffMinute       INT NULL,
    SourceSystem       VARCHAR(50) NULL,
    UpdatedAt          DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
    CONSTRAINT UQ_Silver_PlayerAppearances UNIQUE (MatchID, TeamID, PlayerID)
);
GO

-- ============================================================
-- Gold: features, predictions, and backtests
-- ============================================================

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Gold_TeamMatchFeatures')
CREATE TABLE Gold_TeamMatchFeatures (
    TeamMatchFeatureID BIGINT IDENTITY PRIMARY KEY,
    MatchID            INT NOT NULL REFERENCES Silver_Matches(MatchID),
    TeamID             INT NOT NULL REFERENCES Silver_Teams(TeamID),
    FeatureSetVersion  VARCHAR(50) NOT NULL,
    FeatureName        VARCHAR(100) NOT NULL,
    FeatureValue       DECIMAL(18,6) NULL,
    CalculatedAt       DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
    CONSTRAINT UQ_Gold_TeamMatchFeatures UNIQUE (MatchID, TeamID, FeatureSetVersion, FeatureName)
);
GO

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Gold_ModelVersions')
CREATE TABLE Gold_ModelVersions (
    ModelVersionID INT IDENTITY PRIMARY KEY,
    ModelName      VARCHAR(100) NOT NULL,
    ModelVersion   VARCHAR(50) NOT NULL,
    TargetName     VARCHAR(100) NOT NULL,
    TrainingStart  DATE NULL,
    TrainingEnd    DATE NULL,
    Notes          VARCHAR(1000) NULL,
    CreatedAt      DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
    CONSTRAINT UQ_Gold_ModelVersions UNIQUE (ModelName, ModelVersion, TargetName)
);
GO

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Gold_MatchPredictions')
CREATE TABLE Gold_MatchPredictions (
    PredictionID       BIGINT IDENTITY PRIMARY KEY,
    MatchID            INT NOT NULL REFERENCES Silver_Matches(MatchID),
    ModelVersionID     INT NOT NULL REFERENCES Gold_ModelVersions(ModelVersionID),
    HomeWinProbability DECIMAL(9,6) NULL,
    AwayWinProbability DECIMAL(9,6) NULL,
    DrawProbability    DECIMAL(9,6) NULL,
    PredictedHomeScore DECIMAL(9,3) NULL,
    PredictedAwayScore DECIMAL(9,3) NULL,
    PredictedMargin    DECIMAL(9,3) NULL,
    PredictionMadeAt   DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
    CONSTRAINT UQ_Gold_MatchPredictions UNIQUE (MatchID, ModelVersionID)
);
GO

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Gold_BacktestResults')
CREATE TABLE Gold_BacktestResults (
    BacktestResultID BIGINT IDENTITY PRIMARY KEY,
    ModelVersionID   INT NOT NULL REFERENCES Gold_ModelVersions(ModelVersionID),
    EvaluationStart  DATE NULL,
    EvaluationEnd    DATE NULL,
    MetricName       VARCHAR(100) NOT NULL,
    MetricValue      DECIMAL(18,6) NULL,
    BaselineName     VARCHAR(100) NULL,
    CreatedAt        DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME()
);
GO

IF COL_LENGTH('Gold_BacktestResults', 'EvaluationName') IS NULL
ALTER TABLE Gold_BacktestResults ADD EvaluationName VARCHAR(100) NULL;
GO

IF COL_LENGTH('Gold_BacktestResults', 'EvaluationSeason') IS NULL
ALTER TABLE Gold_BacktestResults ADD EvaluationSeason INT NULL;
GO

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Gold_PredictionEvaluations')
CREATE TABLE Gold_PredictionEvaluations (
    PredictionEvaluationID BIGINT IDENTITY PRIMARY KEY,
    PredictionID           BIGINT NOT NULL REFERENCES Gold_MatchPredictions(PredictionID),
    ModelVersionID         INT NOT NULL REFERENCES Gold_ModelVersions(ModelVersionID),
    MatchID                INT NOT NULL REFERENCES Silver_Matches(MatchID),
    EvaluationName         VARCHAR(100) NOT NULL,
    EvaluationSeason       INT NOT NULL,
    FeatureCutoffDate      DATE NULL,
    HomeTeamID             INT NOT NULL REFERENCES Silver_Teams(TeamID),
    AwayTeamID             INT NOT NULL REFERENCES Silver_Teams(TeamID),
    RoundName              VARCHAR(50) NULL,
    RoundBand              VARCHAR(20) NULL,
    HomeScore              INT NOT NULL,
    AwayScore              INT NOT NULL,
    ActualHomeResult       DECIMAL(9,6) NOT NULL,
    ActualOutcome          CHAR(1) NOT NULL,
    PredictedOutcome       CHAR(1) NOT NULL,
    CorrectWinner          BIT NULL,
    MarginError            DECIMAL(12,6) NULL,
    AbsoluteMarginError    DECIMAL(12,6) NULL,
    SquaredMarginError     DECIMAL(18,6) NULL,
    HomeProbabilityError   DECIMAL(12,6) NULL,
    HomeProbabilityBrier   DECIMAL(18,6) NULL,
    MulticlassBrier        DECIMAL(18,6) NULL,
    LogLoss                DECIMAL(18,6) NULL,
    EvaluatedAt            DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
    CONSTRAINT UQ_Gold_PredictionEvaluations UNIQUE (PredictionID, EvaluationName)
);
GO

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Gold_ModelCalibration')
CREATE TABLE Gold_ModelCalibration (
    ModelCalibrationID       BIGINT IDENTITY PRIMARY KEY,
    ModelVersionID           INT NOT NULL REFERENCES Gold_ModelVersions(ModelVersionID),
    EvaluationName           VARCHAR(100) NOT NULL,
    EvaluationSeason         INT NOT NULL,
    ConfidenceBand           VARCHAR(20) NOT NULL,
    BandStart                DECIMAL(4,2) NOT NULL,
    BandEnd                  DECIMAL(4,2) NOT NULL,
    PredictionCount          INT NOT NULL,
    MeanHomeWinProbability   DECIMAL(9,6) NULL,
    ActualHomeWinRate        DECIMAL(9,6) NULL,
    CalibrationGap           DECIMAL(9,6) NULL,
    WinnerAccuracy           DECIMAL(9,6) NULL,
    MeanAbsoluteMarginError  DECIMAL(12,6) NULL,
    CreatedAt                DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
    CONSTRAINT UQ_Gold_ModelCalibration UNIQUE (
        ModelVersionID, EvaluationName, EvaluationSeason, ConfidenceBand
    )
);
GO

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Gold_RidgeModelParameters')
CREATE TABLE Gold_RidgeModelParameters (
    RidgeModelParameterID BIGINT IDENTITY PRIMARY KEY,
    ModelVersionID        INT NOT NULL REFERENCES Gold_ModelVersions(ModelVersionID),
    EvaluationName        VARCHAR(100) NOT NULL,
    EvaluationSeason      INT NOT NULL,
    FeatureName           VARCHAR(100) NOT NULL,
    Coefficient           DECIMAL(18,9) NOT NULL,
    FeatureMean           DECIMAL(18,9) NULL,
    FeatureStdDev         DECIMAL(18,9) NULL,
    ImputationValue       DECIMAL(18,9) NULL,
    RidgeAlpha            DECIMAL(18,9) NOT NULL,
    IsMissingnessIndicator BIT NOT NULL DEFAULT 0,
    CreatedAt             DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
    CONSTRAINT UQ_Gold_RidgeModelParameters UNIQUE (
        ModelVersionID, EvaluationName, EvaluationSeason, FeatureName
    )
);
GO

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Gold_PredictionFeatureContributions')
CREATE TABLE Gold_PredictionFeatureContributions (
    PredictionFeatureContributionID BIGINT IDENTITY PRIMARY KEY,
    PredictionID                    BIGINT NOT NULL REFERENCES Gold_MatchPredictions(PredictionID),
    ModelVersionID                  INT NOT NULL REFERENCES Gold_ModelVersions(ModelVersionID),
    MatchID                         INT NOT NULL REFERENCES Silver_Matches(MatchID),
    EvaluationName                  VARCHAR(100) NOT NULL,
    EvaluationSeason                INT NOT NULL,
    FeatureName                     VARCHAR(100) NOT NULL,
    FeatureValue                    DECIMAL(18,9) NULL,
    StandardizedFeatureValue        DECIMAL(18,9) NULL,
    Coefficient                     DECIMAL(18,9) NOT NULL,
    Contribution                    DECIMAL(18,9) NOT NULL,
    ContributionRank                INT NULL,
    CreatedAt                       DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
    CONSTRAINT UQ_Gold_PredictionFeatureContributions UNIQUE (PredictionID, FeatureName)
);
GO

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Gold_MarginModelChampionStatus')
CREATE TABLE Gold_MarginModelChampionStatus (
    ChampionStatusID          BIGINT IDENTITY PRIMARY KEY,
    ModelVersionID            INT NOT NULL REFERENCES Gold_ModelVersions(ModelVersionID),
    EvaluationName            VARCHAR(100) NOT NULL,
    EvaluationStartSeason     INT NOT NULL,
    EvaluationEndSeason       INT NOT NULL,
    Status                    VARCHAR(20) NOT NULL,
    BenchmarkModelName        VARCHAR(100) NOT NULL,
    BenchmarkModelVersion     VARCHAR(50) NOT NULL,
    WeightedMarginMAE         DECIMAL(18,6) NULL,
    BenchmarkWeightedMarginMAE DECIMAL(18,6) NULL,
    CompleteSeasonsBeaten     INT NOT NULL,
    OverallBias               DECIMAL(18,6) NULL,
    LargeErrorRate            DECIMAL(18,6) NULL,
    Reason                    VARCHAR(1000) NOT NULL,
    CreatedAt                 DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
    CONSTRAINT CK_Gold_MarginModelChampionStatus_Status CHECK (Status IN ('Champion', 'Challenger', 'Rejected')),
    CONSTRAINT UQ_Gold_MarginModelChampionStatus UNIQUE (
        ModelVersionID, EvaluationName, EvaluationStartSeason, EvaluationEndSeason
    )
);
GO

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Gold_CombinedForwardPredictions')
CREATE TABLE Gold_CombinedForwardPredictions (
    CombinedForwardPredictionID BIGINT IDENTITY PRIMARY KEY,
    MatchID                     INT NOT NULL REFERENCES Silver_Matches(MatchID),
    ProbabilityModelName        VARCHAR(100) NOT NULL,
    ProbabilityModelVersion     VARCHAR(50) NOT NULL,
    MarginModelName             VARCHAR(100) NOT NULL,
    MarginModelVersion          VARCHAR(50) NOT NULL,
    HomeWinProbability          DECIMAL(9,6) NULL,
    DrawProbability             DECIMAL(9,6) NULL,
    AwayWinProbability          DECIMAL(9,6) NULL,
    PredictedMargin             DECIMAL(9,3) NULL,
    ScorePredictionMethod       VARCHAR(100) NULL,
    CreatedAt                   DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
    CONSTRAINT UQ_Gold_CombinedForwardPredictions UNIQUE (
        MatchID, ProbabilityModelName, ProbabilityModelVersion, MarginModelName, MarginModelVersion
    )
);
GO

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Gold_ModelDeploymentStatus')
CREATE TABLE Gold_ModelDeploymentStatus (
    ModelDeploymentStatusID BIGINT IDENTITY PRIMARY KEY,
    TargetType              VARCHAR(50) NOT NULL,
    ModelVersionID          INT NOT NULL REFERENCES Gold_ModelVersions(ModelVersionID),
    DeploymentStatus        VARCHAR(20) NOT NULL,
    EffectiveFrom           DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
    EffectiveTo             DATETIME2 NULL,
    SelectionReason         VARCHAR(1000) NOT NULL,
    EvaluationEvidence      VARCHAR(1000) NULL,
    IsActive                BIT NOT NULL DEFAULT 0,
    SelectedAt              DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
    CreatedAt               DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
    CONSTRAINT CK_Gold_ModelDeploymentStatus_Status CHECK (
        DeploymentStatus IN ('Champion', 'Challenger', 'Rejected', 'Retired')
    )
);
GO

IF NOT EXISTS (
    SELECT * FROM sys.indexes
    WHERE name = 'UX_Gold_ModelDeploymentStatus_ActiveTarget'
      AND object_id = OBJECT_ID('Gold_ModelDeploymentStatus')
)
CREATE UNIQUE INDEX UX_Gold_ModelDeploymentStatus_ActiveTarget
ON Gold_ModelDeploymentStatus(TargetType)
WHERE IsActive = 1;
GO

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Gold_ProductionPredictions')
CREATE TABLE Gold_ProductionPredictions (
    ProductionPredictionID   BIGINT IDENTITY PRIMARY KEY,
    MatchID                  INT NOT NULL REFERENCES Silver_Matches(MatchID),
    ProbabilityModelVersionID INT NOT NULL REFERENCES Gold_ModelVersions(ModelVersionID),
    MarginModelVersionID     INT NOT NULL REFERENCES Gold_ModelVersions(ModelVersionID),
    PredictionGeneratedAt    DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
    FeatureCutoffDate        DATE NULL,
    HomeWinProbability       DECIMAL(9,6) NOT NULL,
    DrawProbability          DECIMAL(9,6) NOT NULL,
    AwayWinProbability       DECIMAL(9,6) NOT NULL,
    PredictedHomeMargin      DECIMAL(9,3) NOT NULL,
    PredictedWinner          CHAR(1) NOT NULL,
    ConfidenceLevel          VARCHAR(20) NOT NULL,
    HomePreMatchElo          DECIMAL(12,3) NULL,
    AwayPreMatchElo          DECIMAL(12,3) NULL,
    RawEloDifference         DECIMAL(12,3) NULL,
    HomeAdvantageAdjustment  DECIMAL(12,3) NULL,
    AdjustedEloDifference    DECIMAL(12,3) NULL,
    ProbabilityContribution  DECIMAL(9,6) NULL,
    HomePriorMatches         INT NOT NULL DEFAULT 0,
    AwayPriorMatches         INT NOT NULL DEFAULT 0,
    HomeRollingMargin        DECIMAL(12,3) NULL,
    AwayRollingMargin        DECIMAL(12,3) NULL,
    RestDaysDiff             INT NULL,
    HeadToHeadContext        DECIMAL(12,3) NULL,
    HomeTeamSheetAvailable   BIT NOT NULL DEFAULT 0,
    AwayTeamSheetAvailable   BIT NOT NULL DEFAULT 0,
    DataQualityStatus        VARCHAR(20) NOT NULL DEFAULT 'Pending',
    CreatedAt                DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
    CONSTRAINT UQ_Gold_ProductionPredictions UNIQUE (
        MatchID, ProbabilityModelVersionID, MarginModelVersionID
    )
);
GO

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Gold_ProductionDataQualityIssues')
CREATE TABLE Gold_ProductionDataQualityIssues (
    ProductionDataQualityIssueID BIGINT IDENTITY PRIMARY KEY,
    MatchID                      INT NULL REFERENCES Silver_Matches(MatchID),
    Season                       INT NULL,
    SourceSystem                 VARCHAR(50) NULL,
    ProcessName                  VARCHAR(100) NOT NULL,
    IssueCode                    VARCHAR(100) NOT NULL,
    Severity                     VARCHAR(20) NOT NULL,
    IssueMessage                 VARCHAR(1000) NOT NULL,
    DetectedAt                   DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
    IsBlocking                   BIT NOT NULL DEFAULT 0,
    CONSTRAINT CK_Gold_ProductionDataQualityIssues_Severity CHECK (
        Severity IN ('Critical', 'Warning', 'Information')
    )
);
GO

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'Gold_PipelineRuns')
CREATE TABLE Gold_PipelineRuns (
    PipelineRunID      BIGINT IDENTITY PRIMARY KEY,
    ProcessName        VARCHAR(100) NOT NULL,
    StartedAt          DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
    CompletedAt        DATETIME2 NULL,
    Status             VARCHAR(20) NOT NULL,
    RecordsRead        INT NOT NULL DEFAULT 0,
    RecordsWritten     INT NOT NULL DEFAULT 0,
    WarningCount       INT NOT NULL DEFAULT 0,
    ErrorCount         INT NOT NULL DEFAULT 0,
    ModelVersion       VARCHAR(150) NULL,
    ErrorSummary       VARCHAR(1000) NULL,
    CreatedAt          DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME()
);
GO

-- ============================================================
-- Silver load helpers from current NPC scraper tables
-- ============================================================

CREATE OR ALTER VIEW vw_SilverMatchResults AS
SELECT
    c.CompetitionCode,
    s.Season,
    m.MatchID,
    m.RoundName,
    m.MatchDate,
    ht.TeamName AS HomeTeam,
    at.TeamName AS AwayTeam,
    m.HomeScore,
    m.AwayScore,
    m.HomeScore - m.AwayScore AS HomeMargin,
    CASE
        WHEN m.HomeScore > m.AwayScore THEN ht.TeamName
        WHEN m.AwayScore > m.HomeScore THEN at.TeamName
        WHEN m.HomeScore = m.AwayScore THEN 'Draw'
        ELSE NULL
    END AS Winner
FROM Silver_Matches m
JOIN Silver_Seasons s ON m.SeasonID = s.SeasonID
JOIN Silver_Competitions c ON s.CompetitionID = c.CompetitionID
JOIN Silver_Teams ht ON m.HomeTeamID = ht.TeamID
JOIN Silver_Teams at ON m.AwayTeamID = at.TeamID;
GO

PRINT 'Platform schema ready.';
GO
