-- ============================================================
-- Gold feature views for early rugby analytics
-- Run after platform_schema.sql and load_npc_to_silver.sql
-- ============================================================

USE RugbyAnalytics;
GO

CREATE OR ALTER VIEW vw_Gold_TeamMatchBase AS
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
    x.TeamID,
    x.TeamName,
    x.OpponentTeamID,
    x.OpponentTeamName,
    x.HomeAway,
    x.PointsFor,
    x.PointsAgainst,
    x.PointsFor - x.PointsAgainst AS Margin,
    CASE
        WHEN x.PointsFor > x.PointsAgainst THEN 1
        WHEN x.PointsFor = x.PointsAgainst THEN 0.5
        WHEN x.PointsFor < x.PointsAgainst THEN 0
        ELSE NULL
    END AS MatchResult,
    CASE WHEN x.PointsFor > x.PointsAgainst THEN 1 ELSE 0 END AS IsWin,
    CASE WHEN x.PointsFor = x.PointsAgainst THEN 1 ELSE 0 END AS IsDraw,
    CASE WHEN x.PointsFor < x.PointsAgainst THEN 1 ELSE 0 END AS IsLoss
FROM Silver_Matches m
JOIN Silver_Seasons s ON m.SeasonID = s.SeasonID
JOIN Silver_Competitions c ON s.CompetitionID = c.CompetitionID
JOIN Silver_Teams ht ON m.HomeTeamID = ht.TeamID
JOIN Silver_Teams at ON m.AwayTeamID = at.TeamID
CROSS APPLY (
    VALUES
        (m.HomeTeamID, ht.TeamName, m.AwayTeamID, at.TeamName, 'H', m.HomeScore, m.AwayScore),
        (m.AwayTeamID, at.TeamName, m.HomeTeamID, ht.TeamName, 'A', m.AwayScore, m.HomeScore)
) AS x(TeamID, TeamName, OpponentTeamID, OpponentTeamName, HomeAway, PointsFor, PointsAgainst)
WHERE m.MatchStatus = 'Completed';
GO

CREATE OR ALTER VIEW vw_Gold_TeamFormFeatures AS
SELECT
    b.*,
    COUNT(*) OVER (
        PARTITION BY b.CompetitionCode, b.Season, b.TeamID
        ORDER BY b.MatchDate, b.MatchID
        ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
    ) AS PriorMatches,
    AVG(CAST(b.MatchResult AS FLOAT)) OVER (
        PARTITION BY b.CompetitionCode, b.Season, b.TeamID
        ORDER BY b.MatchDate, b.MatchID
        ROWS BETWEEN 5 PRECEDING AND 1 PRECEDING
    ) AS Rolling5Result,
    AVG(CAST(b.Margin AS FLOAT)) OVER (
        PARTITION BY b.CompetitionCode, b.Season, b.TeamID
        ORDER BY b.MatchDate, b.MatchID
        ROWS BETWEEN 5 PRECEDING AND 1 PRECEDING
    ) AS Rolling5Margin,
    AVG(CAST(b.PointsFor AS FLOAT)) OVER (
        PARTITION BY b.CompetitionCode, b.Season, b.TeamID
        ORDER BY b.MatchDate, b.MatchID
        ROWS BETWEEN 5 PRECEDING AND 1 PRECEDING
    ) AS Rolling5PointsFor,
    AVG(CAST(b.PointsAgainst AS FLOAT)) OVER (
        PARTITION BY b.CompetitionCode, b.Season, b.TeamID
        ORDER BY b.MatchDate, b.MatchID
        ROWS BETWEEN 5 PRECEDING AND 1 PRECEDING
    ) AS Rolling5PointsAgainst,
    AVG(CAST(CASE WHEN b.HomeAway = 'H' THEN b.MatchResult END AS FLOAT)) OVER (
        PARTITION BY b.CompetitionCode, b.Season, b.TeamID
        ORDER BY b.MatchDate, b.MatchID
        ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
    ) AS PriorHomeResult,
    AVG(CAST(CASE WHEN b.HomeAway = 'A' THEN b.MatchResult END AS FLOAT)) OVER (
        PARTITION BY b.CompetitionCode, b.Season, b.TeamID
        ORDER BY b.MatchDate, b.MatchID
        ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
    ) AS PriorAwayResult
FROM vw_Gold_TeamMatchBase b;
GO

CREATE OR ALTER VIEW vw_Gold_MatchFeatureMatrix AS
SELECT
    hm.CompetitionCode,
    hm.Season,
    hm.MatchID,
    hm.MatchDate,
    hm.RoundName,
    hm.HomeTeamID,
    hm.HomeTeam,
    hm.AwayTeamID,
    hm.AwayTeam,
    hm.PointsFor AS HomeScore,
    hm.PointsAgainst AS AwayScore,
    hm.Margin AS HomeMargin,
    hm.MatchResult AS HomeResult,
    hf.PriorMatches AS HomePriorMatches,
    af.PriorMatches AS AwayPriorMatches,
    hf.Rolling5Result AS HomeRolling5Result,
    af.Rolling5Result AS AwayRolling5Result,
    hf.Rolling5Margin AS HomeRolling5Margin,
    af.Rolling5Margin AS AwayRolling5Margin,
    hf.Rolling5PointsFor AS HomeRolling5PointsFor,
    af.Rolling5PointsFor AS AwayRolling5PointsFor,
    hf.Rolling5PointsAgainst AS HomeRolling5PointsAgainst,
    af.Rolling5PointsAgainst AS AwayRolling5PointsAgainst,
    hf.Rolling5Margin - af.Rolling5Margin AS Rolling5MarginDiff,
    hf.Rolling5Result - af.Rolling5Result AS Rolling5ResultDiff
FROM vw_Gold_TeamMatchBase hm
JOIN vw_Gold_TeamFormFeatures hf
    ON hm.MatchID = hf.MatchID AND hm.TeamID = hf.TeamID
JOIN vw_Gold_TeamMatchBase am
    ON hm.MatchID = am.MatchID AND am.HomeAway = 'A'
JOIN vw_Gold_TeamFormFeatures af
    ON am.MatchID = af.MatchID AND am.TeamID = af.TeamID
WHERE hm.HomeAway = 'H';
GO

PRINT 'Gold feature views ready.';
GO
