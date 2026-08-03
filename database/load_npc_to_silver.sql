-- ============================================================
-- Load current NPC scraper tables into Silver platform tables
-- Run after platform_schema.sql and scraper.py
-- Supports every season present in NPC_Matches / NPC_PlayerStats.
-- ============================================================

USE RugbyAnalytics;
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
        v.VenueID,
        ht.TeamID AS HomeTeamID,
        at.TeamID AS AwayTeamID,
        m.HomeScore,
        m.AwayScore,
        CASE
            WHEN m.HomeScore IS NULL OR m.AwayScore IS NULL THEN 'Scheduled'
            ELSE 'Completed'
        END AS MatchStatus,
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
    VenueID = s.VenueID,
    HomeTeamID = s.HomeTeamID,
    AwayTeamID = s.AwayTeamID,
    HomeScore = s.HomeScore,
    AwayScore = s.AwayScore,
    MatchStatus = s.MatchStatus,
    SourceSystem = s.SourceSystem,
    SourceURL = s.SourceURL,
    UpdatedAt = SYSUTCDATETIME()
WHEN NOT MATCHED THEN INSERT (
    MatchID, SeasonID, RoundName, MatchDate, VenueID, HomeTeamID, AwayTeamID,
    HomeScore, AwayScore, MatchStatus, SourceSystem, SourceURL
) VALUES (
    s.MatchID, s.SeasonID, s.RoundName, s.MatchDate, s.VenueID, s.HomeTeamID,
    s.AwayTeamID, s.HomeScore, s.AwayScore, s.MatchStatus, s.SourceSystem, s.SourceURL
);

MERGE Silver_Players AS t
USING (
    SELECT DISTINCT PlayerName
    FROM NPC_PlayerStats
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
GO

PRINT 'NPC silver load complete.';
GO
