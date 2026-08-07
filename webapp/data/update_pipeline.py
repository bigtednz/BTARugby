"""Controlled local data update pipeline for the Match Centre."""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from webapp.config import AppConfig, PROJECT_ROOT


@dataclass(frozen=True)
class PipelineStep:
    label: str
    command: list[str]


@dataclass(frozen=True)
class PipelineResult:
    succeeded: bool
    started_at: datetime
    finished_at: datetime
    steps_run: int
    message: str


def build_update_steps(config: AppConfig) -> list[PipelineStep]:
    python = sys.executable
    season = str(config.data_update_season)
    steps: list[PipelineStep] = []
    if config.data_update_run_scraper:
        steps.append(PipelineStep("Scrape RugbyPass latest fixtures", [python, "rugbypass_scraper/rugbypass_scraper/scraper.py"]))
    steps.extend(
        [
            PipelineStep("Backfill result lifecycle", [python, "analytics/backfill_result_lifecycle.py", "--season", season]),
            PipelineStep("Load NPC to Silver", [python, "analytics/apply_sql_script.py", "database/load_npc_to_silver.sql"]),
            PipelineStep("Refresh Gold feature views", [python, "analytics/apply_sql_script.py", "database/gold_feature_views.sql"]),
            PipelineStep("Refresh Gold reporting views", [python, "analytics/apply_sql_script.py", "database/model_evaluation_views.sql"]),
        ]
    )
    if config.data_update_run_predictions:
        steps.append(PipelineStep("Refresh production predictions", [python, "analytics/run_production_predictions.py", "--replace", "--season", season]))
    return steps


def _short_output(text: str, limit: int = 500) -> str:
    cleaned = " ".join((text or "").split())
    if len(cleaned) <= limit:
        return cleaned
    return f"{cleaned[:limit].rstrip()}..."


def run_update_pipeline(config: AppConfig, root: Path = PROJECT_ROOT) -> PipelineResult:
    started_at = datetime.now()
    steps = build_update_steps(config)
    env = os.environ.copy()
    env["PYTHONPATH"] = str(root)
    if config.sql_connection_string:
        env["BTA_SQL_CONNECTION_STRING"] = config.sql_connection_string
    for index, step in enumerate(steps, start=1):
        try:
            completed = subprocess.run(
                step.command,
                cwd=root,
                env=env,
                capture_output=True,
                text=True,
                timeout=config.data_update_timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired:
            finished_at = datetime.now()
            return PipelineResult(False, started_at, finished_at, index - 1, f"{step.label} timed out.")
        if completed.returncode != 0:
            output = _short_output(completed.stderr or completed.stdout)
            finished_at = datetime.now()
            return PipelineResult(False, started_at, finished_at, index - 1, f"{step.label} failed. {output}".strip())
    finished_at = datetime.now()
    return PipelineResult(True, started_at, finished_at, len(steps), f"Latest data update complete ({len(steps)} steps).")


def format_update_result(result: PipelineResult | None) -> str:
    if result is None:
        return ""
    status = "Succeeded" if result.succeeded else "Failed"
    return f"{status} {result.finished_at.strftime('%d %b %Y, %I:%M %p')} - {result.message}"
