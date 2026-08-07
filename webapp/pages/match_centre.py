"""Match Centre page layout."""

from __future__ import annotations

import pandas as pd
from dash import dcc, html

from webapp.components.fixture_card import fixture_card
from webapp.presentation import (
    average_prediction_confidence,
    filter_fixtures,
    format_datetime,
    format_kickoff,
    format_percent,
    option_values,
    records_from_frame,
    rows_from_records,
    team_options,
)


def filters_layout(rows: pd.DataFrame) -> html.Div:
    date_values = pd.to_datetime(rows.get("MatchDate", pd.Series(dtype=object)), errors="coerce").dropna()
    return html.Div(
        className="filter-bar",
        children=[
            dcc.Dropdown(id="season-filter", options=option_values(rows, "Season"), value="All", clearable=False, className="filter-control"),
            dcc.Dropdown(id="round-filter", options=option_values(rows, "Round"), value="All", clearable=False, className="filter-control"),
            dcc.DatePickerRange(
                id="date-filter",
                min_date_allowed=date_values.min().date() if not date_values.empty else None,
                max_date_allowed=date_values.max().date() if not date_values.empty else None,
                start_date=None,
                end_date=None,
                display_format="D MMM YYYY",
                className="date-control",
            ),
            dcc.Dropdown(id="team-filter", options=team_options(rows), value="All", clearable=False, className="filter-control"),
            dcc.Dropdown(
                id="confidence-filter",
                options=[{"label": "All", "value": "All"}] + [{"label": label, "value": label} for label in ["Low", "Moderate", "High", "Very High"]],
                value="All",
                clearable=False,
                className="filter-control",
            ),
            html.Button("Clear filters", id="clear-filters", n_clicks=0, className="secondary-button"),
        ],
    )


def summary_cards(rows: pd.DataFrame) -> html.Div:
    next_kickoff = "Not available"
    if not rows.empty:
        next_kickoff = format_kickoff(rows.iloc[0].to_dict())
    avg_confidence = average_prediction_confidence(rows)
    high = 0
    if not rows.empty and "ConfidenceLevel" in rows.columns:
        high = int(rows["ConfidenceLevel"].isin(["High", "Very High"]).sum())
    latest = "Not available"
    if not rows.empty and "PredictionGeneratedAt" in rows.columns:
        latest_value = pd.to_datetime(rows["PredictionGeneratedAt"], errors="coerce").max()
        latest = format_datetime(latest_value, "%d %b %Y, %I:%M %p") if not pd.isna(latest_value) else "Not available"
    cards = [
        ("Upcoming fixtures", str(len(rows))),
        ("Next kickoff", next_kickoff),
        ("Average confidence", format_percent(avg_confidence)),
        ("High confidence", str(high)),
        ("Latest generation", latest),
    ]
    return html.Div(className="summary-grid", children=[html.Div([html.Span(label), html.Strong(value)], className="summary-card") for label, value in cards])


def fixture_list(rows: pd.DataFrame) -> html.Div:
    if rows.empty:
        return html.Div(
            className="empty-state",
            children=[
                html.H2("No fixtures match the current filters"),
                html.P("Clear or adjust filters to show upcoming BTA Rugby production predictions."),
            ],
        )
    return html.Div(className="fixture-list", children=[fixture_card(row) for row in records_from_frame(rows)])


def layout(records: list[dict], refresh_label: str | None = None, error: str | None = None) -> html.Main:
    rows = rows_from_records(records)
    return html.Main(
        className="page",
        children=[
            html.Div(
                className="page-heading",
                children=[
                    html.Div([html.H1("Match Centre"), html.P("Read-only production predictions from SQL Gold views.")]),
                    html.Div(className="refresh-status", children=refresh_label or "Not refreshed"),
                ],
            ),
            html.Div(error, className="error-banner") if error else None,
            filters_layout(rows),
            dcc.Store(id="fixture-records", data=records),
            html.Div(id="match-centre-content", children=[summary_cards(rows), fixture_list(rows)]),
        ],
    )


def filtered_content(records, season, round_name, start_date, end_date, team, confidence):
    rows = filter_fixtures(rows_from_records(records), season, round_name, start_date, end_date, team, confidence)
    return [summary_cards(rows), fixture_list(rows)]
