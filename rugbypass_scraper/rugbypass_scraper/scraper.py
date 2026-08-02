"""
RugbyPass Hilux NPC 2026 Stats Scraper
===================================================
Pulls all match stats for the 2026 season into a local SQL Server database.

Requirements (run once):
    pip install playwright pyodbc
    playwright install chromium

Usage:
    python scraper.py

Config:
    Edit SQL_CONNECTION_STRING below before running.
"""

import asyncio
import json
import re
import logging
import os
import pyodbc
from datetime import datetime
from playwright.async_api import async_playwright

# ── CONFIG ────────────────────────────────────────────────────────────────────
SEASON           = 2026
COMPETITION_CODE = "NPC"
COMPETITION_NAME = "Hilux NPC"
TOURNAMENT_URI   = "bunnings-npc"
BASE_URL         = "https://www.rugbypass.com"
FIXTURES_URL     = f"{BASE_URL}/{TOURNAMENT_URI}/fixtures-results/"
MATCHES_TABLE    = f"{COMPETITION_CODE}_Matches"
STATS_TABLE      = f"{COMPETITION_CODE}_TeamStats"
MATCH_TEAM_UQ    = f"UQ_{COMPETITION_CODE}_MatchTeam"
MIN_GAME_ID      = 100_000
MAX_GAME_ID      = 9_999_999

SQL_CONNECTION_STRING = (
    "DRIVER={ODBC Driver 17 for SQL Server};"
    "SERVER=BIGTEDS;"
    "DATABASE=RugbyAnalytics;"
    "Trusted_Connection=yes;"
    "TrustServerCertificate=yes;"
)

RATE_LIMIT_SECONDS   = 3
REQUEST_TIMEOUT      = 30000  # ms
HEADLESS             = True   # set False to watch the browser (useful for debugging)
MAX_FAILURES_TO_SHOW = 5      # stop early so debugging is fast
DEBUG_HTML_DIR       = "debug_html"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S"
)
log = logging.getLogger(__name__)

# ── SQL DDL ───────────────────────────────────────────────────────────────────
DDL_MATCHES = f"""
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = '{MATCHES_TABLE}')
CREATE TABLE {MATCHES_TABLE} (
    MatchID     INT PRIMARY KEY,
    Season      INT,
    Round       VARCHAR(20),
    MatchDate   DATE,
    Venue       VARCHAR(100),
    HomeTeam    VARCHAR(50),
    AwayTeam    VARCHAR(50),
    HomeScore   INT,
    AwayScore   INT,
    ScrapedAt   DATETIME DEFAULT GETDATE()
)
"""

DDL_STATS = f"""
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = '{STATS_TABLE}')
CREATE TABLE {STATS_TABLE} (
    StatID                  INT IDENTITY PRIMARY KEY,
    MatchID                 INT REFERENCES {MATCHES_TABLE}(MatchID),
    Season                  INT,
    Team                    VARCHAR(50),
    HomeAway                CHAR(1),
    -- Scoring
    Tries                   INT,
    Conversions             INT,
    PenaltyGoals            INT,
    DropGoals               INT,
    PointsFor               INT,
    PointsAgainst           INT,
    -- Attack
    Carries                 INT,
    BallCarries             INT,
    PostContactMetres       INT,
    LineBreaks              INT,
    Passes                  INT,
    -- Possession / Territory
    PossessionPct           DECIMAL(5,4),
    PossessionLast10Pct     DECIMAL(5,4),
    TerritoryPct            DECIMAL(5,4),
    -- 22m
    Entries22m              INT,
    Conversion22m           DECIMAL(5,2),
    -- Set Piece
    ScrumWon                INT,
    ScrumWinPct             DECIMAL(5,4),
    LineoutWon              INT,
    LineoutWinPct           DECIMAL(5,4),
    RestartsReceived        INT,
    RestartsReceivedWinPct  DECIMAL(5,4),
    -- Defence
    TacklesMade             INT,
    TacklesMissed           INT,
    TackleCompletionPct     DECIMAL(5,4),
    -- Turnovers
    TurnoversWon            INT,
    TurnoversLost           INT,
    -- Discipline
    PenaltiesConceded       INT,
    YellowCards             INT,
    RedCards                INT,
    -- Kicking
    TotalKicks              INT,
    KickToPassRatio         DECIMAL(5,4),
    -- Ruck speed
    RuckSpeed0to3Pct        DECIMAL(5,4),
    RuckSpeed3to6Pct        DECIMAL(5,4),
    RucksWon                INT,
    -- Game flow
    MinsInLead              INT,
    PctGameInLead           DECIMAL(5,4),
    PointsLast10            INT,
    ScrapedAt               DATETIME DEFAULT GETDATE(),
    CONSTRAINT {MATCH_TEAM_UQ} UNIQUE (MatchID, Team)
)
"""

DDL_ALTER = f"""
-- Widen KickToPassRatio so ratios above 9.9 don't overflow DECIMAL(5,4)
IF EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_NAME   = '{STATS_TABLE}'
      AND COLUMN_NAME  = 'KickToPassRatio'
      AND NUMERIC_PRECISION = 5
)
    ALTER TABLE {STATS_TABLE} ALTER COLUMN KickToPassRatio DECIMAL(8,4) NULL;
"""

DDL_VIEWS = f"""
CREATE OR ALTER VIEW vw_MatchResults AS
SELECT
    m.MatchID, m.Season, m.Round, m.MatchDate, m.Venue,
    m.HomeTeam, m.AwayTeam, m.HomeScore, m.AwayScore,
    m.HomeScore - m.AwayScore AS HomeMargin,
    CASE WHEN m.HomeScore > m.AwayScore THEN m.HomeTeam
         WHEN m.AwayScore > m.HomeScore THEN m.AwayTeam
         ELSE 'Draw' END AS Winner
FROM {MATCHES_TABLE} m
"""

DDL_VIEW2 = f"""
CREATE OR ALTER VIEW vw_TeamPerformance AS
SELECT
    ts.StatID, ts.MatchID, ts.Season, ts.Team, ts.HomeAway,
    m.Round, m.MatchDate, m.Venue,
    CASE WHEN ts.HomeAway = 'H' THEN m.AwayTeam ELSE m.HomeTeam END AS Opponent,
    ts.Tries, ts.Conversions, ts.PenaltyGoals, ts.DropGoals,
    ts.PointsFor, ts.PointsAgainst,
    ts.PointsFor - ts.PointsAgainst AS Margin,
    CASE WHEN ts.PointsFor > ts.PointsAgainst THEN 'W'
         WHEN ts.PointsFor < ts.PointsAgainst THEN 'L'
         ELSE 'D' END AS Result,
    (ts.Tries - ts.Conversions) * 2 AS PointsLeftOnField,
    CASE WHEN ts.PointsFor > ts.PointsAgainst THEN 4
         WHEN ts.PointsAgainst - ts.PointsFor <= 7 THEN 1
         ELSE 0 END AS LogPoints,
    ts.Carries, ts.BallCarries, ts.PostContactMetres, ts.LineBreaks, ts.Passes,
    ts.PossessionPct, ts.PossessionLast10Pct, ts.TerritoryPct,
    ts.Entries22m, ts.Conversion22m,
    ts.ScrumWon, ts.ScrumWinPct,
    ts.LineoutWon, ts.LineoutWinPct,
    ts.RestartsReceived, ts.RestartsReceivedWinPct,
    ts.TacklesMade, ts.TacklesMissed, ts.TackleCompletionPct,
    ts.TurnoversWon, ts.TurnoversLost,
    ts.PenaltiesConceded, ts.YellowCards, ts.RedCards,
    ts.TotalKicks, ts.KickToPassRatio,
    CASE WHEN ts.Passes > 0
         THEN CAST(ts.TotalKicks AS FLOAT) / NULLIF(ts.Passes,0)
         ELSE NULL END AS KTPRatioCalc,
    ts.RuckSpeed0to3Pct, ts.RuckSpeed3to6Pct, ts.RucksWon,
    ts.MinsInLead, ts.PctGameInLead, ts.PointsLast10
FROM {STATS_TABLE} ts
JOIN {MATCHES_TABLE} m ON ts.MatchID = m.MatchID
"""

# ── BASIC HELPERS ─────────────────────────────────────────────────────────────
def safe_int(val):
    try:
        return int(str(val).replace(',', '').strip())
    except Exception:
        return None

def safe_pct(val):
    """Convert 0.86, 86, or '86%' to decimal 0–1."""
    try:
        s = str(val).strip().replace('%', '')
        f = float(s)
        return round(f if f <= 1 else f / 100, 4)
    except Exception:
        return None

def safe_float(val):
    try:
        return round(float(str(val).strip()), 4)
    except Exception:
        return None

def parse_ratio(val):
    """'1:4.3' → 4.3"""
    try:
        return round(float(str(val).split(':')[1]), 4)
    except Exception:
        return None

def strip_html(content):
    text = re.sub(r'<[^>]+>', ' ', content)
    return re.sub(r'\s+', ' ', text)

def team_slug(name: str) -> str:
    """'Western Force' → 'western-force'"""
    slug = name.lower().replace(' ', '-').replace("'", '').replace('.', '')
    return re.sub(r'-+', '-', slug).strip('-')

def save_debug_html(game_id: int, content: str):
    os.makedirs(DEBUG_HTML_DIR, exist_ok=True)
    path = os.path.join(DEBUG_HTML_DIR, f"game_{game_id}.html")
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    log.info(f"  Debug HTML saved → {path}")

def find_pair(label, text):
    """
    Find the two numeric values flanking a stat label in rendered page text.
    URL pattern is /live/{away}-vs-{home}/stats/ so the page displays:
        AWAY_VALUE  <label>  HOME_VALUE
    Returns (away_val_str, home_val_str).
    Numbers may contain commas (e.g. "1,234") and optional %.
    """
    escaped = re.escape(label)
    num = r'[\d,]+(?:\.\d+)?%?'
    m = re.search(rf'({num})\s+{escaped}\s+({num})', text, re.IGNORECASE)
    if m:
        return m.group(1).replace(',', ''), m.group(2).replace(',', '')
    return None, None

# ── JSON / NEXT_DATA HELPERS ──────────────────────────────────────────────────
def parse_next_data(content: str) -> dict:
    """Extract and parse the __NEXT_DATA__ JSON block embedded by Next.js."""
    m = re.search(
        r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>\s*(.+?)\s*</script>',
        content, re.DOTALL
    )
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError as e:
            log.debug(f"__NEXT_DATA__ parse error: {e}")
    return {}

def find_all(obj, predicate, found=None):
    """
    Recursively collect every item for which predicate(item) is True.
    Does NOT recurse into matched objects (avoids extracting sub-fields as matches).
    """
    if found is None:
        found = []
    if predicate(obj):
        found.append(obj)
        return found   # don't descend into a matched node
    if isinstance(obj, dict):
        for v in obj.values():
            find_all(v, predicate, found)
    elif isinstance(obj, list):
        for item in obj:
            find_all(item, predicate, found)
    return found

def deep_get(obj, *keys, default=None):
    """Return the value of the first non-None key found in a dict."""
    if isinstance(obj, dict):
        for k in keys:
            if k in obj and obj[k] is not None:
                return obj[k]
    return default

def is_match_dict(d):
    """True if d looks like a fixture/match object with teams on both sides."""
    if not isinstance(d, dict):
        return False
    has_id    = any(k in d for k in ('id', 'matchId', 'gameId'))
    has_teams = (('homeTeam' in d or 'home_team' in d) and
                 ('awayTeam' in d or 'away_team' in d))
    return has_id and has_teams

def parse_match_from_dict(d: dict) -> dict | None:
    """Build a normalised game-info dict from a match-like JSON object."""
    gid = deep_get(d, 'id', 'matchId', 'gameId', 'game_id')
    if not gid:
        return None
    try:
        gid = int(gid)
    except (TypeError, ValueError):
        return None
    if not (MIN_GAME_ID <= gid <= MAX_GAME_ID):
        return None

    home_obj = deep_get(d, 'homeTeam', 'home_team', 'home') or {}
    away_obj = deep_get(d, 'awayTeam', 'away_team', 'away') or {}

    def team_name(obj):
        if isinstance(obj, str):
            return obj or None
        if isinstance(obj, dict):
            return (obj.get('name') or obj.get('fullName') or
                    obj.get('teamName') or obj.get('shortName') or None)
        return None

    home_name = team_name(home_obj)
    away_name = team_name(away_obj)
    if not home_name or not away_name:
        return None

    # Derive slug: prefer explicit slug field, fall back to generating from name
    def obj_slug(obj, name):
        if isinstance(obj, dict):
            s = obj.get('slug') or obj.get('uri') or obj.get('urlSlug') or ''
            if s:
                return s
        return team_slug(name)

    date_raw = str(deep_get(d, 'dateId', 'date', 'matchDate', 'startDate',
                             'kickoffDate', 'kickOff') or '')
    if re.match(r'^\d{8}$', date_raw):
        match_date = f"{date_raw[:4]}-{date_raw[4:6]}-{date_raw[6:8]}"
    elif re.match(r'^\d{4}-\d{2}-\d{2}', date_raw):
        match_date = date_raw[:10]
    else:
        match_date = None

    return {
        "game_id":    gid,
        "match_date": match_date,
        "home_team":  home_name,
        "away_team":  away_name,
        "home_slug":  obj_slug(home_obj, home_name),
        "away_slug":  obj_slug(away_obj, away_name),
        "home_score": safe_int(deep_get(d, 'homeScore', 'home_score')),
        "away_score": safe_int(deep_get(d, 'awayScore', 'away_score')),
        "round":      str(deep_get(d, 'round', 'roundName', 'roundNumber') or ''),
        "venue":      deep_get(d, 'venue', 'venueName', 'ground', 'stadium'),
    }

# ── FIXTURES HTML PARSER ──────────────────────────────────────────────────────
def parse_fixtures_html(content: str) -> dict:
    """
    Parse game metadata from the RugbyPass fixtures page HTML.

    Each game card looks like:
        <div class="comp-game" data-round="Round 1">
          <div class="teams">
            <div class="team home"><img alt="Highlanders"> ...</div>
            <div class="middle"><div class="scores">
              <div class="score">25</div>...<div class="score">23</div>
            </div></div>
            <div class="team away"><img alt="Canterbury"> ...</div>
          </div>
          <div class="venue">Forsyth Barr Stadium</div>
          <a href="/live/canterbury-vs-wellington/?g=950838" ...>
        </div>

    URL order is {away}-vs-{home}.  Scores appear home-first in the HTML.
    """
    games = {}

    link_pat = re.compile(
        r'href="https://www\.rugbypass\.com/live/([^/"]+)-vs-([^/"]+)/\?g=(\d+)"'
    )

    for link_m in link_pat.finditer(content):
        away_slug_val = link_m.group(1)
        home_slug_val = link_m.group(2)
        game_id = int(link_m.group(3))

        # Pull the comp-game card (search backwards from the link)
        block_start = content.rfind('<div class="comp-game"', 0, link_m.start())
        block = content[max(block_start, 0):link_m.end()]

        # Team names from the img alt in the home/away team divs
        home_m = re.search(r'class="team home"[^>]*>\s*<img[^>]+alt="([^"]+)"', block)
        away_m = re.search(r'class="team away"[^>]*>\s*<img[^>]+alt="([^"]+)"', block)

        # Scores: the two class="score" divs inside class="scores"
        scores = re.findall(r'class="score">(\d+)<', block)

        # Venue and round
        venue_m = re.search(r'class="venue">([^<]+)<', block)
        round_m = re.search(r'data-round="([^"]+)"', block)

        # Date header: nearest class="date" div before this card
        match_date = None
        date_block_start = content.rfind('<div class="date">', 0, max(block_start, 0))
        if date_block_start != -1:
            date_m = re.search(r'<div class="date">([^<]+)<',
                               content[date_block_start:date_block_start + 100])
            if date_m:
                try:
                    match_date = datetime.strptime(
                        date_m.group(1).strip(), '%a %d %b, %Y'
                    ).strftime('%Y-%m-%d')
                except ValueError:
                    pass

        games[game_id] = {
            "game_id":    game_id,
            "home_team":  home_m.group(1).strip() if home_m else None,
            "away_team":  away_m.group(1).strip() if away_m else None,
            "home_slug":  home_slug_val,
            "away_slug":  away_slug_val,
            "home_score": int(scores[0]) if len(scores) >= 1 else None,
            "away_score": int(scores[1]) if len(scores) >= 2 else None,
            "venue":      venue_m.group(1).strip() if venue_m else None,
            "round":      round_m.group(1) if round_m else None,
            "match_date": match_date,
        }

    return games


# ── STEP 1: DISCOVER GAME IDs ─────────────────────────────────────────────────
async def get_game_ids(page):
    log.info("Loading fixtures page to discover game IDs...")

    api_responses = []

    async def on_response(response):
        if response.status != 200:
            return
        ct = response.headers.get('content-type', '')
        if 'json' not in ct:
            return
        url = response.url
        if any(k in url for k in ['/fixture', '/match', '/game', '/round',
                                    '/tournament', '/schedule', '/season',
                                    TOURNAMENT_URI, 'rugby']):
            try:
                data = await response.json()
                api_responses.append((url, data))
            except Exception:
                pass

    page.on("response", on_response)

    await page.goto(FIXTURES_URL, wait_until="networkidle", timeout=REQUEST_TIMEOUT)
    await page.wait_for_timeout(4000)

    # Scroll to trigger lazy-loaded fixtures until page height stabilises
    prev_height = -1
    for _ in range(20):
        curr_height = await page.evaluate("document.body.scrollHeight")
        if curr_height == prev_height:
            break
        prev_height = curr_height
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(1500)

    content = await page.content()
    games = {}

    def merge_candidates(candidates):
        for d in candidates:
            info = parse_match_from_dict(d)
            if info and info['game_id'] not in games:
                games[info['game_id']] = info

    # ── Primary: __NEXT_DATA__ embedded JSON ──────────────────────────────────
    next_data = parse_next_data(content)
    if next_data:
        candidates = find_all(next_data, is_match_dict)
        log.info(f"__NEXT_DATA__: {len(candidates)} match-like objects")
        merge_candidates(candidates)

    # ── Secondary: captured XHR/fetch API responses ───────────────────────────
    if not games and api_responses:
        log.info(f"Trying {len(api_responses)} captured API responses...")
        for _url, data in api_responses:
            merge_candidates(find_all(data, is_match_dict))

    # ── Tertiary: scan every <script> block for parseable JSON ────────────────
    if not games:
        log.warning("Primary sources empty — scanning all inline script blocks...")
        for sm in re.finditer(r'<script[^>]*>(\{[^<]{50,})</script>', content, re.DOTALL):
            try:
                data = json.loads(sm.group(1))
                merge_candidates(find_all(data, is_match_dict))
            except (json.JSONDecodeError, ValueError):
                pass

    # ── Quaternary: parse the fixtures page HTML card structure ───────────────
    if not games:
        log.info("Parsing fixture card HTML directly...")
        all_cards = parse_fixtures_html(content)
        # Only keep cards where team names were extracted — non-SRP fixture cards
        # (sidebar/related games) tend to use a different HTML structure that
        # doesn't expose alt text, so their home_team/away_team come back as None.
        games = {k: v for k, v in all_cards.items()
                 if v.get('home_team') and v.get('away_team')}
        log.info(f"  Parsed {len(all_cards)} fixture cards, "
                 f"{len(games)} with full team metadata")

    # ── Last resort: pull IDs only — no team names or slugs ──────────────────
    if not games:
        log.warning("No structured match data found — ID-only fallback (stats will need slugs)")
        for m in re.finditer(r'"(?:id|gameId|matchId)"\s*:\s*(\d{6,7})', content):
            gid = int(m.group(1))
            if MIN_GAME_ID <= gid <= MAX_GAME_ID and gid not in games:
                games[gid] = {"game_id": gid}

    log.info(f"Found {len(games)} games")
    for gid, info in list(games.items())[:3]:
        log.info(f"  Sample: {gid} → {info.get('home_team')} vs "
                 f"{info.get('away_team')} ({info.get('match_date')})")
    return games

# ── STEP 2: MATCH METADATA ────────────────────────────────────────────────────
async def get_match_info(page, game_id, prefilled=None):
    """
    Use metadata already captured from the fixtures page when available.
    Falls back to loading the stats page and parsing __NEXT_DATA__ or HTML.
    """
    info = prefilled or {"game_id": game_id}

    if info.get("home_team") and info.get("away_team"):
        log.info(f"  Metadata from fixtures: {info['home_team']} vs {info['away_team']}")
        return info

    away_slug = info.get("away_slug", "")
    home_slug = info.get("home_slug", "")

    if away_slug and home_slug:
        url = f"{BASE_URL}/live/{away_slug}-vs-{home_slug}/stats/?g={game_id}"
    else:
        url = f"{BASE_URL}/live/stats/?g={game_id}"

    log.info(f"  Loading stats page for metadata: {url}")
    await page.goto(url, wait_until="domcontentloaded", timeout=REQUEST_TIMEOUT)
    await page.wait_for_timeout(3000)
    content = await page.content()

    # ── Try __NEXT_DATA__ first ────────────────────────────────────────────────
    next_data = parse_next_data(content)
    if next_data:
        candidates = find_all(next_data, is_match_dict)
        # Prefer an exact game_id match; otherwise take the first candidate
        for d in candidates:
            m_info = parse_match_from_dict(d)
            if m_info and m_info['game_id'] == game_id:
                log.info(f"  Metadata from __NEXT_DATA__: "
                         f"{m_info['home_team']} vs {m_info['away_team']}")
                return m_info
        if candidates:
            m_info = parse_match_from_dict(candidates[0])
            if m_info:
                log.info(f"  Metadata from __NEXT_DATA__ (first candidate): "
                         f"{m_info['home_team']} vs {m_info['away_team']}")
                return m_info

    # ── Fallback: regex on raw HTML ────────────────────────────────────────────
    # These patterns use [\s\S]*? (DOTALL-safe) instead of [^}]+ to handle
    # nested JSON objects inside the team field (e.g. logo, division, etc.)
    def rx(pattern):
        m = re.search(pattern, content, re.IGNORECASE | re.DOTALL)
        return m.group(1) if m else None

    # Extract team names — match up to 3 levels of nesting inside the team object
    def extract_team_name(field):
        pat = (rf'"{field}"\s*:\s*\{{(?:[^{{}}]|\{{[^{{}}]*\}}|\{{'
               r'(?:[^{}]|\{[^{}]*\})*\})*?"name"\s*:\s*"([^"]+)"')
        return rx(pat)

    info.setdefault("home_team", extract_team_name("homeTeam"))
    info.setdefault("away_team", extract_team_name("awayTeam"))

    for field, pattern in {
        "home_score": r'"homeScore"\s*:\s*(\d+)',
        "away_score": r'"awayScore"\s*:\s*(\d+)',
        "round":      r'"round"\s*:\s*"([^"]+)"',
        "venue":      r'"venue"\s*:\s*"([^"]+)"',
        "date_id":    r'"dateId"\s*:\s*"(\d{8})"',
    }.items():
        if field not in info:
            info[field] = rx(pattern)

    if info.get("date_id") and not info.get("match_date"):
        d = info["date_id"]
        info["match_date"] = f"{d[:4]}-{d[4:6]}-{d[6:8]}"

    for key in ("home_score", "away_score"):
        if info.get(key):
            info[key] = int(info[key])

    if info.get("home_team") and not info.get("home_slug"):
        info["home_slug"] = team_slug(info["home_team"])
    if info.get("away_team") and not info.get("away_slug"):
        info["away_slug"] = team_slug(info["away_team"])

    return info

# ── STEP 3: MATCH STATS ───────────────────────────────────────────────────────

# Possible JSON field names for each stat (most likely names first)
STAT_JSON_KEYS = {
    "tries":                     ["tries", "triesScored", "trys"],
    "conversions":               ["conversions", "conversionsMade"],
    "penalty_goals":             ["penaltyGoals", "penaltiesKicked", "penaltyKicks"],
    "drop_goals":                ["dropGoals"],
    "carries":                   ["carries", "totalCarries"],
    "ball_carries":              ["ballCarries"],
    "post_contact_metres":       ["postContactMetres", "postContactMeters", "postContactGain"],
    "line_breaks":               ["lineBreaks"],
    "passes":                    ["passes", "totalPasses"],
    "scrums_won":                ["scrumsWon", "scrums"],
    "scrum_win_pct":             ["scrumWinPct", "scrumSuccessRate", "scrumSuccess"],
    "lineout_won":               ["lineoutsWon", "lineoutWon"],
    "lineout_win_pct":           ["lineoutWinPct", "lineoutSuccessRate", "lineoutSuccess"],
    "restarts_received":         ["restartsReceived", "kickoffsReceived"],
    "restarts_received_win_pct": ["restartsReceivedWinPct", "restartWinPct"],
    "tackles_made":              ["tacklesMade", "tackles"],
    "tackles_missed":            ["tacklesMissed", "missedTackles"],
    "tackle_completion_pct":     ["tackleCompletionPct", "tackleSuccess", "tackleSuccessRate"],
    "turnovers_won":             ["turnoversWon", "turnovers"],
    "turnovers_lost":            ["turnoversLost"],
    "penalties_conceded":        ["penaltiesConceded", "penaltiesAgainst"],
    "yellow_cards":              ["yellowCards"],
    "red_cards":                 ["redCards"],
    "total_kicks":               ["totalKicks", "kicks"],
    "kick_to_pass_ratio":        ["kickToPassRatio"],
    "ruck_0_3":                  ["ruckSpeed0to3Pct", "ruck0to3", "ruckSpeedFast"],
    "ruck_3_6":                  ["ruckSpeed3to6Pct", "ruck3to6"],
    "rucks_won":                 ["rucksWon", "rucks"],
    "possession":                ["possession", "possessionPct", "possessionPercent"],
    "poss_last10":               ["possessionLast10Pct", "possessionLast10", "possessionLastTen"],
    "territory":                 ["territory", "territoryPct"],
    "entries_22m":               ["entries22m", "twentyTwoEntries"],
    "conversion_22m":            ["conversion22m", "twentyTwoConversionRate"],
    "mins_lead":                 ["minsInLead", "minutesInLead"],
    "pct_lead":                  ["pctGameInLead", "percentageInLead", "pctInLead"],
    "points_last10":             ["pointsLast10", "pointsLastTenMins"],
}

# Keys whose raw value is a percentage that needs normalising to 0–1
PCT_STAT_KEYS = {
    "scrum_win_pct", "lineout_win_pct", "restarts_received_win_pct",
    "tackle_completion_pct", "possession", "poss_last10", "territory",
    "ruck_0_3", "ruck_3_6", "pct_lead",
}

# Keys that are floats but NOT percentage conversions
FLOAT_STAT_KEYS = {"conversion_22m", "kick_to_pass_ratio"}

def _coerce(key, val):
    if key in PCT_STAT_KEYS:
        return safe_pct(val)
    if key in FLOAT_STAT_KEYS:
        return safe_float(val)
    return safe_int(val)

def extract_stats_from_json(data: dict, side: str) -> dict:
    """
    Try to pull stats for one side ('home' or 'away') from a JSON payload.
    Handles two common RugbyPass response shapes:
      1. Flat dicts keyed by side: data['homeStats'] / data['awayStats']
      2. Array of stat rows: data['stats'] = [{label, home, away}, ...]
    """
    stats = {}
    side_obj_keys = {
        'home': ['homeStats', 'home', 'homeTeamStats', 'team1Stats', 'team1'],
        'away': ['awayStats', 'away', 'awayTeamStats', 'team2Stats', 'team2'],
    }

    # --- Shape 1: find the side object anywhere in the JSON tree ---
    def find_side_obj(obj, target_keys):
        if isinstance(obj, dict):
            for k in target_keys:
                if k in obj and isinstance(obj[k], dict):
                    return obj[k]
            for v in obj.values():
                r = find_side_obj(v, target_keys)
                if r is not None:
                    return r
        elif isinstance(obj, list):
            for item in obj:
                r = find_side_obj(item, target_keys)
                if r is not None:
                    return r
        return None

    side_obj = find_side_obj(data, side_obj_keys[side])
    if isinstance(side_obj, dict):
        for our_key, json_keys in STAT_JSON_KEYS.items():
            for jk in json_keys:
                if jk in side_obj and side_obj[jk] is not None:
                    stats[f"{side}_{our_key}"] = _coerce(our_key, side_obj[jk])
                    break

    # --- Shape 2: array of {label/key, home, away} rows ---
    if len(stats) < 5:
        def find_stats_array(obj):
            if isinstance(obj, dict):
                for k in ('stats', 'matchStats', 'statistics', 'teamStats'):
                    if k in obj and isinstance(obj[k], list):
                        return obj[k]
                for v in obj.values():
                    r = find_stats_array(v)
                    if r:
                        return r
            elif isinstance(obj, list) and len(obj) > 3:
                if all(isinstance(i, dict) for i in obj[:3]):
                    return obj
            return None

        stats_array = find_stats_array(data)
        if stats_array:
            for item in stats_array:
                if not isinstance(item, dict):
                    continue
                label = str(item.get('label') or item.get('name') or item.get('key') or '')
                val   = item.get(side) or item.get(f'{side}Value')
                if not label or val is None:
                    continue
                norm = label.lower().replace(' ', '').replace('%', '').replace('_', '')
                for our_key, json_keys in STAT_JSON_KEYS.items():
                    if any(jk.lower().replace('_', '') == norm for jk in json_keys):
                        stats.setdefault(f"{side}_{our_key}", _coerce(our_key, val))
                        break

    return stats

async def get_match_stats(page, game_id, away_slug="", home_slug=""):
    """
    Load the RugbyPass stats page and extract all match statistics.
    URL format: /live/{away}-vs-{home}/stats/?g={game_id}  (away team is FIRST)
    So in the rendered text: away value appears LEFT of the label, home RIGHT.
    """
    if away_slug and home_slug:
        url = f"{BASE_URL}/live/{away_slug}-vs-{home_slug}/stats/?g={game_id}"
    else:
        url = f"{BASE_URL}/live/stats/?g={game_id}"

    log.info(f"  Stats URL: {url}")

    # Intercept JSON responses BEFORE navigating
    captured_json = []

    async def capture_response(response):
        if response.status != 200:
            return
        ct = response.headers.get('content-type', '')
        if 'json' not in ct:
            return
        resp_url = response.url
        if any(k in resp_url for k in [str(game_id), '/stats', '/live/', '/match', 'rugby']):
            try:
                data = await response.json()
                captured_json.append((resp_url, data))
            except Exception:
                pass

    page.on("response", capture_response)

    await page.goto(url, wait_until="networkidle", timeout=REQUEST_TIMEOUT)
    await page.wait_for_timeout(3000)
    content = await page.content()
    stats = {}

    # ── Primary: __NEXT_DATA__ ────────────────────────────────────────────────
    next_data = parse_next_data(content)
    if next_data:
        for side in ("home", "away"):
            stats.update(extract_stats_from_json(next_data, side))
        if len(stats) >= 10:
            log.info(f"  {len(stats)} stat values from __NEXT_DATA__")

    # ── Secondary: captured API/XHR responses ─────────────────────────────────
    if len(stats) < 10 and captured_json:
        log.info(f"  Trying {len(captured_json)} captured API responses for stats...")
        for _url, data in captured_json:
            for side in ("home", "away"):
                for k, v in extract_stats_from_json(data, side).items():
                    stats.setdefault(k, v)
        if len(stats) >= 10:
            log.info(f"  {len(stats)} stat values from API responses")

    # ── Tertiary: text parsing ─────────────────────────────────────────────────
    if len(stats) < 10:
        log.info("  Falling back to rendered text parsing...")
        text = strip_html(content)

        # URL is /{away}-vs-{home}/stats/ → left column = away, right = home
        int_stats = [
            ("Penalty Goals",       "penalty_goals"),
            ("Tries",               "tries"),
            ("Conversions",         "conversions"),
            ("Drop Goals",          "drop_goals"),
            ("Carries",             "carries"),
            ("Ball Carries",        "ball_carries"),
            ("Post Contact Metres", "post_contact_metres"),
            ("Line Breaks",         "line_breaks"),
            ("Passes",              "passes"),
            ("Scrums",              "scrums_won"),
            ("Lineout",             "lineout_won"),
            ("Restarts Received",   "restarts_received"),
            ("Tackles Made",        "tackles_made"),
            ("Tackles Missed",      "tackles_missed"),
            ("Turnovers Won",       "turnovers_won"),
            ("Turnovers Lost",      "turnovers_lost"),
            ("Penalties Conceded",  "penalties_conceded"),
            ("Yellow Cards",        "yellow_cards"),
            ("Red Cards",           "red_cards"),
            ("Total Kicks",         "total_kicks"),
            ("Rucks Won",           "rucks_won"),
            ("Mins in lead",        "mins_lead"),
            ("Points Last 10 min",  "points_last10"),
        ]
        pct_stats = [
            ("Possession Last 10 min",  "poss_last10"),
            ("Possession",              "possession"),
            ("Territory",               "territory"),
            ("Scrum Win %",             "scrum_win_pct"),
            ("Lineout Win %",           "lineout_win_pct"),
            ("Restarts Received Win %", "restarts_received_win_pct"),
            ("Tackle Completion %",     "tackle_completion_pct"),
            ("% Of Game In Lead",       "pct_lead"),
        ]

        for label, key in int_stats:
            away_v, home_v = find_pair(label, text)
            if home_v: stats.setdefault(f"home_{key}", safe_int(home_v))
            if away_v: stats.setdefault(f"away_{key}", safe_int(away_v))

        for label, key in pct_stats:
            away_v, home_v = find_pair(label, text)
            if home_v: stats.setdefault(f"home_{key}", safe_pct(home_v))
            if away_v: stats.setdefault(f"away_{key}", safe_pct(away_v))

        # 22m Conversion  (away left, home right)
        m = re.search(r'([\d.]+)\s+22m Conversion\s+([\d.]+)', text, re.IGNORECASE)
        if m:
            stats.setdefault("away_conversion_22m", safe_float(m.group(1)))
            stats.setdefault("home_conversion_22m", safe_float(m.group(2)))

        # 22m Entries
        m = re.search(r'(\d+)\s+22m Entries\s+(\d+)', text, re.IGNORECASE)
        if m:
            stats.setdefault("away_entries_22m", safe_int(m.group(1)))
            stats.setdefault("home_entries_22m", safe_int(m.group(2)))

        # Kick to pass ratio  e.g. "1:4.3 Kick To Pass Ratio 1:2.9"
        m = re.search(r'(1:[\d.]+)\s+Kick To Pass Ratio\s+(1:[\d.]+)', text, re.IGNORECASE)
        if m:
            stats.setdefault("away_kick_to_pass_ratio", parse_ratio(m.group(1)))
            stats.setdefault("home_kick_to_pass_ratio", parse_ratio(m.group(2)))

        # Ruck speed
        m = re.search(r'([\d.]+)%?\s+0-3 secs\s+([\d.]+)%?', text, re.IGNORECASE)
        if m:
            stats.setdefault("away_ruck_0_3", safe_pct(m.group(1)))
            stats.setdefault("home_ruck_0_3", safe_pct(m.group(2)))

        m = re.search(r'([\d.]+)%?\s+3-6 secs\s+([\d.]+)%?', text, re.IGNORECASE)
        if m:
            stats.setdefault("away_ruck_3_6", safe_pct(m.group(1)))
            stats.setdefault("home_ruck_3_6", safe_pct(m.group(2)))

        log.info(f"  Text parsing produced {len(stats)} stat values")

    if len(stats) < 10:
        log.warning(f"  Only {len(stats)} stats parsed — saving debug HTML")
        save_debug_html(game_id, content)

    return stats

# ── STEP 4: WRITE TO SQL ──────────────────────────────────────────────────────
def write_to_sql(conn, match_info, stats):
    cur = conn.cursor()
    gid = match_info["game_id"]

    cur.execute(f"""
        MERGE {MATCHES_TABLE} AS t
        USING (SELECT ? AS MatchID) AS s ON t.MatchID = s.MatchID
        WHEN NOT MATCHED THEN
            INSERT (MatchID,Season,Round,MatchDate,Venue,HomeTeam,AwayTeam,HomeScore,AwayScore)
            VALUES (?,?,?,?,?,?,?,?,?);
    """, (gid,
          gid, SEASON,
          match_info.get("round"),
          match_info.get("match_date"),
          match_info.get("venue"),
          match_info.get("home_team"),
          match_info.get("away_team"),
          match_info.get("home_score"),
          match_info.get("away_score")))

    for side in ("home", "away"):
        team = match_info.get(f"{side}_team")
        if not team:
            continue

        opp = "away" if side == "home" else "home"
        ha  = "H"   if side == "home" else "A"

        def g(key):
            return stats.get(f"{side}_{key}")

        # 41 values — must match UPDATE SET and INSERT VALUES counts exactly
        row = (
            SEASON, team, ha,
            g("tries"), g("conversions"), g("penalty_goals"), g("drop_goals"),
            match_info.get(f"{side}_score"), match_info.get(f"{opp}_score"),
            g("carries"), g("ball_carries"), g("post_contact_metres"),
            g("line_breaks"), g("passes"),
            g("possession"), g("poss_last10"), g("territory"),
            g("entries_22m"), g("conversion_22m"),
            g("scrums_won"), g("scrum_win_pct"),
            g("lineout_won"), g("lineout_win_pct"),
            g("restarts_received"), g("restarts_received_win_pct"),
            g("tackles_made"), g("tackles_missed"), g("tackle_completion_pct"),
            g("turnovers_won"), g("turnovers_lost"),
            g("penalties_conceded"), g("yellow_cards"), g("red_cards"),
            g("total_kicks"), g("kick_to_pass_ratio"),
            g("ruck_0_3"), g("ruck_3_6"), g("rucks_won"),
            g("mins_lead"), g("pct_lead"), g("points_last10"),
        )

        # params: 2 (USING) + 41 (UPDATE) + 1 (INSERT MatchID) + 41 (INSERT values) = 85
        _SQL_COL_NAMES = [
            'Season','Team','HomeAway','Tries','Conversions','PenaltyGoals','DropGoals',
            'PointsFor','PointsAgainst','Carries','BallCarries','PostContactMetres',
            'LineBreaks','Passes','PossessionPct','PossessionLast10Pct','TerritoryPct',
            'Entries22m','Conversion22m','ScrumWon','ScrumWinPct','LineoutWon',
            'LineoutWinPct','RestartsReceived','RestartsReceivedWinPct','TacklesMade',
            'TacklesMissed','TackleCompletionPct','TurnoversWon','TurnoversLost',
            'PenaltiesConceded','YellowCards','RedCards','TotalKicks','KickToPassRatio',
            'RuckSpeed0to3Pct','RuckSpeed3to6Pct','RucksWon','MinsInLead',
            'PctGameInLead','PointsLast10',
        ]
        try:
          cur.execute(f"""
            MERGE {STATS_TABLE} AS t
            USING (SELECT ? AS MatchID, ? AS Team) AS s
                ON t.MatchID = s.MatchID AND t.Team = s.Team
            WHEN MATCHED THEN UPDATE SET
                Season=?,Team=?,HomeAway=?,Tries=?,Conversions=?,PenaltyGoals=?,
                DropGoals=?,PointsFor=?,PointsAgainst=?,Carries=?,BallCarries=?,
                PostContactMetres=?,LineBreaks=?,Passes=?,PossessionPct=?,
                PossessionLast10Pct=?,TerritoryPct=?,Entries22m=?,Conversion22m=?,
                ScrumWon=?,ScrumWinPct=?,LineoutWon=?,LineoutWinPct=?,
                RestartsReceived=?,RestartsReceivedWinPct=?,TacklesMade=?,
                TacklesMissed=?,TackleCompletionPct=?,TurnoversWon=?,TurnoversLost=?,
                PenaltiesConceded=?,YellowCards=?,RedCards=?,TotalKicks=?,
                KickToPassRatio=?,RuckSpeed0to3Pct=?,RuckSpeed3to6Pct=?,RucksWon=?,
                MinsInLead=?,PctGameInLead=?,PointsLast10=?,ScrapedAt=GETDATE()
            WHEN NOT MATCHED THEN INSERT (
                MatchID,Season,Team,HomeAway,Tries,Conversions,PenaltyGoals,DropGoals,
                PointsFor,PointsAgainst,Carries,BallCarries,PostContactMetres,
                LineBreaks,Passes,PossessionPct,PossessionLast10Pct,TerritoryPct,
                Entries22m,Conversion22m,ScrumWon,ScrumWinPct,LineoutWon,
                LineoutWinPct,RestartsReceived,RestartsReceivedWinPct,TacklesMade,
                TacklesMissed,TackleCompletionPct,TurnoversWon,TurnoversLost,
                PenaltiesConceded,YellowCards,RedCards,TotalKicks,KickToPassRatio,
                RuckSpeed0to3Pct,RuckSpeed3to6Pct,RucksWon,MinsInLead,
                PctGameInLead,PointsLast10
            ) VALUES (
                ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?
            );
          """, (gid, team, *row, gid, *row))
        except pyodbc.Error as db_err:
            log.error(f"  SQL error writing {side} stats for game {gid}: {db_err}")
            for col, val in zip(_SQL_COL_NAMES, row):
                log.error(f"    {col:<30s} = {val!r}")
            raise

    conn.commit()
    log.info(f"  ✓ {match_info.get('home_team')} vs {match_info.get('away_team')} — saved")

# ── MAIN ──────────────────────────────────────────────────────────────────────
async def main():
    log.info(f"=== RugbyPass {COMPETITION_NAME} {SEASON} Scraper ===")

    log.info("Connecting to SQL Server...")
    try:
        conn = pyodbc.connect(SQL_CONNECTION_STRING)
        cur  = conn.cursor()
        cur.execute(DDL_MATCHES)
        cur.execute(DDL_STATS)
        cur.execute(DDL_ALTER)
        cur.execute(DDL_VIEWS)
        cur.execute(DDL_VIEW2)
        conn.commit()
        log.info("Database tables ready")
    except Exception as e:
        log.error(f"SQL connection failed: {e}")
        log.error("Check SQL_CONNECTION_STRING in the config section at the top of this file")
        return

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=HEADLESS)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800},
        )
        page = await context.new_page()

        games = await get_game_ids(page)

        if not games:
            log.error("No game IDs found.")
            log.error("Set HEADLESS = False and re-run to see what the browser loads.")
            await browser.close()
            conn.close()
            return

        log.info(f"Processing {len(games)} matches...")
        success, failed = 0, []

        for i, (game_id, _) in enumerate(games.items(), 1):
            log.info(f"[{i}/{len(games)}] Game ID {game_id}")
            try:
                cur.execute(
                    f"SELECT COUNT(*) FROM {STATS_TABLE} WHERE MatchID = ?", game_id
                )
                if cur.fetchone()[0] >= 2:
                    log.info("  → Already in DB, skipping")
                    continue

                match_info = await get_match_info(page, game_id, games[game_id])

                if not match_info.get("home_team"):
                    log.warning("  → Could not parse match metadata")
                    failed.append(game_id)
                    continue

                await asyncio.sleep(RATE_LIMIT_SECONDS)

                match_stats = await get_match_stats(
                    page, game_id,
                    away_slug=match_info.get("away_slug", ""),
                    home_slug=match_info.get("home_slug", ""),
                )
                write_to_sql(conn, match_info, match_stats)
                success += 1

            except Exception as e:
                log.error(f"  → Error: {e}")
                failed.append(game_id)
                if len(failed) >= MAX_FAILURES_TO_SHOW:
                    log.info(f"Reached {MAX_FAILURES_TO_SHOW} failures — stopping for debugging.")
                    break

            await asyncio.sleep(RATE_LIMIT_SECONDS)

        await browser.close()

    conn.close()
    log.info("=" * 50)
    log.info(f"Complete — Success: {success}  Failed: {len(failed)}")
    if failed:
        log.info(f"Failed IDs (re-run to retry): {failed}")

if __name__ == "__main__":
    asyncio.run(main())
