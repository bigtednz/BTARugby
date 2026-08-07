"""Probability display components."""

from __future__ import annotations

from dash import html

from webapp.presentation import format_percent


def _width(value) -> str:
    try:
        return f"{max(0.0, min(1.0, float(value))) * 100:.1f}%"
    except (TypeError, ValueError):
        return "0%"


def probability_bar(row: dict) -> html.Div:
    items = [
        ("Home", row.get("HomeWinProbability"), "home"),
        ("Draw", row.get("DrawProbability"), "draw"),
        ("Away", row.get("AwayWinProbability"), "away"),
    ]
    return html.Div(
        className="probability-stack",
        children=[
            html.Div(
                className=f"probability-segment probability-{name}",
                style={"width": _width(value)},
                title=f"{label}: {format_percent(value)}",
                children=html.Span(format_percent(value)),
            )
            for label, value, name in items
        ],
    )


def probability_triplet(row: dict) -> html.Div:
    return html.Div(
        className="probability-triplet",
        children=[
            html.Div([html.Span("Home"), html.Strong(format_percent(row.get("HomeWinProbability")))]),
            html.Div([html.Span("Draw"), html.Strong(format_percent(row.get("DrawProbability")))]),
            html.Div([html.Span("Away"), html.Strong(format_percent(row.get("AwayWinProbability")))]),
        ],
    )
