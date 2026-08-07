"""Fixture card component for Match Centre."""

from __future__ import annotations

from dash import dcc, html

from webapp.components.probability_bar import probability_bar, probability_triplet
from webapp.presentation import fixture_url, format_kickoff, format_margin


def fixture_card(row: dict) -> html.Article:
    model = f"{row.get('ProbabilityModelName') or 'Model'} {row.get('ProbabilityModelVersion') or ''}".strip()
    return html.Article(
        className="fixture-card",
        children=[
            html.Div(
                className="fixture-card__meta",
                children=[
                    html.Span(format_kickoff(row), className="fixture-kickoff"),
                    html.Span(row.get("Round") or "Round TBC"),
                    html.Span(row.get("Venue") or "Venue TBC"),
                ],
            ),
            html.Div(
                className="fixture-card__body",
                children=[
                    html.Div(
                        className="fixture-teams",
                        children=[
                            html.Strong(row.get("HomeTeam") or "Home team TBC"),
                            html.Span("v"),
                            html.Strong(row.get("AwayTeam") or "Away team TBC"),
                        ],
                    ),
                    probability_bar(row),
                    probability_triplet(row),
                ],
            ),
            html.Div(
                className="fixture-card__footer",
                children=[
                    html.Div([html.Span("Predicted winner"), html.Strong(row.get("PredictedWinner") or "Not available")]),
                    html.Div([html.Span("Margin"), html.Strong(format_margin(row))]),
                    html.Div([html.Span("Confidence"), html.Strong(row.get("ConfidenceLevel") or "Not available")]),
                    html.Div([html.Span("Readiness"), html.Strong(row.get("DataQualityStatus") or "Not available")]),
                    html.Div([html.Span("Model"), html.Strong(model)]),
                    dcc.Link("Preview", href=fixture_url(row.get("MatchID")), className="button-link"),
                ],
            ),
        ],
    )
