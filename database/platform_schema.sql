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
