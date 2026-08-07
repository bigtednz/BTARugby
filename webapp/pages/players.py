"""Players page."""

from __future__ import annotations

import pandas as pd
from dash import dash_table, dcc, html
import plotly.express as px

from webapp.presentation import option_values, records_from_frame, rows_from_records, team_options


APPEARANCE_COLUMNS = [
    ("Season", "Season"),
    ("MatchDate", "Date"),
    ("Round", "Round"),
    ("TeamName", "Team"),
    ("PlayerName", "Player"),
    ("JerseyNumber", "#"),
    ("Role", "Role"),
    ("SubOnMinute", "On"),
    ("SubOffMinute", "Off"),
]

LEADERBOARD_COLUMNS = [
    ("Season", "Season"),
    ("MatchID", "Match"),
    ("Team", "Team"),
    ("PlayerName", "Player"),
    ("StatName", "Stat"),
    ("Rank", "Rank"),
    ("StatValueRaw", "Value"),
]


TOP10_COLUMNS = [
    ("Discipline", "Discipline"),
    ("CalculatedRank", "Rank"),
    ("Team", "Team"),
    ("PlayerName", "Player"),
    ("SeasonTotal", "Total"),
    ("Appearances", "Appearances"),
    ("PerAppearance", "Per appearance"),
]


def layout(appearance_records: list[dict], leaderboard_records: list[dict], top10_records: list[dict]) -> html.Main:
    appearances = rows_from_records(appearance_records)
    leaderboards = rows_from_records(leaderboard_records)
    top10 = rows_from_records(top10_records)
    seasons = option_values(appearances, "Season")
    teams = team_options(appearances.rename(columns={"TeamName": "HomeTeam"})) if not appearances.empty else [{"label": "All", "value": "All"}]
    stat_options = option_values(top10.rename(columns={"Discipline": "StatName"}), "StatName")
    return html.Main(
        className="page",
        children=[
            html.Div(className="page-heading", children=[html.Div([html.H1("Players"), html.P("Team sheets and dense-ranked top 10 season totals by discipline.")])]),
            html.Div(
                className="filter-bar players-filter-bar",
                children=[
                    dcc.Dropdown(id="players-season-filter", options=seasons, value="All", clearable=False, className="filter-control"),
                    dcc.Dropdown(id="players-team-filter", options=teams, value="All", clearable=False, className="filter-control"),
                    dcc.Dropdown(id="players-stat-filter", options=stat_options, value="All", clearable=False, className="filter-control"),
                    dcc.Input(id="players-name-filter", type="text", debounce=True, placeholder="Search player", className="text-filter"),
                    html.Button("Clear filters", id="players-clear-filters", n_clicks=0, className="secondary-button"),
                ],
            ),
            dcc.Store(id="player-appearance-records", data=appearance_records),
            dcc.Store(id="player-leaderboard-records", data=leaderboard_records),
            dcc.Store(id="player-top10-records", data=top10_records),
            html.Div(id="players-content", children=players_content(appearance_records, leaderboard_records, top10_records, "All", "All", "All", None)),
        ],
    )


def _filter_appearances(rows: pd.DataFrame, season, team, name) -> pd.DataFrame:
    if rows.empty:
        return rows
    filtered = rows.copy()
    if season not in (None, "", "All"):
        filtered = filtered[filtered["Season"].astype(str) == str(season)]
    if team not in (None, "", "All"):
        filtered = filtered[filtered["TeamName"].astype(str) == str(team)]
    if name:
        filtered = filtered[filtered["PlayerName"].astype(str).str.contains(str(name), case=False, na=False)]
    return filtered


def _filter_leaderboards(rows: pd.DataFrame, season, team, stat_name, name) -> pd.DataFrame:
    if rows.empty:
        return rows
    filtered = rows.copy()
    if season not in (None, "", "All"):
        filtered = filtered[filtered["Season"].astype(str) == str(season)]
    if team not in (None, "", "All"):
        filtered = filtered[filtered["Team"].astype(str) == str(team)]
    if stat_name not in (None, "", "All") and "StatName" in filtered.columns:
        filtered = filtered[filtered["StatName"].astype(str) == str(stat_name)]
    if name:
        filtered = filtered[filtered["PlayerName"].astype(str).str.contains(str(name), case=False, na=False)]
    return filtered


def _filter_top10(rows: pd.DataFrame, season, team, stat_name, name) -> pd.DataFrame:
    if rows.empty:
        return rows
    filtered = rows.copy()
    if season not in (None, "", "All"):
        filtered = filtered[filtered["Season"].astype(str) == str(season)]
    if team not in (None, "", "All"):
        filtered = filtered[filtered["Team"].astype(str) == str(team)]
    if stat_name not in (None, "", "All"):
        filtered = filtered[filtered["Discipline"].astype(str) == str(stat_name)]
    if name:
        filtered = filtered[filtered["PlayerName"].astype(str).str.contains(str(name), case=False, na=False)]
    return filtered


def players_content(appearance_records, leaderboard_records, top10_records, season, team, stat_name, name) -> list:
    appearances = _filter_appearances(rows_from_records(appearance_records), season, team, name)
    leaderboards = _filter_leaderboards(rows_from_records(leaderboard_records), season, team, stat_name, name)
    top10 = _filter_top10(rows_from_records(top10_records), season, team, stat_name, name)
    return [
        html.Div(
            className="summary-grid result-summary-grid",
            children=[
                html.Div([html.Span("Appearances"), html.Strong(str(len(appearances)))], className="summary-card"),
                html.Div([html.Span("Disciplines"), html.Strong(str(top10["Discipline"].nunique() if "Discipline" in top10.columns else 0))], className="summary-card"),
                html.Div([html.Span("Top-10 entries"), html.Strong(str(len(top10)))], className="summary-card"),
            ],
        ),
        html.Section(className="panel", children=[html.H2("Top 10 by Discipline"), html.Div(className="section-kicker", children="Dense rank by season total; tied players remain in the top 10."), top10_tables(top10)]),
        html.Section(className="panel", children=[html.H2("Team Sheets"), table(appearances, APPEARANCE_COLUMNS)]),
    ]


def top10_tables(frame: pd.DataFrame):
    if frame.empty:
        return html.Div("No top-10 rows match the current filters.", className="empty-inline")
    sections = []
    for stat_name, stat_rows in frame.groupby("Discipline", sort=True):
        stat_rows = stat_rows.sort_values(["CalculatedRank", "PlayerName"])
        sections.append(
            html.Div(
                className="top10-section",
                children=[
                    html.H3(str(stat_name)),
                    top10_chart(stat_rows, str(stat_name)),
                    table(stat_rows, TOP10_COLUMNS),
                ],
            )
        )
    return html.Div(className="top10-grid", children=sections)


def top10_chart(frame: pd.DataFrame, discipline: str):
    if frame.empty:
        return None
    chart_frame = frame.sort_values(["SeasonTotal", "PlayerName"], ascending=[True, True]).tail(10)
    fig = px.bar(
        chart_frame,
        x="SeasonTotal",
        y="PlayerName",
        color="Team",
        orientation="h",
        text="SeasonTotal",
        labels={"SeasonTotal": "Total", "PlayerName": "Player"},
    )
    fig.update_layout(
        title=None,
        height=max(260, 26 * len(chart_frame) + 80),
        margin={"l": 8, "r": 8, "t": 8, "b": 28},
        font={"family": "Segoe UI, Arial, sans-serif", "size": 12},
        legend_title_text="Team",
    )
    fig.update_traces(texttemplate="%{text:.0f}", textposition="outside", cliponaxis=False)
    return html.Div(
        dcc.Graph(
            figure=fig,
            config={"displayModeBar": False, "responsive": True},
            className="top10-chart",
        ),
        role="img",
        **{"aria-label": f"Top 10 {discipline} season totals"},
    )


def table(frame: pd.DataFrame, columns: list[tuple[str, str]]):
    available = [column for column, _ in columns if column in frame.columns]
    if frame.empty or not available:
        return html.Div("No player rows match the current filters.", className="empty-inline")
    table_frame = frame[available].head(250)
    return dash_table.DataTable(
        data=records_from_frame(table_frame),
        columns=[{"name": label, "id": column} for column, label in columns if column in available],
        page_size=20,
        sort_action="native",
        filter_action="native",
        style_table={"overflowX": "auto"},
        style_cell={"fontFamily": "Segoe UI, Arial, sans-serif", "fontSize": "13px", "textAlign": "left"},
        style_header={"fontWeight": "800", "backgroundColor": "#F5F7FA"},
    )
