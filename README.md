# BTA Rugby Analytics

BTA Rugby Analytics is a rugby data and modelling platform for historical analysis, trend detection, and match prediction.

The project is being built in layers:

| Layer | Purpose |
| --- | --- |
| Bronze | Capture raw source data exactly as collected |
| Silver | Normalise competitions, teams, players, matches, and stats |
| Gold | Build model-ready features, predictions, and backtests |

See [docs/platform_blueprint.md](docs/platform_blueprint.md) for the full platform direction and [docs/project_status.md](docs/project_status.md) for completed work and the current todo list.

## Current Ingestion

The current ingestion source is the RugbyPass Hilux NPC scraper:

```text
rugbypass_scraper/rugbypass_scraper/scraper.py
```

It currently populates:

- `Bronze_SourceSnapshots`
- `NPC_Matches`
- `NPC_TeamStats`
- `NPC_PlayerStats`
- `NPC_PlayerAppearances`

NPC player leaderboard rows and team-sheet appearances are kept separate from team totals to avoid cross-pollinating player rankings with team match statistics.

## Database Scripts

Run these scripts in order against SQL Server:

1. `database/platform_schema.sql`
2. `rugbypass_scraper/rugbypass_scraper/setup.sql`
3. `rugbypass_scraper/rugbypass_scraper/scraper.py`
4. `database/load_npc_to_silver.sql`
5. `database/gold_feature_views.sql`
6. `database/model_evaluation_views.sql`
7. `analytics/baseline_evaluation.py`
8. `analytics/ridge_margin_model.py`
9. `analytics/run_production_predictions.py`

The database name is currently:

```text
RugbyAnalytics
```

## Current Gold Views

- `vw_Gold_TeamMatchBase`: team-perspective match results.
- `vw_Gold_TeamFormFeatures`: rolling form, attack/defence trends, venue splits, and rest days.
- `vw_Gold_HeadToHeadFeatures`: recent head-to-head result and margin signals.
- `vw_Gold_TeamSheetFeatures`: listed players, starters, substitutes, and returning-player continuity.
- `vw_Gold_MatchFeatureMatrix`: one model-ready row per completed match.

## Current Baseline Model

`analytics/baseline_evaluation.py` writes transparent benchmark model predictions, walk-forward backtests, and calibration rows to:

- `Gold_ModelVersions`
- `Gold_MatchPredictions`
- `Gold_BacktestResults`
- `Gold_PredictionEvaluations`
- `Gold_ModelCalibration`

Current baseline release:

```text
Baseline Evaluation v0.2
```

Run all benchmark models:

```powershell
python analytics/baseline_evaluation.py --model all --evaluation-season all
```

Run one model:

```powershell
python analytics/baseline_evaluation.py --model EloOnlyBaseline --evaluation-season all
```

Run one evaluation season:

```powershell
python analytics/baseline_evaluation.py --model all --evaluation-season 2025
```

Use `--dry-run` to calculate without writes and `--replace` to replace stored results for the same model/version/evaluation window.

Walk-forward evaluation uses seasons before 2023 to evaluate 2023, seasons through 2023 to evaluate 2024, seasons through 2024 to evaluate 2025, and seasons through 2025 to evaluate completed 2026 matches. Draws are included in probability metrics and margin metrics; winner accuracy excludes draws.

Current comparison views:

- `vw_Gold_ModelPerformanceComparison`
- `vw_Gold_ModelCalibration`
- `vw_Gold_ModelPerformanceByTeam`
- `vw_Gold_ModelPerformanceByRoundBand`

## Dedicated Margin Model

`analytics/ridge_margin_model.py` implements `RidgeMarginModel v0.3.0`.

It predicts home margin with fixed-alpha ridge regression while preserving `EloOnlyBaseline v0.2.0` probabilities for home/draw/away. Feature scaling and imputation are learned from the training window only, and each prediction stores an intercept row plus ranked feature contributions.

Run the model:

```powershell
D:\Cursor\BTA_Rugby\.venv\Scripts\python.exe analytics\ridge_margin_model.py --replace
```

Current champion status: `Rejected` versus Elo-only for complete 2023-2025 margin performance. Ridge weighted MAE was 13.56 versus Elo-only 12.81, with zero of three complete seasons beaten.

Additional v0.3 views:

- `vw_Gold_RidgeModelParameters`
- `vw_Gold_RidgePredictionExplanation`
- `vw_Gold_RidgeStrongestDrivers`
- `vw_Gold_MarginModelComparison`
- `vw_Gold_MarginChampionStatus`
- `vw_Gold_CombinedUpcomingPredictions`

## Production Predictions v0.4

`analytics/run_production_predictions.py` registers the active production model registry and writes Power BI-ready upcoming predictions.

Current production decision:

- `EloOnlyBaseline v0.2.0` is active champion for win probability.
- `EloOnlyBaseline v0.2.0` is the active margin incumbent.
- `RidgeMarginModel v0.3.0` remains rejected for margin.

Run production predictions:

```powershell
D:\Cursor\BTA_Rugby\.venv\Scripts\python.exe analytics\run_production_predictions.py --dry-run --season 2026
D:\Cursor\BTA_Rugby\.venv\Scripts\python.exe analytics\run_production_predictions.py --season 2026
```

Use `--replace` to intentionally replace existing production predictions for the same match and champion model versions. Use `--match-id <id>` to regenerate one fixture.

Production reporting views:

- `vw_Gold_ProductionUpcomingPredictions`
- `vw_Gold_ProductionHistoricalPredictions`
- `vw_Gold_ProductionMatchExplanation`
- `vw_Gold_ProductionModelSummary`
- `vw_Gold_ProductionCalibration`
- `vw_Gold_ProductionDataQuality`
- `vw_Gold_ProductionPipelineRuns`

Power BI build notes are in [docs/powerbi_reporting_guide.md](docs/powerbi_reporting_guide.md).

## Near-Term Roadmap

1. Improve the margin feature set before another champion challenge.
2. Review v0.2 probability calibration gaps before adding logistic models.
3. Add richer source data for team totals, events, and injuries when available.
4. Surface predictions and explanations in a dashboard/API.
5. Add run logs and CI checks around evaluation scripts.
