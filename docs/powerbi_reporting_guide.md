# BTA Rugby Analytics Power BI Reporting Guide

## Connection

Use Power BI Desktop's SQL Server connector.

- Server: `BIGTEDS`
- Database: `RugbyAnalytics`
- Data connectivity mode: Import for early development, DirectQuery only after performance testing
- Recommended schema objects: Gold production views only

Load these views:

- `vw_Gold_ProductionUpcomingPredictions`
- `vw_Gold_ProductionResults`
- `vw_Gold_PlayerTop10ByDiscipline`
- `vw_Gold_ProductionMatchExplanation`
- `vw_Gold_ProductionHistoricalPredictions`
- `vw_Gold_ProductionModelSummary`
- `vw_Gold_ProductionCalibration`
- `vw_Gold_ProductionDataQuality`
- `vw_Gold_ProductionPipelineRuns`
- `vw_Gold_MarginModelComparison`

Create relationships using durable IDs:

- `MatchID` between upcoming predictions and match explanations
- `ModelVersionID` where exposed in model summary and evaluation views
- Keep calibration and model comparison as separate fact-style tables; do not average already aggregated season metrics across seasons without weighting by match count.

Sort upcoming fixtures by:

1. `MatchDate`
2. `KickoffDateTimeLocal`
3. `MatchID`

## Essential Measures

```DAX
Upcoming Matches = COUNTROWS('vw_Gold_ProductionUpcomingPredictions')

Average Home Win Probability =
AVERAGE('vw_Gold_ProductionUpcomingPredictions'[HomeWinProbability])

High Confidence Matches =
CALCULATE(
    COUNTROWS('vw_Gold_ProductionUpcomingPredictions'),
    'vw_Gold_ProductionUpcomingPredictions'[ConfidenceLevel] IN {"High", "Very High"}
)

Critical Data Quality Issues =
CALCULATE(
    COUNTROWS('vw_Gold_ProductionDataQuality'),
    'vw_Gold_ProductionDataQuality'[Severity] = "Critical"
)

Warning Data Quality Issues =
CALCULATE(
    COUNTROWS('vw_Gold_ProductionDataQuality'),
    'vw_Gold_ProductionDataQuality'[Severity] = "Warning"
)

Production Results Winner Accuracy =
DIVIDE(
    SUMX(
        FILTER(
            'vw_Gold_ProductionResults',
            'vw_Gold_ProductionResults'[ProductionEvaluationEligibleFlag] = TRUE()
        ),
        IF('vw_Gold_ProductionResults'[CorrectWinner] = TRUE(), 1, 0)
    ),
    COUNTROWS(
        FILTER(
            'vw_Gold_ProductionResults',
            'vw_Gold_ProductionResults'[ProductionEvaluationEligibleFlag] = TRUE()
        )
    )
)

Production Results Margin MAE =
CALCULATE(
    AVERAGE('vw_Gold_ProductionResults'[AbsoluteMarginError]),
    'vw_Gold_ProductionResults'[ProductionEvaluationEligibleFlag] = TRUE()
)

Pipeline Errors =
SUM('vw_Gold_ProductionPipelineRuns'[ErrorCount])

Kickoff Display =
IF(
    'vw_Gold_ProductionUpcomingPredictions'[KickoffTimeKnownFlag] = TRUE(),
    FORMAT('vw_Gold_ProductionUpcomingPredictions'[KickoffDateTimeLocal], "ddd d mmm yyyy, h:mm AM/PM"),
    FORMAT('vw_Gold_ProductionUpcomingPredictions'[MatchDate], "ddd d mmm yyyy") & " - time TBC"
)
```

Formatting:

- Probability fields: Percentage, 1 decimal place
- Brier/log loss: Decimal, 3 decimals
- Margin fields: Decimal, 1 decimal
- Counts: Whole number

## Page 1: Upcoming Matches

Source view: `vw_Gold_ProductionUpcomingPredictions`

Recommended visuals:

- Table: `Kickoff Display`, `Round`, `HomeTeam`, `AwayTeam`, `PredictedWinner`, `HomeWinProbability`, `DrawProbability`, `AwayWinProbability`, `PredictedHomeMargin`, `ConfidenceLevel`, `DataQualityStatus`
- Cards: `Upcoming Matches`, `High Confidence Matches`, `Critical Data Quality Issues`
- Slicers: `Season`, `Round`, `ConfidenceLevel`, `DataQualityStatus`

Conditional formatting:

- `ConfidenceLevel`: Low gray, Moderate blue, High green, Very High dark green
- `DataQualityStatus`: OK green, Warning amber, Critical red

Tooltips:

- Probability model name/version
- Margin model name/version
- `KickoffTimeStatus`
- `KickoffDateTimeUTC`
- Feature cutoff date
- Prediction generated datetime

Display rule:

- Known time: `Sat 3 Oct 2026, 2:05 PM`
- Unknown time: `Sat 3 Oct 2026 - time TBC`
- Do not use `KickoffDateTime` for new visuals; it remains only as a nullable backward-compatible alias for known local kickoff datetimes.

Drill-through:

- Drill from `MatchID` to Match Preview and Explanation.

## Page 2: Match Preview and Explanation

Source view: `vw_Gold_ProductionMatchExplanation`

Recommended visuals:

- Header cards: `HomeTeam`, `AwayTeam`, `PredictedHomeMargin`, `ConfidenceLevel`
- Bar chart: `HomeWinProbability`, `DrawProbability`, `AwayWinProbability`
- Table: `HomePreMatchElo`, `AwayPreMatchElo`, `RawEloDifference`, `HomeAdvantageAdjustment`, `AdjustedEloDifference`, `ProbabilityContribution`
- Context table: `ContextHomeRollingMargin`, `ContextAwayRollingMargin`, `ContextRestDaysDiff`, `ContextHeadToHeadMargin`, team-sheet fields
- Text box/table field: `ExplanationSummary`

Important wording:

- Elo fields are model inputs.
- Rolling margin, rest days, head-to-head and team sheets are context only for `EloOnlyBaseline v0.2.0`.

## Page 3: Model Performance

Source views:

- `vw_Gold_MarginModelComparison`
- `vw_Gold_ProductionHistoricalPredictions`
- `vw_Gold_ProductionModelSummary`

Recommended visuals:

- Matrix: `ModelName`, `ModelVersion`, `EvaluationSeason`, `MatchesEvaluated`, `MarginMAE`, `MarginRMSE`, `MeanMarginError`
- Line chart: `EvaluationSeason` by `MarginMAE`
- Table: champion registry with `TargetType`, `ModelName`, `ModelVersion`, `DeploymentStatus`, `IsActive`, `SelectionReason`

Do not average seasonal MAE rows without weighting by `MatchesEvaluated`.

## Page 4: Calibration

Source view: `vw_Gold_ProductionCalibration`

Recommended visuals:

- Calibration line chart: `ConfidenceBand`, `MeanHomeWinProbability`, `ActualHomeWinRate`
- Bar chart: `CalibrationGap` by `ConfidenceBand`
- Table: `ModelName`, `ModelVersion`, `EvaluationSeason`, `PredictionCount`, `WinnerAccuracy`, `MeanAbsoluteMarginError`

Slicers:

- `ModelName`
- `ModelVersion`
- `EvaluationSeason`

## Page 5: Historical Prediction Explorer

Source view: `vw_Gold_ProductionResults`

Recommended visuals:

- Table: `Season`, `Round`, `HomeTeam`, `AwayTeam`, `HomeScore`, `AwayScore`, `ScoreStatus`, `ResultReadyFlag`, `PredictionAvailableFlag`, `ProductionEvaluationEligibleFlag`, `PredictedWinner`, `CorrectWinner`, `PredictedMarginError`, `AbsoluteMarginError`, `EvaluationStatus`
- Cards: `Production Results Winner Accuracy`, `Production Results Margin MAE`
- Scatter plot: `PredictedHomeMargin` versus `HomeMargin`

Slicers:

- `Season`
- `ModelName`
- `ModelVersion`
- `ScoreStatus`
- `EvaluationStatus`

Use `ResultReadyFlag = TRUE()` for tables and result display. Use `ProductionEvaluationEligibleFlag = TRUE()` for retained production-prediction accuracy and margin-error measures. Rows that are result-ready but lack retained production predictions can remain in retrospective/backtest model evaluation only when those pipelines independently generated valid out-of-sample predictions.

## Page 6: Player Top 10

Source view: `vw_Gold_PlayerTop10ByDiscipline`

Recommended visuals:

- Bar chart: `PlayerName` by `SeasonTotal`, filtered by `Discipline`.
- Table: `Season`, `Discipline`, `CalculatedRank`, `Team`, `PlayerName`, `SeasonTotal`, `Appearances`, `PerAppearance`.

Ranking rule:

- `CalculatedRank` is a dense rank within season, competition and discipline.
- Ties are retained, so a discipline can display more than ten rows.

## Page 7: Data Quality and Pipeline Status

Source views:

- `vw_Gold_ProductionDataQuality`
- `vw_Gold_ProductionPipelineRuns`

Recommended visuals:

- Cards: `Critical Data Quality Issues`, `Warning Data Quality Issues`, `Pipeline Errors`
- Table: `Severity`, `IssueCode`, `IssueMessage`, `MatchID`, `Season`, `DetectedAt`
- Pipeline table: `ProcessName`, `StartedAt`, `CompletedAt`, `Status`, `RecordsRead`, `RecordsWritten`, `WarningCount`, `ErrorCount`, `ModelVersion`

Conditional formatting:

- Critical: red
- Warning: amber
- Information: blue

Operational notes:

- Critical production data-quality issues are blocking and should keep affected matches out of `vw_Gold_ProductionUpcomingPredictions`.
- Missing future team sheets are warnings because teams are often unavailable before squads are published.
- Scheduled 0-0 placeholders are information unless they are incorrectly marked completed.
