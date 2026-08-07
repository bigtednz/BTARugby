"""Completed Results page layout."""

from __future__ import annotations

import pandas as pd
from dash import dcc, html

from webapp.presentation import (
    filter_fixtures,
    format_datetime,
    format_result,
    format_result_winner,
    format_prediction_comparison,
    option_values,
    records_from_frame,
    rows_from_records,
    team_options,
)


def _missing(value) -> bool:
    return value is None or str(value).strip().lower() in {"", "nan", "none", "nat", "<na>", "null"}


def filters_layout(rows: pd.DataFrame) -> html.Div:
    date_values = pd.to_datetime(rows.get("MatchDate", pd.Series(dtype=object)), errors="coerce").dropna()
    return html.Div(
        className="filter-bar results-filter-bar",
        children=[
            dcc.Dropdown(id="results-season-filter", options=option_values(rows, "Season"), value="All", clearable=False, className="filter-control"),
            dcc.Dropdown(id="results-round-filter", options=option_values(rows, "Round"), value="All", clearable=False, className="filter-control"),
            dcc.DatePickerRange(
                id="results-date-filter",
                min_date_allowed=date_values.min().date() if not date_values.empty else None,
                max_date_allowed=date_values.max().date() if not date_values.empty else None,
                start_date=None,
                end_date=None,
                display_format="D MMM YYYY",
                className="date-control",
            ),
            dcc.Dropdown(id="results-team-filter", options=team_options(rows), value="All", clearable=False, className="filter-control"),
            html.Button("Clear filters", id="results-clear-filters", n_clicks=0, className="secondary-button"),
        ],
    )


def summary_cards(rows: pd.DataFrame) -> html.Div:
    latest = "Not available"
    if not rows.empty:
        latest = format_datetime(pd.to_datetime(rows["MatchDate"], errors="coerce").max(), "%d %b %Y")
    result_ready = int(rows.get("ResultReadyFlag", pd.Series(dtype=object)).fillna(0).astype(bool).sum()) if "ResultReadyFlag" in rows.columns else 0
    production_available = int(rows.get("PredictionAvailableFlag", pd.Series(dtype=object)).fillna(0).astype(bool).sum()) if "PredictionAvailableFlag" in rows.columns else 0
    production_eligible = int(rows.get("ProductionEvaluationEligibleFlag", pd.Series(dtype=object)).fillna(0).astype(bool).sum()) if "ProductionEvaluationEligibleFlag" in rows.columns else 0
    return html.Div(
        className="summary-grid result-summary-grid",
        children=[
            html.Div([html.Span("Completed matches"), html.Strong(str(len(rows)))], className="summary-card"),
            html.Div([html.Span("Result ready"), html.Strong(str(result_ready))], className="summary-card"),
            html.Div([html.Span("Prediction available"), html.Strong(str(production_available))], className="summary-card"),
            html.Div([html.Span("Production evaluable"), html.Strong(str(production_eligible))], className="summary-card"),
            html.Div([html.Span("Latest result date"), html.Strong(latest)], className="summary-card"),
        ],
    )


def result_card(row: dict) -> html.Article:
    return html.Article(
        className="fixture-card result-card",
        children=[
            html.Div(
                className="fixture-card__meta",
                children=[
                    html.Span(format_datetime(row.get("MatchDate"), "%a %d %b %Y"), className="fixture-kickoff"),
                    html.Span(row.get("Round") or "Round TBC"),
                    html.Span(row.get("CompetitionCode") or "Competition TBC"),
                    html.Span(row.get("ScoreStatus") or "Score status TBC"),
                ],
            ),
            html.Div(
                className="result-card__body",
                children=[
                    html.Div(className="fixture-teams", children=[html.Strong(row.get("HomeTeam") or "Home team TBC"), html.Span("v"), html.Strong(row.get("AwayTeam") or "Away team TBC")]),
                    html.Div(className="result-score", children=format_result(row)),
                    html.Div(className="result-winner", children=format_result_winner(row)),
                ],
            ),
            html.Div(
                className="result-comparison",
                children=[
                    html.Div([html.Span("Prediction"), html.Strong(format_prediction_comparison(row))]),
                    html.Div([html.Span("Model"), html.Strong(row.get("PredictionModel") or "Not available")]),
                    html.Div([html.Span("Margin error"), html.Strong("Not available" if _missing(row.get("AbsoluteMarginError")) else f"{float(row.get('AbsoluteMarginError')):.1f}")]),
                    html.Div([html.Span("Production eval"), html.Strong(row.get("EvaluationStatus") or "Not available")]),
                ],
            ),
        ],
    )


def result_list(rows: pd.DataFrame) -> html.Div:
    if rows.empty:
        return html.Div(
            className="empty-state",
            children=[
                html.H2("No results match the current filters"),
                html.P("Clear or adjust filters to show completed NPC results."),
            ],
        )
    return html.Div(className="fixture-list", children=[result_card(row) for row in records_from_frame(rows)])


def layout(records: list[dict]) -> html.Main:
    rows = rows_from_records(records)
    return html.Main(
        className="page",
        children=[
            html.Div(className="page-heading", children=[html.Div([html.H1("Results"), html.P("Result readiness, retained production predictions and production-evaluation eligibility from SQL Gold views.")])]),
            filters_layout(rows),
            dcc.Store(id="result-records", data=records),
            html.Div(id="results-content", children=[summary_cards(rows), result_list(rows)]),
        ],
    )


def filtered_content(records, season, round_name, start_date, end_date, team):
    rows = filter_fixtures(rows_from_records(records), season, round_name, start_date, end_date, team, confidence=None)
    return [summary_cards(rows), result_list(rows)]
