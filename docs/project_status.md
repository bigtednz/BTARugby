# BTA Rugby Analytics Project Status

Last updated: 2026-08-03

## Current Objective

Build a rugby analytics platform that ingests historical rugby data, normalises it into Bronze/Silver/Gold layers, detects trends, and produces explainable match predictions.

The current competition focus is Hilux NPC.

## Completed Work

### Repository and Project Setup

- Created the BTA Rugby Analytics repository structure.
- Connected the local project to GitHub at `bigtednz/BTARugby`.
- Added platform documentation in `README.md` and `docs/platform_blueprint.md`.
- Added SQL Server database scripts under `database/`.

### Competition Conversion

- Converted the RugbyPass scraper from its original target to Hilux NPC.
- Set RugbyPass tournament URI to `bunnings-npc`.
- Added NPC-specific table naming:
  - `NPC_Matches`
  - `NPC_TeamStats`
  - `NPC_PlayerStats`
  - `NPC_PlayerAppearances`

### Bronze Layer

- Added `Bronze_SourceSnapshots`.
- Captures raw RugbyPass HTML/JSON snapshots for:
  - fixtures
  - team stats pages
  - player stats pages
  - team sheets
- Uses content hashes so raw source evidence can be audited and reprocessed later.

### Silver Layer

- Added normalised tables for:
  - competitions
  - seasons
  - teams
  - players
  - venues
  - matches
  - team match stats
  - player leaderboard stats
  - player appearances
- Added `database/load_npc_to_silver.sql` to load NPC scraper tables into Silver.
- Fixed future fixture handling so future `0-0` fixtures are marked `Scheduled`, not `Completed`.

### Player Data

- Identified that RugbyPass match stats pages expose player leaderboard rows, not full squads.
- Kept leaderboard stats in `NPC_PlayerStats`.
- Added `NPC_PlayerAppearances` for full team-sheet appearances.
- Added `Silver_PlayerAppearances`.
- Confirmed Richie Mo'unga appears correctly for Canterbury:
  - match `950772`
  - jersey `22`
  - substitute
  - sub on at `51`

### Historical Data Load

- Added historical fixture loading through RugbyPass archive POST endpoint.
- Added `NPC_TARGET_SEASONS` so a specific season can be loaded repeatably.
- Confirmed RugbyPass archive currently exposes NPC data from 2021 onward.
- Confirmed the RugbyPass 2020 archive request returns no NPC games.
- Loaded available NPC seasons:
  - 2021
  - 2022
  - 2023
  - 2024
  - 2025
  - 2026 current fixtures/results

### Gold Feature Layer

- Added `database/gold_feature_views.sql`.
- Implemented:
  - `vw_Gold_TeamMatchBase`
  - `vw_Gold_TeamFormFeatures`
  - `vw_Gold_HeadToHeadFeatures`
  - `vw_Gold_TeamSheetFeatures`
  - `vw_Gold_MatchFeatureMatrix`
- Current feature matrix includes:
  - rolling 3 and rolling 5 form
  - season-to-date result, margin, points for, points against
  - rest days
  - home/away venue form
  - recent head-to-head form
  - listed players, starters, substitutes
  - returning players and returning starters

### Baseline Prediction Model

- Added `analytics/run_baseline_predictions.py`.
- Implemented `EloRollingMarginBaseline v0.1.0`.
- Writes to:
  - `Gold_ModelVersions`
  - `Gold_MatchPredictions`
  - `Gold_BacktestResults`
- Model combines:
  - Elo rating difference
  - fixed home advantage
  - rolling five-match margin difference
- Produces:
  - home win probability
  - away win probability
  - draw probability
  - predicted home score
  - predicted away score
  - predicted margin

### Baseline Evaluation v0.2

- Added `analytics/baseline_evaluation.py`.
- Added offline tests in `tests/test_baseline_evaluation.py`.
- Added model evaluation SQL views in `database/model_evaluation_views.sql`.
- Added Gold evaluation tables:
  - `Gold_PredictionEvaluations`
  - `Gold_ModelCalibration`
- Extended `Gold_BacktestResults` with:
  - `EvaluationName`
  - `EvaluationSeason`
- Implemented benchmark models:
  - `HomeTeamBaseline v0.2.0`
  - `EloOnlyBaseline v0.2.0`
  - `RollingMarginOnlyBaseline v0.2.0`
  - `SeasonToDateMarginBaseline v0.2.0`
  - `EloRollingMarginBaseline v0.2.0`
- Added walk-forward evaluation by season:
  - seasons before 2023 evaluate 2023
  - seasons through 2023 evaluate 2024
  - seasons through 2024 evaluate 2025
  - seasons through 2025 evaluate completed 2026 matches
- Added confidence-band calibration in 0.10 home-win-probability bands.
- Added data-quality checks for duplicate predictions, invalid probabilities, scheduled matches in evaluation, feature cutoff leakage, missing scores, suspicious completed `0-0` rows, and small samples.

### Dedicated Margin Model v0.3

- Added `analytics/ridge_margin_model.py`.
- Registered `RidgeMarginModel v0.3.0`.
- Retained `EloOnlyBaseline v0.2.0` as the probability component for home/draw/away probabilities.
- Implemented fixed-alpha ridge regression for home margin using point-in-time features:
  - pre-match Elo difference generated from model state before match update
  - rolling 3 and rolling 5 margin difference
  - season-to-date margin difference
  - rolling points-for and points-against differences
  - home/away form
  - rest-day difference
  - head-to-head margin
  - returning-player and returning-starter continuity with missingness indicators
- Added training-window-only standardisation and imputation.
- Added explicit missingness indicators for sparse feature inputs.
- Added stored ridge parameters and per-prediction feature contributions.
- Added champion/challenger/rejected status storage.
- Added offline unit tests in `tests/test_ridge_margin_model.py`.
- Added Gold tables:
  - `Gold_RidgeModelParameters`
  - `Gold_PredictionFeatureContributions`
  - `Gold_MarginModelChampionStatus`
  - `Gold_CombinedForwardPredictions`
- Added reporting views:
  - `vw_Gold_RidgeModelParameters`
  - `vw_Gold_RidgePredictionExplanation`
  - `vw_Gold_RidgeStrongestDrivers`
  - `vw_Gold_MarginModelComparison`
  - `vw_Gold_MarginChampionStatus`
  - `vw_Gold_CombinedUpcomingPredictions`

Champion decision: `Rejected`. Across complete seasons 2023-2025, ridge weighted margin MAE was 13.56 versus 12.81 for `EloOnlyBaseline v0.2.0`, and ridge beat Elo-only in zero of the three complete seasons.

### Data Reset and Repeatability

- Added `database/reset_data.sql` to clear Bronze/Silver/Gold and NPC scraper tables for clean reloads.
- Scraper and SQL loads are mostly idempotent via `MERGE` and uniqueness constraints.

## Current Database State

### NPC Matches

| Season | Matches |
| --- | ---: |
| 2021 | 76 |
| 2022 | 77 |
| 2023 | 77 |
| 2024 | 77 |
| 2025 | 77 |
| 2026 | 70 |

### Silver

| Item | Count |
| --- | ---: |
| Completed matches | 391 |
| Scheduled matches | 63 |
| Silver players | 929 |
| Silver player appearances | 6,348 |

### Gold

| Item | Count |
| --- | ---: |
| Match feature rows | 391 |
| Predictions | 1,959 |
| Detailed v0.2 evaluation rows | 1,190 |
| v0.2 calibration rows | 126 |
| Ridge v0.3 predictions | 301 |
| Ridge v0.3 detailed evaluation rows | 238 |
| Ridge v0.3 parameter rows | 88 |
| Ridge v0.3 contribution rows | 6,622 |

### Baseline Backtest

`EloRollingMarginBaseline v0.1.0`

| Metric | Value |
| --- | ---: |
| Matches evaluated | 391 |
| Non-draw matches evaluated | 365 |
| Winner accuracy | 69.04% |
| Margin MAE | 12.23 |
| Margin RMSE | 16.42 |
| Home probability Brier | 0.207 |

### Baseline Evaluation v0.2 Best Current Benchmark

Across 2023-2025 completed seasons, `EloOnlyBaseline v0.2.0` is currently the strongest simple benchmark by winner accuracy and probability metrics.

| Season | Winner Accuracy | Margin MAE |
| --- | ---: | ---: |
| 2023 | 71.05% | 11.31 |
| 2024 | 70.13% | 12.97 |
| 2025 | 69.74% | 14.15 |
| 2026 completed | 85.71% | 13.75 |

### Dedicated Margin Model v0.3 Result

`RidgeMarginModel v0.3.0` was evaluated as a margin challenger while retaining Elo-only probabilities.

| Season | Matches Evaluated | Margin MAE | Margin RMSE | Median Abs Error | Bias | Within 15 | Large Error Rate |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 2023 | 77 | 12.32 | 15.21 | 10.50 | -1.39 | 66.23% | 33.77% |
| 2024 | 77 | 13.24 | 18.23 | 9.59 | -2.26 | 70.13% | 29.87% |
| 2025 | 77 | 15.12 | 18.78 | 13.44 | 2.49 | 58.44% | 41.56% |
| 2026 completed | 7 | 12.06 | 12.92 | 13.92 | 3.17 | 71.43% | 28.57% |

## Current Limitations

- RugbyPass does not currently return NPC archive fixtures for 2020 through the tested archive endpoint.
- Team totals are sparse because NPC RugbyPass pages often do not expose true team-total stat JSON.
- Player stats are leaderboard rows only; full player event stats are not yet available.
- Team sheets are available for only some matches.
- `RidgeMarginModel v0.3.0` did not improve the current margin benchmark, so combined forward predictions are not promoted.
- No injury, weather, travel, betting market, or squad announcement source is integrated yet.
- The baseline models are intentionally simple; calibration rows now exist, but no probability recalibration has been fitted yet.

## Todo List

### Next

- Review v0.2 calibration gaps and decide whether to add probability recalibration.
- Improve margin features before running another champion challenge.
- Review why ridge underperformed Elo-only, especially sparse team-sheet continuity and negative point-trend coefficients.
- Add model comparison notes for which baseline remains the benchmark to beat.

### Modelling

- Add logistic regression for home win probability using `vw_Gold_MatchFeatureMatrix`.
- Add a second margin challenger only after better explanatory data is available.
- Add backtest split controls by season and round.
- Add probability recalibration or logistic regression without replacing Elo-only until backtests justify it.

### Data

- Investigate other sources for 2020 NPC results.
- Add richer team totals if a reliable source is found.
- Add match event data:
  - tries
  - cards
  - substitutions
  - scoring timeline
- Add team availability inputs:
  - squad announcements
  - injuries
  - suspensions
  - returning All Blacks or representative players
- Add weather and venue conditions.

### Platform

- Add Power BI-ready reporting views.
- Add dashboard/API layer for:
  - upcoming match predictions
  - team form
  - head-to-head comparison
  - model performance
  - player continuity
- Add a data quality monitor for missing snapshots, missing team sheets, and suspicious `0-0` rows.

### Engineering

- Move database connection settings to environment variables.
- Add a lightweight test suite for parser and model functions.
- Add command wrappers for the standard pipeline:
  - scrape
  - load Silver
  - refresh Gold
  - run predictions
- Add run logs for model executions.
- Add CI checks for Python compile and SQL script linting where practical.
