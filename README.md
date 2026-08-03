# BTA Rugby Analytics

BTA Rugby Analytics is a rugby data and modelling platform for historical analysis, trend detection, and match prediction.

The project is being built in layers:

| Layer | Purpose |
| --- | --- |
| Bronze | Capture raw source data exactly as collected |
| Silver | Normalise competitions, teams, players, matches, and stats |
| Gold | Build model-ready features, predictions, and backtests |

See [docs/platform_blueprint.md](docs/platform_blueprint.md) for the full platform direction.

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

## Near-Term Roadmap

1. Implement Elo and rolling-margin baseline predictions.
2. Store predictions in `Gold_MatchPredictions`.
3. Backtest every model version before using it for forward predictions.
4. Add richer source data for team totals, events, and injuries when available.
