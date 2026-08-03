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

Targets:
- win probability
- predicted margin
- predicted total points

### Phase 2: Feature Models

Use engineered features from Gold tables.

Models:
- logistic regression for win probability
- linear or ridge regression for margin
- Poisson-style score model
- gradient boosting after enough history is collected

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
python analytics/run_baseline_predictions.py
```

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
