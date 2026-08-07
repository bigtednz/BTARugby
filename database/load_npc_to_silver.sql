-- ============================================================
-- Load current NPC scraper tables into Silver platform tables
-- Run after platform_schema.sql and scraper.py
-- Supports every season present in NPC_Matches / NPC_PlayerStats.
-- ============================================================

USE RugbyAnalytics;
GO

IF OBJECT_ID('NPC_Matches', 'U') IS NOT NULL AND COL_LENGTH('NPC_Matches', 'KickoffDateTimeLocal') IS NULL
ALTER TABLE NPC_Matches ADD KickoffDateTimeLocal DATETIME2 NULL;
GO

IF OBJECT_ID('NPC_Matches', 'U') IS NOT NULL AND COL_LENGTH('NPC_Matches', 'KickoffDateTimeUTC') IS NULL
ALTER TABLE NPC_Matches ADD KickoffDateTimeUTC DATETIME2 NULL;
GO

IF OBJECT_ID('NPC_Matches', 'U') IS NOT NULL AND COL_LENGTH('NPC_Matches', 'KickoffTimeKnownFlag') IS NULL
ALTER TABLE NPC_Matches ADD KickoffTimeKnownFlag BIT NOT NULL DEFAULT 0;
GO

IF OBJECT_ID('NPC_Matches', 'U') IS NOT NULL AND COL_LENGTH('NPC_Matches', 'KickoffTimeSource') IS NULL
ALTER TABLE NPC_Matches ADD KickoffTimeSource VARCHAR(200) NULL;
GO

IF OBJECT_ID('NPC_Matches', 'U') IS NOT NULL AND COL_LENGTH('NPC_Matches', 'KickoffTimeCapturedAt') IS NULL
ALTER TABLE NPC_Matches ADD KickoffTimeCapturedAt DATETIME2 NULL;
GO

IF OBJECT_ID('NPC_Matches', 'U') IS NOT NULL AND COL_LENGTH('NPC_Matches', 'MatchStatus') IS NULL
ALTER TABLE NPC_Matches ADD MatchStatus VARCHAR(30) NULL;
GO

IF OBJECT_ID('NPC_Matches', 'U') IS NOT NULL AND COL_LENGTH('NPC_Matches', 'ScoreStatus') IS NULL
ALTER TABLE NPC_Matches ADD ScoreStatus VARCHAR(30) NULL;
GO

IF OBJECT_ID('NPC_Matches', 'U') IS NOT NULL AND COL_LENGTH('NPC_Matches', 'ResultReadyFlag') IS NULL
ALTER TABLE NPC_Matches ADD ResultReadyFlag BIT NOT NULL DEFAULT 0;
GO

IF OBJECT_ID('NPC_Matches', 'U') IS NOT NULL AND COL_LENGTH('NPC_Matches', 'ScoreSource') IS NULL
ALTER TABLE NPC_Matches ADD ScoreSource VARCHAR(200) NULL;
GO

IF OBJECT_ID('NPC_Matches', 'U') IS NOT NULL AND COL_LENGTH('NPC_Matches', 'ScoreCapturedAt') IS NULL
ALTER TABLE NPC_Matches ADD ScoreCapturedAt DATETIME2 NULL;
GO

IF OBJECT_ID('NPC_Matches', 'U') IS NOT NULL AND COL_LENGTH('NPC_Matches', 'ResultValidationStatus') IS NULL
ALTER TABLE NPC_Matches ADD ResultValidationStatus VARCHAR(50) NULL;
GO

IF COL_LENGTH('Silver_Matches', 'ScoreStatus') IS NULL
ALTER TABLE Silver_Matches ADD ScoreStatus VARCHAR(30) NULL;
GO

IF COL_LENGTH('Silver_Matches', 'ResultReadyFlag') IS NULL
ALTER TABLE Silver_Matches ADD ResultReadyFlag BIT NOT NULL DEFAULT 0;
GO

IF COL_LENGTH('Silver_Matches', 'ScoreSource') IS NULL
ALTER TABLE Silver_Matches ADD ScoreSource VARCHAR(200) NULL;
GO

IF COL_LENGTH('Silver_Matches', 'ScoreCapturedAt') IS NULL
ALTER TABLE Silver_Matches ADD ScoreCapturedAt DATETIME2 NULL;
GO

IF COL_LENGTH('Silver_Matches', 'ResultValidationStatus') IS NULL
ALTER TABLE Silver_Matches ADD ResultValidationStatus VARCHAR(50) NULL;
GO

DECLARE @CompetitionID INT;

MERGE Silver_Competitions AS t
USING (
    SELECT 'NPC' AS CompetitionCode, 'Hilux NPC' AS CompetitionName,
           'RugbyPass' AS SourceSystem, 'bunnings-npc' AS SourceURI
) AS s
ON t.CompetitionCode = s.CompetitionCode
WHEN MATCHED THEN UPDATE SET
    CompetitionName = s.CompetitionName,
    SourceSystem = s.SourceSystem,
    SourceURI = s.SourceURI
WHEN NOT MATCHED THEN INSERT (
    CompetitionCode, CompetitionName, SourceSystem, SourceURI
) VALUES (
    s.CompetitionCode, s.CompetitionName, s.SourceSystem, s.SourceURI
);

SELECT @CompetitionID = CompetitionID
FROM Silver_Competitions
WHERE CompetitionCode = 'NPC';

MERGE Silver_Seasons AS t
USING (
    SELECT DISTINCT
        @CompetitionID AS CompetitionID,
        Season,
        CONCAT(Season, ' Hilux NPC') AS SeasonName
    FROM NPC_Matches
    WHERE Season IS NOT NULL
) AS s
ON t.CompetitionID = s.CompetitionID AND t.Season = s.Season
WHEN MATCHED THEN UPDATE SET SeasonName = s.SeasonName
WHEN NOT MATCHED THEN INSERT (
    CompetitionID, Season, SeasonName
) VALUES (
    s.CompetitionID, s.Season, s.SeasonName
);

MERGE Silver_Teams AS t
USING (
    SELECT HomeTeam AS TeamName FROM NPC_Matches WHERE HomeTeam IS NOT NULL
    UNION
    SELECT AwayTeam AS TeamName FROM NPC_Matches WHERE AwayTeam IS NOT NULL
    UNION
    SELECT Team AS TeamName FROM NPC_PlayerStats WHERE Team IS NOT NULL
) AS s
ON t.TeamName = s.TeamName
WHEN NOT MATCHED THEN INSERT (TeamName, TeamSlug)
VALUES (s.TeamName, LOWER(REPLACE(REPLACE(REPLACE(s.TeamName, '''', ''), '.', ''), ' ', '-')));

MERGE Silver_Venues AS t
USING (
    SELECT DISTINCT Venue AS VenueName
    FROM NPC_Matches
    WHERE Venue IS NOT NULL
) AS s
ON t.VenueName = s.VenueName
WHEN NOT MATCHED THEN INSERT (VenueName)
VALUES (s.VenueName);

MERGE Silver_Matches AS t
USING (
    SELECT
        m.MatchID,
        ss.SeasonID,
        m.Round AS RoundName,
        m.MatchDate,
        m.KickoffDateTimeLocal,
        m.KickoffDateTimeUTC,
        m.KickoffTimeKnownFlag,
        m.KickoffTimeSource,
        m.KickoffTimeCapturedAt,
        v.VenueID,
        ht.TeamID AS HomeTeamID,
        at.TeamID AS AwayTeamID,
        m.HomeScore,
        m.AwayScore,
        CASE
            WHEN m.MatchStatus IN ('Scheduled', 'Live', 'Completed', 'Postponed', 'Cancelled') THEN m.MatchStatus
            WHEN m.ResultReadyFlag = 1 THEN 'Completed'
            WHEN m.MatchDate > CAST(GETDATE() AS DATE) THEN 'Scheduled'
            WHEN m.HomeScore IS NULL OR m.AwayScore IS NULL THEN 'Scheduled'
            WHEN NOT (m.HomeScore = 0 AND m.AwayScore = 0) THEN 'Completed'
            ELSE 'Completed'
        END AS MatchStatus,
        CASE
            WHEN m.ScoreStatus IN ('Pending', 'Confirmed', 'Unavailable') THEN m.ScoreStatus
            WHEN m.ResultReadyFlag = 1 THEN 'Confirmed'
            WHEN m.HomeScore IS NULL OR m.AwayScore IS NULL THEN 'Unavailable'
            WHEN m.MatchDate <= CAST(GETDATE() AS DATE) AND NOT (m.HomeScore = 0 AND m.AwayScore = 0) THEN 'Confirmed'
            ELSE 'Pending'
        END AS ScoreStatus,
        CAST(CASE
            WHEN m.ResultReadyFlag = 1 THEN 1
            WHEN m.ScoreStatus = 'Confirmed' AND m.HomeScore IS NOT NULL AND m.AwayScore IS NOT NULL THEN 1
            WHEN m.MatchDate <= CAST(GETDATE() AS DATE)
                 AND m.HomeScore IS NOT NULL
                 AND m.AwayScore IS NOT NULL
                 AND NOT (m.HomeScore = 0 AND m.AwayScore = 0) THEN 1
            ELSE 0
        END AS BIT) AS ResultReadyFlag,
        COALESCE(
            m.ScoreSource,
            CASE
                WHEN m.MatchDate <= CAST(GETDATE() AS DATE)
                     AND m.HomeScore IS NOT NULL
                     AND m.AwayScore IS NOT NULL
                     AND NOT (m.HomeScore = 0 AND m.AwayScore = 0)
                THEN 'Legacy NPC_Matches score'
                ELSE NULL
            END
        ) AS ScoreSource,
        COALESCE(
            m.ScoreCapturedAt,
            CASE
                WHEN m.MatchDate <= CAST(GETDATE() AS DATE)
                     AND m.HomeScore IS NOT NULL
                     AND m.AwayScore IS NOT NULL
                     AND NOT (m.HomeScore = 0 AND m.AwayScore = 0)
                THEN SYSUTCDATETIME()
                ELSE NULL
            END
        ) AS ScoreCapturedAt,
        COALESCE(
            m.ResultValidationStatus,
            CASE
                WHEN m.ResultReadyFlag = 1 THEN 'Valid'
                WHEN m.ScoreStatus = 'Confirmed' AND m.HomeScore IS NOT NULL AND m.AwayScore IS NOT NULL THEN 'Valid'
                WHEN m.MatchDate <= CAST(GETDATE() AS DATE)
                     AND m.HomeScore IS NOT NULL
                     AND m.AwayScore IS NOT NULL
                     AND NOT (m.HomeScore = 0 AND m.AwayScore = 0)
                THEN 'Valid legacy score'
                ELSE 'Awaiting source confirmation'
            END
        ) AS ResultValidationStatus,
        'RugbyPass' AS SourceSystem,
        CONCAT(
            'https://www.rugbypass.com/live/',
            LOWER(REPLACE(REPLACE(REPLACE(m.AwayTeam, '''', ''), '.', ''), ' ', '-')),
            '-vs-',
            LOWER(REPLACE(REPLACE(REPLACE(m.HomeTeam, '''', ''), '.', ''), ' ', '-')),
            '/'
        ) AS SourceURL
    FROM NPC_Matches m
    JOIN Silver_Seasons ss
        ON ss.CompetitionID = @CompetitionID
       AND ss.Season = m.Season
    JOIN Silver_Teams ht ON m.HomeTeam = ht.TeamName
    JOIN Silver_Teams at ON m.AwayTeam = at.TeamName
    LEFT JOIN Silver_Venues v ON m.Venue = v.VenueName
) AS s
ON t.MatchID = s.MatchID
WHEN MATCHED THEN UPDATE SET
    SeasonID = s.SeasonID,
    RoundName = s.RoundName,
    MatchDate = s.MatchDate,
    KickoffDateTimeLocal = s.KickoffDateTimeLocal,
    KickoffDateTimeUTC = s.KickoffDateTimeUTC,
    KickoffTimeKnownFlag = s.KickoffTimeKnownFlag,
    KickoffTimeSource = s.KickoffTimeSource,
    KickoffTimeCapturedAt = s.KickoffTimeCapturedAt,
    VenueID = s.VenueID,
    HomeTeamID = s.HomeTeamID,
    AwayTeamID = s.AwayTeamID,
    HomeScore = s.HomeScore,
    AwayScore = s.AwayScore,
    MatchStatus = s.MatchStatus,
    ScoreStatus = s.ScoreStatus,
    ResultReadyFlag = s.ResultReadyFlag,
    ScoreSource = s.ScoreSource,
    ScoreCapturedAt = s.ScoreCapturedAt,
    ResultValidationStatus = s.ResultValidationStatus,
    SourceSystem = s.SourceSystem,
    SourceURL = s.SourceURL,
    UpdatedAt = SYSUTCDATETIME()
WHEN NOT MATCHED THEN INSERT (
    MatchID, SeasonID, RoundName, MatchDate, KickoffDateTimeLocal, KickoffDateTimeUTC,
    KickoffTimeKnownFlag, KickoffTimeSource, KickoffTimeCapturedAt, VenueID, HomeTeamID, AwayTeamID,
    HomeScore, AwayScore, MatchStatus, ScoreStatus, ResultReadyFlag, ScoreSource, ScoreCapturedAt,
    ResultValidationStatus, SourceSystem, SourceURL
) VALUES (
    s.MatchID, s.SeasonID, s.RoundName, s.MatchDate, s.KickoffDateTimeLocal, s.KickoffDateTimeUTC,
    s.KickoffTimeKnownFlag, s.KickoffTimeSource, s.KickoffTimeCapturedAt, s.VenueID, s.HomeTeamID,
    s.AwayTeamID, s.HomeScore, s.AwayScore, s.MatchStatus, s.ScoreStatus, s.ResultReadyFlag,
    s.ScoreSource, s.ScoreCapturedAt, s.ResultValidationStatus, s.SourceSystem, s.SourceURL
);

MERGE Silver_Players AS t
USING (
    SELECT DISTINCT PlayerName
    FROM NPC_PlayerStats
    WHERE PlayerName IS NOT NULL
    UNION
    SELECT DISTINCT PlayerName
    FROM NPC_PlayerAppearances
    WHERE PlayerName IS NOT NULL
) AS s
ON t.PlayerName = s.PlayerName
WHEN NOT MATCHED THEN INSERT (PlayerName)
VALUES (s.PlayerName);

MERGE Silver_PlayerMatchStats AS t
USING (
    SELECT
        ps.MatchID,
        tm.TeamID,
        p.PlayerID,
        ps.StatCategory,
        ps.StatName,
        ps.Rank,
        ps.StatValue,
        ps.StatValueRaw,
        'RugbyPass' AS SourceSystem
    FROM NPC_PlayerStats ps
    JOIN Silver_Players p ON ps.PlayerName = p.PlayerName
    LEFT JOIN Silver_Teams tm ON ps.Team = tm.TeamName
) AS s
ON t.MatchID = s.MatchID
   AND t.PlayerID = s.PlayerID
   AND t.StatName = s.StatName
WHEN MATCHED THEN UPDATE SET
    TeamID = s.TeamID,
    StatCategory = s.StatCategory,
    Rank = s.Rank,
    StatValue = s.StatValue,
    StatValueRaw = s.StatValueRaw,
    SourceSystem = s.SourceSystem,
    UpdatedAt = SYSUTCDATETIME()
WHEN NOT MATCHED THEN INSERT (
    MatchID, TeamID, PlayerID, StatCategory, StatName, Rank,
    StatValue, StatValueRaw, SourceSystem
) VALUES (
    s.MatchID, s.TeamID, s.PlayerID, s.StatCategory, s.StatName, s.Rank,
    s.StatValue, s.StatValueRaw, s.SourceSystem
);

MERGE Silver_PlayerAppearances AS t
USING (
    SELECT
        pa.MatchID,
        tm.TeamID,
        p.PlayerID,
        pa.JerseyNumber,
        pa.IsStarter,
        pa.IsSubstitute,
        pa.SubOnMinute,
        pa.SubOffMinute,
        'RugbyPass' AS SourceSystem
    FROM NPC_PlayerAppearances pa
    JOIN Silver_Players p ON pa.PlayerName = p.PlayerName
    LEFT JOIN Silver_Teams tm ON pa.Team = tm.TeamName
) AS s
ON t.MatchID = s.MatchID
   AND t.TeamID = s.TeamID
   AND t.PlayerID = s.PlayerID
WHEN MATCHED THEN UPDATE SET
    JerseyNumber = s.JerseyNumber,
    IsStarter = s.IsStarter,
    IsSubstitute = s.IsSubstitute,
    SubOnMinute = s.SubOnMinute,
    SubOffMinute = s.SubOffMinute,
    SourceSystem = s.SourceSystem,
    UpdatedAt = SYSUTCDATETIME()
WHEN NOT MATCHED THEN INSERT (
    MatchID, TeamID, PlayerID, JerseyNumber, IsStarter, IsSubstitute,
    SubOnMinute, SubOffMinute, SourceSystem
) VALUES (
    s.MatchID, s.TeamID, s.PlayerID, s.JerseyNumber, s.IsStarter,
    s.IsSubstitute, s.SubOnMinute, s.SubOffMinute, s.SourceSystem
);
GO

PRINT 'NPC silver load complete.';
GO
