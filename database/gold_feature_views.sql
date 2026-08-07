-- ============================================================
-- Gold feature views for rugby analytics
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
        WHEN x.PointsFor > x.PointsAgainst THEN 1.0
        WHEN x.PointsFor = x.PointsAgainst THEN 0.5
        WHEN x.PointsFor < x.PointsAgainst THEN 0.0
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
WHERE m.MatchStatus = 'Completed'
  AND m.ResultReadyFlag = 1
  AND m.ScoreStatus = 'Confirmed'
  AND m.HomeScore IS NOT NULL
  AND m.AwayScore IS NOT NULL;
GO

CREATE OR ALTER VIEW vw_Gold_TeamFormFeatures AS
WITH ordered AS (
    SELECT
        b.*,
        LAG(b.MatchDate) OVER (
            PARTITION BY b.CompetitionCode, b.TeamID
            ORDER BY b.MatchDate, b.MatchID
        ) AS PriorMatchDate
    FROM vw_Gold_TeamMatchBase b
)
SELECT
    o.*,
    DATEDIFF(DAY, o.PriorMatchDate, o.MatchDate) AS RestDays,
    COUNT(*) OVER (
        PARTITION BY o.CompetitionCode, o.Season, o.TeamID
        ORDER BY o.MatchDate, o.MatchID
        ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
    ) AS PriorSeasonMatches,
    COUNT(*) OVER (
        PARTITION BY o.CompetitionCode, o.TeamID
        ORDER BY o.MatchDate, o.MatchID
        ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
    ) AS PriorAllMatches,
    AVG(CAST(o.MatchResult AS FLOAT)) OVER (
        PARTITION BY o.CompetitionCode, o.Season, o.TeamID
        ORDER BY o.MatchDate, o.MatchID
        ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
    ) AS SeasonToDateResult,
    AVG(CAST(o.Margin AS FLOAT)) OVER (
        PARTITION BY o.CompetitionCode, o.Season, o.TeamID
        ORDER BY o.MatchDate, o.MatchID
        ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
    ) AS SeasonToDateMargin,
    AVG(CAST(o.PointsFor AS FLOAT)) OVER (
        PARTITION BY o.CompetitionCode, o.Season, o.TeamID
        ORDER BY o.MatchDate, o.MatchID
        ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
    ) AS SeasonToDatePointsFor,
    AVG(CAST(o.PointsAgainst AS FLOAT)) OVER (
        PARTITION BY o.CompetitionCode, o.Season, o.TeamID
        ORDER BY o.MatchDate, o.MatchID
        ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
    ) AS SeasonToDatePointsAgainst,
    AVG(CAST(o.MatchResult AS FLOAT)) OVER (
        PARTITION BY o.CompetitionCode, o.TeamID
        ORDER BY o.MatchDate, o.MatchID
        ROWS BETWEEN 3 PRECEDING AND 1 PRECEDING
    ) AS Rolling3Result,
    AVG(CAST(o.Margin AS FLOAT)) OVER (
        PARTITION BY o.CompetitionCode, o.TeamID
        ORDER BY o.MatchDate, o.MatchID
        ROWS BETWEEN 3 PRECEDING AND 1 PRECEDING
    ) AS Rolling3Margin,
    AVG(CAST(o.PointsFor AS FLOAT)) OVER (
        PARTITION BY o.CompetitionCode, o.TeamID
        ORDER BY o.MatchDate, o.MatchID
        ROWS BETWEEN 3 PRECEDING AND 1 PRECEDING
    ) AS Rolling3PointsFor,
    AVG(CAST(o.PointsAgainst AS FLOAT)) OVER (
        PARTITION BY o.CompetitionCode, o.TeamID
        ORDER BY o.MatchDate, o.MatchID
        ROWS BETWEEN 3 PRECEDING AND 1 PRECEDING
    ) AS Rolling3PointsAgainst,
    AVG(CAST(o.MatchResult AS FLOAT)) OVER (
        PARTITION BY o.CompetitionCode, o.TeamID
        ORDER BY o.MatchDate, o.MatchID
        ROWS BETWEEN 5 PRECEDING AND 1 PRECEDING
    ) AS Rolling5Result,
    AVG(CAST(o.Margin AS FLOAT)) OVER (
        PARTITION BY o.CompetitionCode, o.TeamID
        ORDER BY o.MatchDate, o.MatchID
        ROWS BETWEEN 5 PRECEDING AND 1 PRECEDING
    ) AS Rolling5Margin,
    AVG(CAST(o.PointsFor AS FLOAT)) OVER (
        PARTITION BY o.CompetitionCode, o.TeamID
        ORDER BY o.MatchDate, o.MatchID
        ROWS BETWEEN 5 PRECEDING AND 1 PRECEDING
    ) AS Rolling5PointsFor,
    AVG(CAST(o.PointsAgainst AS FLOAT)) OVER (
        PARTITION BY o.CompetitionCode, o.TeamID
        ORDER BY o.MatchDate, o.MatchID
        ROWS BETWEEN 5 PRECEDING AND 1 PRECEDING
    ) AS Rolling5PointsAgainst,
    AVG(CAST(o.MatchResult AS FLOAT)) OVER (
        PARTITION BY o.CompetitionCode, o.TeamID, o.HomeAway
        ORDER BY o.MatchDate, o.MatchID
        ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
    ) AS PriorVenueResult,
    AVG(CAST(o.Margin AS FLOAT)) OVER (
        PARTITION BY o.CompetitionCode, o.TeamID, o.HomeAway
        ORDER BY o.MatchDate, o.MatchID
        ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
    ) AS PriorVenueMargin
FROM ordered o;
GO

CREATE OR ALTER VIEW vw_Gold_HeadToHeadFeatures AS
SELECT
    b.CompetitionCode,
    b.Season,
    b.MatchID,
    b.TeamID,
    b.OpponentTeamID,
    h2h.PriorHeadToHeadMatches,
    h2h.HeadToHeadLast5Result,
    h2h.HeadToHeadLast5Margin
FROM vw_Gold_TeamMatchBase b
OUTER APPLY (
    SELECT
        COUNT(*) AS PriorHeadToHeadMatches,
        AVG(CAST(prior.MatchResult AS FLOAT)) AS HeadToHeadLast5Result,
        AVG(CAST(prior.Margin AS FLOAT)) AS HeadToHeadLast5Margin
    FROM (
        SELECT TOP (5)
            b2.MatchResult,
            b2.Margin
        FROM vw_Gold_TeamMatchBase b2
        WHERE b2.CompetitionCode = b.CompetitionCode
          AND b2.TeamID = b.TeamID
          AND b2.OpponentTeamID = b.OpponentTeamID
          AND (
              b2.MatchDate < b.MatchDate
              OR (b2.MatchDate = b.MatchDate AND b2.MatchID < b.MatchID)
          )
        ORDER BY b2.MatchDate DESC, b2.MatchID DESC
    ) prior
) h2h;
GO

CREATE OR ALTER VIEW vw_Gold_TeamSheetFeatures AS
SELECT
    b.CompetitionCode,
    b.Season,
    b.MatchID,
    b.TeamID,
    COALESCE(curr.TotalPlayers, 0) AS ListedPlayers,
    COALESCE(curr.Starters, 0) AS ListedStarters,
    COALESCE(curr.Substitutes, 0) AS ListedSubstitutes,
    prior.PriorMatchID,
    overlap.ReturningPlayers,
    overlap.ReturningStarters
FROM vw_Gold_TeamMatchBase b
OUTER APPLY (
    SELECT TOP (1)
        b2.MatchID AS PriorMatchID
    FROM vw_Gold_TeamMatchBase b2
    WHERE b2.CompetitionCode = b.CompetitionCode
      AND b2.TeamID = b.TeamID
      AND (
          b2.MatchDate < b.MatchDate
          OR (b2.MatchDate = b.MatchDate AND b2.MatchID < b.MatchID)
      )
    ORDER BY b2.MatchDate DESC, b2.MatchID DESC
) prior
OUTER APPLY (
    SELECT
        COUNT(*) AS TotalPlayers,
        SUM(CASE WHEN spa.IsStarter = 1 THEN 1 ELSE 0 END) AS Starters,
        SUM(CASE WHEN spa.IsSubstitute = 1 THEN 1 ELSE 0 END) AS Substitutes
    FROM Silver_PlayerAppearances spa
    WHERE spa.MatchID = b.MatchID
      AND spa.TeamID = b.TeamID
) curr
OUTER APPLY (
    SELECT
        COUNT(*) AS ReturningPlayers,
        SUM(CASE WHEN curr_players.IsStarter = 1 AND prior_players.IsStarter = 1 THEN 1 ELSE 0 END) AS ReturningStarters
    FROM Silver_PlayerAppearances curr_players
    JOIN Silver_PlayerAppearances prior_players
        ON prior_players.MatchID = prior.PriorMatchID
       AND prior_players.TeamID = b.TeamID
       AND prior_players.PlayerID = curr_players.PlayerID
    WHERE curr_players.MatchID = b.MatchID
      AND curr_players.TeamID = b.TeamID
) overlap;
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
    hf.PriorSeasonMatches AS HomePriorSeasonMatches,
    af.PriorSeasonMatches AS AwayPriorSeasonMatches,
    hf.PriorAllMatches AS HomePriorAllMatches,
    af.PriorAllMatches AS AwayPriorAllMatches,
    hf.RestDays AS HomeRestDays,
    af.RestDays AS AwayRestDays,
    hf.RestDays - af.RestDays AS RestDaysDiff,
    hf.SeasonToDateResult AS HomeSeasonToDateResult,
    af.SeasonToDateResult AS AwaySeasonToDateResult,
    hf.SeasonToDateResult - af.SeasonToDateResult AS SeasonToDateResultDiff,
    hf.SeasonToDateMargin AS HomeSeasonToDateMargin,
    af.SeasonToDateMargin AS AwaySeasonToDateMargin,
    hf.SeasonToDateMargin - af.SeasonToDateMargin AS SeasonToDateMarginDiff,
    hf.SeasonToDatePointsFor AS HomeSeasonToDatePointsFor,
    af.SeasonToDatePointsFor AS AwaySeasonToDatePointsFor,
    hf.SeasonToDatePointsAgainst AS HomeSeasonToDatePointsAgainst,
    af.SeasonToDatePointsAgainst AS AwaySeasonToDatePointsAgainst,
    hf.Rolling3Result AS HomeRolling3Result,
    af.Rolling3Result AS AwayRolling3Result,
    hf.Rolling3Result - af.Rolling3Result AS Rolling3ResultDiff,
    hf.Rolling3Margin AS HomeRolling3Margin,
    af.Rolling3Margin AS AwayRolling3Margin,
    hf.Rolling3Margin - af.Rolling3Margin AS Rolling3MarginDiff,
    hf.Rolling3PointsFor AS HomeRolling3PointsFor,
    af.Rolling3PointsFor AS AwayRolling3PointsFor,
    hf.Rolling3PointsAgainst AS HomeRolling3PointsAgainst,
    af.Rolling3PointsAgainst AS AwayRolling3PointsAgainst,
    hf.Rolling5Result AS HomeRolling5Result,
    af.Rolling5Result AS AwayRolling5Result,
    hf.Rolling5Result - af.Rolling5Result AS Rolling5ResultDiff,
    hf.Rolling5Margin AS HomeRolling5Margin,
    af.Rolling5Margin AS AwayRolling5Margin,
    hf.Rolling5Margin - af.Rolling5Margin AS Rolling5MarginDiff,
    hf.Rolling5PointsFor AS HomeRolling5PointsFor,
    af.Rolling5PointsFor AS AwayRolling5PointsFor,
    hf.Rolling5PointsAgainst AS HomeRolling5PointsAgainst,
    af.Rolling5PointsAgainst AS AwayRolling5PointsAgainst,
    hf.PriorVenueResult AS HomePriorHomeResult,
    af.PriorVenueResult AS AwayPriorAwayResult,
    hf.PriorVenueMargin AS HomePriorHomeMargin,
    af.PriorVenueMargin AS AwayPriorAwayMargin,
    hh.PriorHeadToHeadMatches,
    hh.HeadToHeadLast5Result AS HomeHeadToHeadLast5Result,
    hh.HeadToHeadLast5Margin AS HomeHeadToHeadLast5Margin,
    hts.ListedPlayers AS HomeListedPlayers,
    ats.ListedPlayers AS AwayListedPlayers,
    hts.ListedPlayers - ats.ListedPlayers AS ListedPlayersDiff,
    hts.ListedStarters AS HomeListedStarters,
    ats.ListedStarters AS AwayListedStarters,
    hts.ReturningPlayers AS HomeReturningPlayers,
    ats.ReturningPlayers AS AwayReturningPlayers,
    hts.ReturningPlayers - ats.ReturningPlayers AS ReturningPlayersDiff,
    hts.ReturningStarters AS HomeReturningStarters,
    ats.ReturningStarters AS AwayReturningStarters,
    hts.ReturningStarters - ats.ReturningStarters AS ReturningStartersDiff
FROM vw_Gold_TeamMatchBase hm
JOIN vw_Gold_TeamFormFeatures hf
    ON hm.MatchID = hf.MatchID AND hm.TeamID = hf.TeamID
JOIN vw_Gold_TeamMatchBase am
    ON hm.MatchID = am.MatchID AND am.HomeAway = 'A'
JOIN vw_Gold_TeamFormFeatures af
    ON am.MatchID = af.MatchID AND am.TeamID = af.TeamID
LEFT JOIN vw_Gold_HeadToHeadFeatures hh
    ON hm.MatchID = hh.MatchID AND hm.TeamID = hh.TeamID
LEFT JOIN vw_Gold_TeamSheetFeatures hts
    ON hm.MatchID = hts.MatchID AND hm.TeamID = hts.TeamID
LEFT JOIN vw_Gold_TeamSheetFeatures ats
    ON am.MatchID = ats.MatchID AND am.TeamID = ats.TeamID
WHERE hm.HomeAway = 'H';
GO

PRINT 'Gold feature views ready.';
GO
