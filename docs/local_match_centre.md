# BTA Rugby Analytics Local Match Centre v0.5.1

## Purpose

The Local Match Centre is a read-only Dash browser application for product-style NPC match predictions, completed results, a derived competition table, player views, and match previews.

Power BI remains the internal analytical reporting and model-evaluation surface. The Dash browser application focuses on upcoming production predictions and individual match previews. SQL Gold views are the shared reporting contract for both interfaces.

## Architecture

```text
Scrape -> Bronze -> Silver -> Gold -> Elo update -> production predictions -> browser application
```

The web application reads from existing SQL Server Gold reporting views. It does not train models, recalculate Elo, generate predictions, or write to the database.

Directory structure:

```text
webapp/
  app.py
  config.py
  presentation.py
  data/repository.py
  pages/
  components/
  assets/styles.css
```

## SQL Views Used

- `dbo.vw_Gold_ProductionUpcomingPredictions`
- `dbo.vw_Gold_ProductionResults`
- `dbo.vw_Gold_FinalPreMatchProductionPrediction`
- `dbo.vw_Gold_PlayerTop10ByDiscipline`
- `dbo.vw_Gold_ProductionMatchExplanation`
- `dbo.vw_Gold_ProductionModelSummary`
- `dbo.vw_Gold_ModelPerformanceComparison`
- `dbo.vw_Gold_ProductionCalibration`
- `dbo.vw_Gold_ProductionDataQuality`
- `dbo.vw_Gold_ProductionPipelineRuns`
- `dbo.Silver_PlayerAppearances`
- `dbo.Silver_Players`
- `dbo.Silver_Teams`
- `dbo.Silver_Matches`
- `dbo.Silver_Seasons`
- `dbo.Silver_Competitions`
- `dbo.NPC_PlayerStats`

The repository layer uses parameterised SQL for variable inputs and blocks write-style SQL statements.

## Configuration

Copy `.env.example` to `.env` for local overrides. Do not commit `.env`.

Default local settings:

```text
BTA_SQL_SERVER=BIGTEDS
BTA_SQL_DATABASE=RugbyAnalytics
BTA_SQL_TRUSTED_CONNECTION=yes
BTA_APP_HOST=127.0.0.1
BTA_APP_PORT=8050
BTA_APP_DEBUG=false
BTA_CACHE_TTL_SECONDS=300
BTA_DATA_UPDATE_SEASON=2026
BTA_DATA_UPDATE_TIMEOUT_SECONDS=900
BTA_UPDATE_RUN_SCRAPER=false
BTA_UPDATE_RUN_PREDICTIONS=true
```

`BTA_SQL_CONNECTION_STRING` can be used for a complete ODBC connection string if needed.

## Installation

Install dependencies into the existing virtual environment:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Local Startup

Run:

```powershell
.\.venv\Scripts\python.exe webapp\app.py
```

Open:

```text
http://127.0.0.1:8050
```

The app binds to `127.0.0.1` by default and does not create a tunnel or hosted deployment.

## Cache Behaviour

The app caches the core Match Centre, model, calibration, data-quality and pipeline datasets for `BTA_CACHE_TTL_SECONDS`, defaulting to 300 seconds.

Normal filtering uses the cached in-memory dataset. The refresh button forces a reload of the relevant application caches. If refresh fails after a successful load, the app keeps showing the previous cached dataset and displays a safe database-unavailable message.

The `Update latest data` button runs the configured local update pipeline and then reloads the app cache. By default it backfills result lifecycle from existing Bronze snapshots, reloads Silver, refreshes Gold views and refreshes production predictions. Set `BTA_UPDATE_RUN_SCRAPER=true` to include a RugbyPass scrape before the SQL rebuild.

## Pages

Match Centre:

- Summary indicators for upcoming fixtures, next kickoff, average confidence, high-confidence fixtures and latest prediction generation.
- Filters for season, round, date range, team and confidence.
- Fixture cards with three-way probabilities, predicted winner, human-readable margin, confidence, model version and data-quality status.

Match Preview:

- Route: `/match/<MatchID>`.
- Reads the selected match through parameterised SQL.
- Shows kickoff, venue, probabilities, predicted winner, margin, model versions, Elo inputs, team-sheet availability, prior matches and contextual fields.
- Labels recent form, rest days, head-to-head and team-sheet fields as context only where appropriate.

Results:

- Route: `/results`.
- Shows completed and result-lifecycle rows from `vw_Gold_ProductionResults`.
- Filters by season, round, match-date range and team.
- Displays confirmed scorelines only when `ResultReadyFlag=1`.
- Shows final pre-match production prediction, predicted winner, actual winner, margin error and evaluation status where prediction history exists.

Table:

- Route: `/table`.
- Derives standings from `vw_Gold_ProductionResults`.
- Includes only `ResultReadyFlag=1` matches, so pending scores never affect the table.
- Uses win = 4 points and draw = 2 points because bonus-point data is not available yet.

Players:

- Route: `/players`.
- Shows Silver team-sheet appearances and dense-ranked top 10 season totals for each available player-stat discipline.
- Filters by season, team, stat and player search text.
- Keeps leaderboard ranking at season/competition/discipline/team/player grain and hides internal scrape row counts.

## Result Lifecycle

`MatchStatus` says whether a match is scheduled, live or completed. `ScoreStatus` says whether the score is pending, confirmed or unavailable. `ResultReadyFlag=1` means the score has source evidence and can be used by standings, result display and Gold feature views.

Production prediction evaluation is stricter:

- `PredictionAvailableFlag=1` means a retained final pre-match production prediction is available.
- `FinalPredictionPredatesKickoffFlag=1` means that retained prediction was generated before kickoff.
- `ProductionEvaluationEligibleFlag=1` means `ResultReadyFlag=1`, `PredictionAvailableFlag=1` and the prediction predates kickoff.
- `RetrospectiveModelEvaluationEligibleFlag=1` means the result can remain in retrospective/backtest datasets when those pipelines independently generate valid out-of-sample predictions.

Confirmed `0-0` scorelines are valid. Placeholder `0-0` values remain pending until RugbyPass Bronze evidence marks the fixture as a result with complete scores.

Model Performance and Pipeline Status:

- Foundation pages backed by existing Gold views.
- Intended to grow into richer charts after the Match Centre workflow is stable.

## Tests

Run all tests:

```powershell
.\.venv\Scripts\python.exe -m unittest discover tests
```

Run Python compilation checks:

```powershell
.\.venv\Scripts\python.exe -m compileall analytics tests webapp
```

## Known Limitations

- The app depends on the local SQL Server database and Gold views being present.
- No authentication is included in v0.5.0.
- Model Performance and Pipeline Status are table-first foundation pages.
- Standard tests mock database access; live database validation remains a local integration step.

## Future Development

Next useful development work is to add richer model-performance charts and a live integration smoke test that validates required Gold view columns against `BIGTEDS/RugbyAnalytics` without becoming part of normal offline tests.
