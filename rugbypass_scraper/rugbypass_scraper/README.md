# RugbyPass Hilux NPC Scraper

Pulls Hilux NPC match metadata and team stats from RugbyPass into a local SQL Server database.

## Quick Start

### 1. Install dependencies

```bash
pip install playwright pyodbc
playwright install chromium
```

### 2. Create the database

Run `setup.sql` in SSMS against your local SQL Server.

### 3. Configure the scraper

Open `scraper.py` and update `SQL_CONNECTION_STRING` if needed:

```python
SQL_CONNECTION_STRING = (
    "DRIVER={ODBC Driver 17 for SQL Server};"
    "SERVER=BIGTEDS;"
    "DATABASE=RugbyAnalytics;"
    "Trusted_Connection=yes;"
    "TrustServerCertificate=yes;"
)
```

The current competition config is:

```python
SEASON = 2026
COMPETITION_CODE = "NPC"
TOURNAMENT_URI = "bunnings-npc"
```

### 4. Run

```bash
python scraper.py
```

## What It Does

1. Opens the RugbyPass Hilux NPC fixtures page.
2. Extracts game IDs and match metadata.
3. Visits each match stats page.
4. Parses home and away team stats.
5. Upserts into SQL Server so re-runs do not duplicate matches.

## Database Structure

| Table | Content |
| --- | --- |
| `NPC_Matches` | One row per match with teams, score, venue, and date |
| `NPC_TeamStats` | Two rows per match, one per team |

| View | Use |
| --- | --- |
| `vw_MatchResults` | Match results with winner and margin |
| `vw_TeamPerformance` | Team-level match stats with derived metrics |

## Stats Captured

| Group | Stats |
| --- | --- |
| Scoring | Tries, conversions, penalty goals, drop goals, points for/against |
| Attack | Carries, ball carries, post-contact metres, line breaks, passes |
| Possession | Possession %, possession last 10 min %, territory % |
| 22m | Entries, conversion rate |
| Set piece | Scrum win %, lineout win %, restarts received win % |
| Defence | Tackles made/missed, tackle completion % |
| Discipline | Penalties conceded, yellow cards, red cards |
| Kicking | Total kicks, kick-pass ratio |
| Ruck speed | 0-3s %, 3-6s %, rucks won |
| Game flow | Minutes in lead, % game in lead, points last 10 min |

## Debugging

Set `HEADLESS = False` in `scraper.py` to watch the browser navigate pages.

If fixture discovery returns zero game IDs, check RugbyPass manually and confirm the NPC page still uses:

```text
https://www.rugbypass.com/bunnings-npc/fixtures-results/
```

## Extending to Other Competitions

Update these values in `scraper.py`:

```python
COMPETITION_CODE = "SRP"
COMPETITION_NAME = "Super Rugby Pacific"
TOURNAMENT_URI = "super-rugby"
```

The table names are derived from `COMPETITION_CODE`.
