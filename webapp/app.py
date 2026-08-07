"""BTA Rugby Analytics v0.5.0 local Match Centre application."""

from __future__ import annotations

import logging
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import dash_bootstrap_components as dbc
from dash import ctx
import pandas as pd
from dash import Dash, Input, Output, State, dcc, html

from webapp.components.navigation import navigation
from webapp.config import AppConfig
from webapp.data.repository import MatchCentreRepository, RepositoryError
from webapp.data.update_pipeline import PipelineResult, format_update_result, run_update_pipeline
from webapp.pages import match_centre, match_preview, model_performance, pipeline_status, players, results, table
from webapp.presentation import records_from_frame, safe_error_message


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
LOGGER = logging.getLogger(__name__)


@dataclass
class CachedDataset:
    loaded_at: datetime
    loaded_monotonic: float
    frames: dict[str, pd.DataFrame]


class DataCache:
    def __init__(self, repository: MatchCentreRepository, ttl_seconds: int) -> None:
        self.repository = repository
        self.ttl_seconds = ttl_seconds
        self.cached: CachedDataset | None = None
        self.last_error: str | None = None
        self.last_refresh_clicks = 0
        self.last_update_clicks = 0
        self.last_update_result: PipelineResult | None = None

    def load(self, force: bool = False) -> CachedDataset:
        now = time.monotonic()
        if self.cached and not force:
            age = now - self.cached.loaded_monotonic
            if age < self.ttl_seconds:
                return self.cached
        try:
            frames = {
                "upcoming": self.repository.upcoming_predictions(),
                "results": self.repository.completed_results(),
                "standings": self.repository.standings(),
                "player_appearances": self.repository.player_appearances(),
                "player_leaderboards": self.repository.player_leaderboards(),
                "player_top10": self.repository.player_top10_by_stat(),
                "model_summary": self.repository.model_summary(),
                "model_performance": self.repository.model_performance(),
                "calibration": self.repository.calibration(),
                "data_quality": self.repository.data_quality(),
                "pipeline_runs": self.repository.pipeline_runs(),
            }
            self.cached = CachedDataset(datetime.now(), now, frames)
            self.last_error = None
            return self.cached
        except Exception as exc:
            self.last_error = safe_error_message(exc)
            LOGGER.exception("Cache refresh failed")
            if self.cached:
                return self.cached
            empty = CachedDataset(
                datetime.now(),
                now,
                {
                    "upcoming": pd.DataFrame(),
                    "results": pd.DataFrame(),
                    "standings": pd.DataFrame(),
                    "player_appearances": pd.DataFrame(),
                    "player_leaderboards": pd.DataFrame(),
                    "player_top10": pd.DataFrame(),
                    "model_summary": pd.DataFrame(),
                    "model_performance": pd.DataFrame(),
                    "calibration": pd.DataFrame(),
                    "data_quality": pd.DataFrame(),
                    "pipeline_runs": pd.DataFrame(),
                },
            )
            self.cached = empty
            return empty


def refresh_label(dataset: CachedDataset, error: str | None = None) -> str:
    label = f"Last refreshed {dataset.loaded_at.strftime('%d %b %Y, %I:%M %p')}"
    return f"{label} - showing cached data after refresh error" if error else label


def create_app(config: AppConfig | None = None, repository: MatchCentreRepository | None = None) -> Dash:
    config = config or AppConfig.from_env()
    repository = repository or MatchCentreRepository(config)
    cache = DataCache(repository, config.cache_ttl_seconds)

    app = Dash(
        __name__,
        suppress_callback_exceptions=True,
        title="BTA Rugby Analytics",
    )
    app.server.config["BTA_CACHE"] = cache

    app.layout = html.Div(
        className="app-shell",
        children=[
            dcc.Location(id="url"),
            html.Header(
                className="app-header",
                children=[
                    html.Div(className="brand", children=[html.Div("BTA", className="brand-mark"), html.Div([html.Strong("BTA Rugby Analytics"), html.Span("Local Match Centre")])]),
                    html.Div(id="nav-container"),
                    html.Div(
                        className="header-actions",
                        children=[
                            html.Button("Update latest data", id="update-data", n_clicks=0, className="secondary-button", title="Run the local SQL data update pipeline"),
                            html.Button("Refresh data", id="refresh-data", n_clicks=0, className="primary-button", title="Clear the app cache and reload SQL Gold views"),
                            html.Span(id="data-update-status", className="data-update-status"),
                        ],
                    ),
                    dbc.Tooltip("Run the configured local update pipeline, then reload the app cache.", target="update-data", placement="bottom"),
                    dbc.Tooltip("Reload SQL Gold view data and refresh the in-memory app cache.", target="refresh-data", placement="bottom"),
                ],
            ),
            dcc.Loading(type="dot", color="#00A6A6", children=html.Div(id="page-content")),
        ],
    )

    @app.callback(Output("nav-container", "children"), Input("url", "pathname"))
    def render_navigation(pathname):
        return navigation(pathname)

    @app.callback(
        Output("page-content", "children"),
        Output("data-update-status", "children"),
        Input("url", "pathname"),
        Input("refresh-data", "n_clicks"),
        Input("update-data", "n_clicks"),
    )
    def render_page(pathname, refresh_clicks, update_clicks):
        refresh_clicks = refresh_clicks or 0
        update_clicks = update_clicks or 0
        force = refresh_clicks > cache.last_refresh_clicks
        if update_clicks > cache.last_update_clicks:
            cache.last_update_clicks = update_clicks
            cache.last_update_result = run_update_pipeline(config)
            force = True
        cache.last_refresh_clicks = refresh_clicks
        dataset = cache.load(force=force)
        error = cache.last_error
        update_status = format_update_result(cache.last_update_result)
        if pathname in (None, "/", ""):
            return (
                match_centre.layout(
                records_from_frame(dataset.frames["upcoming"]),
                refresh_label(dataset, error),
                error,
                ),
                update_status,
            )
        if pathname == "/results":
            return results.layout(records_from_frame(dataset.frames["results"])), update_status
        if pathname == "/table":
            return table.layout(records_from_frame(dataset.frames["standings"])), update_status
        if pathname == "/players":
            return (
                players.layout(
                records_from_frame(dataset.frames["player_appearances"]),
                records_from_frame(dataset.frames["player_leaderboards"]),
                records_from_frame(dataset.frames["player_top10"]),
                ),
                update_status,
            )
        if pathname == "/models":
            return (
                model_performance.layout(
                dataset.frames["model_summary"],
                dataset.frames["model_performance"],
                dataset.frames["calibration"],
                ),
                update_status,
            )
        if pathname == "/pipeline":
            return pipeline_status.layout(dataset.frames["data_quality"], dataset.frames["pipeline_runs"]), update_status
        match = re.fullmatch(r"/match/(\d+)", pathname or "")
        if match:
            match_id = int(match.group(1))
            try:
                upcoming = repository.upcoming_prediction(match_id)
                explanation = repository.match_explanation(match_id)
                return match_preview.layout(match_id, upcoming, explanation), update_status
            except RepositoryError as exc:
                return match_preview.layout(match_id, pd.DataFrame(), pd.DataFrame(), safe_error_message(exc)), update_status
        if (pathname or "").startswith("/match/"):
            return match_preview.layout(None, pd.DataFrame(), pd.DataFrame()), update_status
        return html.Main(className="page", children=[html.Div(className="empty-state", children=[html.H1("Page not found"), html.P("Use the navigation to return to the Match Centre.")])]), update_status

    @app.callback(
        Output("match-centre-content", "children"),
        Output("season-filter", "value"),
        Output("round-filter", "value"),
        Output("date-filter", "start_date"),
        Output("date-filter", "end_date"),
        Output("team-filter", "value"),
        Output("confidence-filter", "value"),
        Input("season-filter", "value"),
        Input("round-filter", "value"),
        Input("date-filter", "start_date"),
        Input("date-filter", "end_date"),
        Input("team-filter", "value"),
        Input("confidence-filter", "value"),
        Input("clear-filters", "n_clicks"),
        State("fixture-records", "data"),
        prevent_initial_call=True,
    )
    def update_match_centre(season, round_name, start_date, end_date, team, confidence, clear_clicks, records):
        if ctx.triggered_id == "clear-filters":
            season = round_name = team = confidence = "All"
            start_date = end_date = None
        content = match_centre.filtered_content(records or [], season, round_name, start_date, end_date, team, confidence)
        return content, season, round_name, start_date, end_date, team, confidence

    @app.callback(
        Output("results-content", "children"),
        Output("results-season-filter", "value"),
        Output("results-round-filter", "value"),
        Output("results-date-filter", "start_date"),
        Output("results-date-filter", "end_date"),
        Output("results-team-filter", "value"),
        Input("results-season-filter", "value"),
        Input("results-round-filter", "value"),
        Input("results-date-filter", "start_date"),
        Input("results-date-filter", "end_date"),
        Input("results-team-filter", "value"),
        Input("results-clear-filters", "n_clicks"),
        State("result-records", "data"),
        prevent_initial_call=True,
    )
    def update_results(season, round_name, start_date, end_date, team, clear_clicks, records):
        if ctx.triggered_id == "results-clear-filters":
            season = round_name = team = "All"
            start_date = end_date = None
        content = results.filtered_content(records or [], season, round_name, start_date, end_date, team)
        return content, season, round_name, start_date, end_date, team

    @app.callback(
        Output("table-content", "children"),
        Input("table-season-filter", "value"),
        State("table-records", "data"),
        prevent_initial_call=True,
    )
    def update_table(season, records):
        return table.table_content(records or [], season)

    @app.callback(
        Output("players-content", "children"),
        Output("players-season-filter", "value"),
        Output("players-team-filter", "value"),
        Output("players-stat-filter", "value"),
        Output("players-name-filter", "value"),
        Input("players-season-filter", "value"),
        Input("players-team-filter", "value"),
        Input("players-stat-filter", "value"),
        Input("players-name-filter", "value"),
        Input("players-clear-filters", "n_clicks"),
        State("player-appearance-records", "data"),
        State("player-leaderboard-records", "data"),
        State("player-top10-records", "data"),
        prevent_initial_call=True,
    )
    def update_players(season, team, stat_name, name, clear_clicks, appearance_records, leaderboard_records, top10_records):
        if ctx.triggered_id == "players-clear-filters":
            season = team = stat_name = "All"
            name = None
        content = players.players_content(appearance_records or [], leaderboard_records or [], top10_records or [], season, team, stat_name, name)
        return content, season, team, stat_name, name

    return app


def main() -> None:
    config = AppConfig.from_env()
    app = create_app(config)
    app.run(host=config.app_host, port=config.app_port, debug=config.app_debug)


if __name__ == "__main__":
    main()
