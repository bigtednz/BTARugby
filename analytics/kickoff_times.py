"""
Kickoff date/time parsing for RugbyPass NPC fixtures.

RugbyPass supplies NPC dates separately from local kickoff strings. Store the
local datetime as Auckland civil time and derive UTC with the IANA timezone so
NZST/NZDT transitions are handled by the standard library.
"""

from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


try:
    AUCKLAND_TZ = ZoneInfo("Pacific/Auckland")
except ZoneInfoNotFoundError:
    AUCKLAND_TZ = None


@dataclass(frozen=True)
class KickoffInfo:
    match_date: str | None
    kickoff_datetime_local: datetime | None
    kickoff_datetime_utc: datetime | None
    kickoff_time_known: bool
    kickoff_time_source: str


def parse_match_date(value: object) -> str | None:
    text = str(value or "").strip()
    if re.match(r"^\d{8}$", text):
        return f"{text[:4]}-{text[4:6]}-{text[6:8]}"
    if re.match(r"^\d{4}-\d{2}-\d{2}", text):
        return text[:10]
    for fmt in ("%a %d %b, %Y", "%a %d %b %Y", "%a %b %d"):
        try:
            parsed = datetime.strptime(text, fmt)
            year = parsed.year if "%Y" in fmt else None
            if year:
                return parsed.strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def parse_time_value(value: object) -> tuple[int, int] | None:
    text = str(value or "").strip()
    if not text:
        return None
    match = re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*([ap]m)?\b", text, re.IGNORECASE)
    if not match:
        return None
    hour = int(match.group(1))
    minute = int(match.group(2) or "0")
    suffix = (match.group(3) or "").lower()
    if suffix == "pm" and hour < 12:
        hour += 12
    elif suffix == "am" and hour == 12:
        hour = 0
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    return hour, minute


def first_sunday(year: int, month: int) -> date:
    day = date(year, month, 1)
    return day + timedelta(days=(6 - day.weekday()) % 7)


def last_sunday(year: int, month: int) -> date:
    next_month = date(year + (month == 12), 1 if month == 12 else month + 1, 1)
    day = next_month - timedelta(days=1)
    return day - timedelta(days=(day.weekday() - 6) % 7)


def nz_offset_hours(local_dt: datetime) -> int:
    dst_start = datetime.combine(last_sunday(local_dt.year, 9), datetime.min.time()).replace(hour=2)
    dst_end = datetime.combine(first_sunday(local_dt.year, 4), datetime.min.time()).replace(hour=3)
    if dst_start <= local_dt < dst_start.replace(hour=3):
        raise ValueError(f"Invalid Auckland DST transition kickoff datetime: {local_dt}")
    if dst_end.replace(hour=2) <= local_dt < dst_end:
        raise ValueError(f"Ambiguous Auckland DST transition kickoff datetime: {local_dt}")
    return 13 if local_dt >= dst_start or local_dt < dst_end else 12


def local_to_utc(local_dt: datetime) -> datetime:
    if AUCKLAND_TZ is None:
        return local_dt - timedelta(hours=nz_offset_hours(local_dt))
    aware = local_dt.replace(tzinfo=AUCKLAND_TZ)
    utc = aware.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
    round_trip = utc.replace(tzinfo=ZoneInfo("UTC")).astimezone(AUCKLAND_TZ).replace(tzinfo=None)
    if round_trip != local_dt:
        raise ValueError(f"Invalid or ambiguous Auckland kickoff datetime: {local_dt}")
    return utc


def auckland_date_from_utc(utc_dt: datetime) -> date:
    if AUCKLAND_TZ is None:
        local_guess = utc_dt + timedelta(hours=12)
        return (utc_dt + timedelta(hours=nz_offset_hours(local_guess))).date()
    return utc_dt.replace(tzinfo=timezone.utc).astimezone(AUCKLAND_TZ).date()


def kickoff_from_values(match_date: str | None, time_value: object, source: str) -> KickoffInfo:
    if not match_date:
        return KickoffInfo(None, None, None, False, "Match date not supplied by source")
    parsed_time = parse_time_value(time_value)
    if parsed_time is None:
        return KickoffInfo(match_date, None, None, False, "Not supplied by source")
    hour, minute = parsed_time
    local_dt = datetime.strptime(match_date, "%Y-%m-%d").replace(hour=hour, minute=minute)
    return KickoffInfo(match_date, local_dt, local_to_utc(local_dt), True, source)


def kickoff_from_match_dict(game: dict) -> KickoffInfo:
    match_date = parse_match_date(
        game.get("dateId")
        or game.get("date")
        or game.get("matchDate")
        or game.get("startDate")
        or game.get("kickoffDate")
        or game.get("kickOff")
    )
    time_value = game.get("timeSmall") or game.get("time") or game.get("startTime") or game.get("kickoffTime")
    source_bits = []
    if game.get("time") is not None:
        source_bits.append(f"time={game.get('time')}")
    if game.get("timeSmall") is not None:
        source_bits.append(f"timeSmall={game.get('timeSmall')}")
    if game.get("epoch") is not None:
        source_bits.append(f"epoch={game.get('epoch')}")
    source = "RugbyPass current-game-days " + "; ".join(source_bits) if source_bits else "Not supplied by source"
    return kickoff_from_values(match_date, time_value, source)


def parse_current_game_days(content: str) -> dict[int, KickoffInfo]:
    match = re.search(
        r"<div[^>]+id=[\"']current-game-days[\"'][^>]*>(.*?)</div>",
        content,
        re.DOTALL | re.IGNORECASE,
    )
    if not match:
        return {}
    raw_json = html.unescape(match.group(1)).strip()
    if not raw_json:
        return {}
    game_days = json.loads(raw_json)
    results = {}
    for day in game_days:
        tournaments = day.get("tournaments", []) if isinstance(day, dict) else []
        if isinstance(tournaments, dict):
            tournaments = tournaments.values()
        for tournament in tournaments:
            if not isinstance(tournament, dict):
                continue
            for game in tournament.get("games", []) or []:
                if isinstance(game, dict) and game.get("id") is not None:
                    results[int(game["id"])] = kickoff_from_match_dict(game)
    return results


def kickoff_status(known: bool, source: str | None) -> str:
    if known:
        return "Confirmed"
    if source and source != "Not supplied by source":
        return source
    return "Not supplied by source"
