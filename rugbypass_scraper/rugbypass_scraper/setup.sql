-- ============================================================
-- RugbyAnalytics Database Setup
-- Run this in SSMS before running scraper.py
-- ============================================================

-- 1. Create database
IF NOT EXISTS (SELECT name FROM sys.databases WHERE name = 'RugbyAnalytics')
BEGIN
    CREATE DATABASE RugbyAnalytics;
    PRINT 'Created database RugbyAnalytics';
END
GO

USE RugbyAnalytics;
GO

-- 2. Tables are created automatically by scraper.py.
--    After running the scraper, verify the NPC tables exist:
--    SELECT * FROM sys.tables WHERE name LIKE 'NPC%';

-- 3. Useful ad-hoc queries after scraping

-- All Canterbury matches with result
SELECT
    m.Round,
    m.MatchDate,
    m.HomeTeam,
    m.AwayTeam,
    m.HomeScore,
    m.AwayScore,
    ts.Result,
    ts.Margin,
    ts.KickToPassRatio,
    ts.TurnoversLost,
    ts.PossessionPct,
    ts.TerritoryPct,
    ts.Entries22m,
    ts.Conversion22m,
    ts.PctGameInLead
FROM vw_TeamPerformance ts
JOIN NPC_Matches m ON ts.MatchID = m.MatchID
WHERE ts.Team = 'Canterbury'
  AND ts.Season = 2026
ORDER BY m.MatchDate;

-- Season averages by team
SELECT
    Team,
    COUNT(*) AS Matches,
    AVG(CAST(PointsFor AS FLOAT)) AS AvgPointsFor,
    AVG(CAST(PointsAgainst AS FLOAT)) AS AvgPointsAgainst,
    AVG(CAST(Margin AS FLOAT)) AS AvgMargin,
    AVG(KickToPassRatio) AS AvgKTPRatio,
    AVG(PossessionPct) AS AvgPossession,
    AVG(TerritoryPct) AS AvgTerritory,
    AVG(CAST(TurnoversLost AS FLOAT)) AS AvgTurnoversLost,
    AVG(Conversion22m) AS Avg22mConversion
FROM vw_TeamPerformance
WHERE Season = 2026
GROUP BY Team
ORDER BY AVG(CAST(Margin AS FLOAT)) DESC;

-- Win vs loss stat comparison for Canterbury
SELECT
    Result,
    COUNT(*) AS Matches,
    AVG(KickToPassRatio) AS AvgKTPRatio,
    AVG(PossessionPct) AS AvgPossession,
    AVG(TerritoryPct) AS AvgTerritory,
    AVG(CAST(TurnoversLost AS FLOAT)) AS AvgTurnoversLost,
    AVG(CAST(TurnoversWon AS FLOAT)) AS AvgTurnoversWon,
    AVG(Conversion22m) AS Avg22mConversion,
    AVG(PctGameInLead) AS AvgPctInLead,
    AVG(TackleCompletionPct) AS AvgTackleCompletion
FROM vw_TeamPerformance
WHERE Team = 'Canterbury' AND Season = 2026
GROUP BY Result;
GO

PRINT 'Setup complete. Run scraper.py next.';
