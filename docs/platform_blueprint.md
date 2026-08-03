# BTA Rugby Analytics Platform Blueprint

## Objective

Build a rugby analytics platform that can ingest historic rugby data, standardise it into clean analytical tables, detect performance trends, and generate explainable match predictions.

The platform should prioritise traceability. Every prediction should be explainable from the source data, feature values, and model version that produced it.

## Data Layers

### Bronze: Source Capture

Bronze stores source data with minimal transformation.

Purpose:
- Preserve raw evidence from RugbyPass and future sources.
- Allow reprocessing when parsers improve.
- Track source URL, scrape time, competition, season, and source system.

Examples:
- raw fixture page HTML
- raw match page HTML
- raw embedded JSON payloads
- raw API responses

### Silver: Normalised Rugby Model

Silver stores clean rugby entities and event-level facts.

Purpose:
- De-duplicate teams, players, venues, matches, and stat names.
- Provide stable IDs for analytics and reporting.
- Separate team totals from player leaderboards.

Core entities:
- competitions
- seasons
- teams
- players
- venues
- matches
- team match stats
- player match stats

### Gold: Analytical Features

Gold stores model-ready features and outputs.

Purpose:
- Convert historical records into comparable performance signals.
- Store model predictions and backtest results.
- Keep modelling logic separate from raw scraped data.

Feature examples:
- rolling form over 3, 5, and 10 matches
- home and away splits
- points for and against trend
- opponent-adjusted margin
- attacking efficiency
- defensive pressure
- discipline risk
- player leaderboard strength
- rest days
- venue effect
- Elo-style team rating

Implemented Gold views:
- `vw_Gold_TeamMatchBase`
- `vw_Gold_TeamFormFeatures`
- `vw_Gold_HeadToHeadFeatures`
- `vw_Gold_TeamSheetFeatures`
- `vw_Gold_MatchFeatureMatrix`

## Prediction Roadmap

### Phase 1: Baselines

Build transparent baseline models before advanced ML.

Models:
- home team win-rate baseline
- season points differential baseline
- Elo rating model implemented as `EloRollingMarginBaseline v0.1.0`
- rolling margin model implemented as part of `EloRollingMarginBaseline v0.1.0`
- Baseline Evaluation v0.2 benchmark set:
  - `HomeTeamBaseline v0.2.0`
  - `EloOnlyBaseline v0.2.0`
  - `RollingMarginOnlyBaseline v0.2.0`
  - `SeasonToDateMarginBaseline v0.2.0`
  - `EloRollingMarginBaseline v0.2.0`

Targets:
- win probability
- predicted margin
- predicted total points

### Phase 2: Feature Models

Use engineered features from Gold tables.

Models:
- logistic regression for win probability
- `RidgeMarginModel v0.3.0` for margin, using fixed-alpha ridge regression and stored feature contributions
- Poisson-style score model
- gradient boosting after enough history is collected

`RidgeMarginModel v0.3.0` keeps `EloOnlyBaseline v0.2.0` as the probability component. It was evaluated as a margin challenger across the same walk-forward seasons and was rejected for champion promotion because complete-season weighted MAE was worse than Elo-only.

### Phase 3: Backtesting and Calibration

Every model version must be evaluated against historical rounds.

Metrics:
- accuracy
- Brier score
- log loss
- margin mean absolute error
- calibration by confidence band
- return over baseline

Current baseline metrics are stored in `Gold_BacktestResults` after running:

```powershell
python analytics/baseline_evaluation.py --model all --evaluation-season all
```

Walk-forward evaluation is season based:
- train with seasons before 2023, evaluate 2023
- train with seasons through 2023, evaluate 2024
- train with seasons through 2024, evaluate 2025
- train with seasons through 2025, evaluate completed 2026 matches

Draw treatment:
- probability metrics include draws
- multiclass Brier and log loss use home/draw/away probabilities
- winner accuracy excludes drawn matches
- margin metrics include draws

Current reporting views:
- `vw_Gold_ModelPerformanceComparison`
- `vw_Gold_ModelCalibration`
- `vw_Gold_ModelPerformanceByTeam`
- `vw_Gold_ModelPerformanceByRoundBand`
- `vw_Gold_RidgeModelParameters`
- `vw_Gold_RidgePredictionExplanation`
- `vw_Gold_RidgeStrongestDrivers`
- `vw_Gold_MarginModelComparison`
- `vw_Gold_MarginChampionStatus`
- `vw_Gold_CombinedUpcomingPredictions`
- `vw_Gold_ProductionUpcomingPredictions`
- `vw_Gold_ProductionHistoricalPredictions`
- `vw_Gold_ProductionMatchExplanation`
- `vw_Gold_ProductionModelSummary`
- `vw_Gold_ProductionCalibration`
- `vw_Gold_ProductionDataQuality`
- `vw_Gold_ProductionPipelineRuns`

### Phase 4: Production Predictions and Reporting

`Production Predictions and Reporting Layer v0.4.0` makes the validated Elo-only model operational for scheduled NPC fixtures.

Production champion registry:
- `EloOnlyBaseline v0.2.0` is active for win probability.
- `EloOnlyBaseline v0.2.0` is active as the margin incumbent.
- `RidgeMarginModel v0.3.0` is retained as rejected for margin traceability.

Production prediction principles:
- resolve champion models from SQL by model name/version, not hard-coded IDs
- generate predictions only for scheduled NPC fixtures
- store generation datetime, feature cutoff date, match date, local kickoff datetime and UTC kickoff datetime
- expose confidence bands based on largest win probability
- keep provisional score estimates out of the main production view
- block critical data-quality failures from production upcoming outputs
- show form, rest-day, head-to-head and team-sheet fields as context only for Elo predictions
- preserve unknown kickoff times as NULL rather than displaying midnight

### Kickoff Time Handling

`Kickoff Date and Time Correction v0.4.1` keeps `MatchDate` as the durable date column and stores kickoff time in separate nullable fields.

Source evidence:
- RugbyPass `current-game-days` JSON includes `dateId`, `time`, `timeSmall` and `epoch`.
- Example `950775`: `time=19:10pm NZST`, converted to `2026-08-06 19:10` local and `2026-08-06 07:10` UTC.
- Example `950837`: `time=17:05pm NZDT`, converted to `2026-10-04 17:05` local and `2026-10-04 04:05` UTC.

Timezone rule:
- Use `Pacific/Auckland` for conversion.
- If a source does not supply time, keep kickoff datetime fields NULL and report `Not supplied by source` or `Time TBC`.

## Platform Surfaces

### Analyst Database

SQL Server remains the system of record during early development.

Priority outputs:
- team trend views
- player trend views
- match preview feature table
- prediction history table

### Reporting

Initial reporting can use Power BI.

Core pages:
- competition overview
- team profile
- match preview
- player impact
- model performance

### Application Layer

Once the database and models stabilise, add a web app.

Candidate screens:
- upcoming match predictions
- team comparison
- player leaderboard trends
- model explanation panel
- data quality monitor

## Engineering Principles

- Keep raw, cleaned, feature, and prediction data separate.
- Never overwrite raw source captures.
- Store model version with every prediction.
- Prefer simple models until backtests prove complexity is useful.
- Treat missing data as a first-class data quality signal.
- Avoid mixing team totals and player statistics in the same table.

## Near-Term Build Order

1. Add bronze source snapshot tables.
2. Add silver normalised rugby tables.
3. Load current NPC tables into silver tables.
4. Add gold feature views for team form and points trends.
5. Implement Elo and rolling margin baselines.
6. Store predictions and backtest results.
7. Build Power BI-ready views.
8. Improve margin features before testing another margin champion.
9. Build the first Power BI report from `docs/powerbi_reporting_guide.md`.
