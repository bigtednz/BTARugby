"""Match Preview page layout."""

from __future__ import annotations

from dash import dcc, html

from webapp.components.probability_bar import probability_bar, probability_triplet
from webapp.presentation import format_datetime, format_kickoff, format_margin, records_from_frame, safe_value


def stat(label: str, value: str) -> html.Div:
    return html.Div([html.Span(label), html.Strong(value)], className="detail-stat")


def layout(match_id: int | None, upcoming, explanation, error: str | None = None) -> html.Main:
    if match_id is None:
        return missing_layout("Missing match ID")
    if error:
        return html.Main(className="page", children=[dcc.Link("Back to Match Centre", href="/", className="back-link"), html.Div(error, className="error-banner")])
    upcoming_records = records_from_frame(upcoming)
    if not upcoming_records:
        return missing_layout(f"Match {match_id} was not found in upcoming production predictions.")
    row = upcoming_records[0]
    explanation_records = records_from_frame(explanation)
    details = explanation_records[0] if explanation_records else {}
    merged = {**row, **details}
    return html.Main(
        className="page",
        children=[
            dcc.Link("Back to Match Centre", href="/", className="back-link"),
            html.Div(
                className="match-hero",
                children=[
                    html.Div([html.Span(format_kickoff(row)), html.H1(f"{row.get('HomeTeam')} v {row.get('AwayTeam')}"), html.P(row.get("Venue") or "Venue TBC")]),
                    html.Div(className="match-badge", children=[html.Span("Predicted"), html.Strong(row.get("PredictedWinner") or "Not available")]),
                ],
            ),
            html.Section(
                className="panel",
                children=[
                    html.H2("Prediction"),
                    probability_bar(row),
                    probability_triplet(row),
                    html.Div(
                        className="detail-grid",
                        children=[
                            stat("Margin", format_margin(row)),
                            stat("Confidence", row.get("ConfidenceLevel") or "Not available"),
                            stat("Probability model", f"{row.get('ProbabilityModelName')} {row.get('ProbabilityModelVersion')}"),
                            stat("Margin model", f"{row.get('MarginModelName')} {row.get('MarginModelVersion')}"),
                            stat("Generated", format_datetime(row.get("PredictionGeneratedAt"), "%d %b %Y, %I:%M %p")),
                            stat("Feature cutoff", format_datetime(row.get("FeatureCutoffDate"), "%d %b %Y")),
                        ],
                    ),
                ],
            ),
            html.Section(
                className="panel",
                children=[
                    html.H2("Elo Inputs"),
                    html.Div(
                        className="detail-grid",
                        children=[
                            stat("Home Elo", safe_value(merged.get("HomePreMatchElo"))),
                            stat("Away Elo", safe_value(merged.get("AwayPreMatchElo"))),
                            stat("Raw Elo difference", safe_value(merged.get("RawEloDifference"))),
                            stat("Home advantage", safe_value(merged.get("HomeAdvantageAdjustment"))),
                            stat("Adjusted Elo difference", safe_value(merged.get("AdjustedEloDifference"))),
                            stat("Probability contribution", safe_value(merged.get("ProbabilityContribution"))),
                        ],
                    ),
                ],
            ),
            html.Section(
                className="panel",
                children=[
                    html.Div(className="section-kicker", children="Context only - not used by the production Elo model"),
                    html.Div(
                        className="detail-grid",
                        children=[
                            stat("Home rolling margin", safe_value(merged.get("ContextHomeRollingMargin"))),
                            stat("Away rolling margin", safe_value(merged.get("ContextAwayRollingMargin"))),
                            stat("Rest days difference", safe_value(merged.get("ContextRestDaysDiff"))),
                            stat("Head-to-head margin", safe_value(merged.get("ContextHeadToHeadMargin"))),
                            stat("Home team sheet", "Available" if row.get("HomeTeamSheetAvailable") else "Not available"),
                            stat("Away team sheet", "Available" if row.get("AwayTeamSheetAvailable") else "Not available"),
                            stat("Home prior matches", safe_value(row.get("HomePriorMatches"))),
                            stat("Away prior matches", safe_value(row.get("AwayPriorMatches"))),
                            stat("Readiness", row.get("DataQualityStatus") or "Not available"),
                        ],
                    ),
                    html.P(details.get("ExplanationSummary") or "", className="explanation-summary"),
                ],
            ),
        ],
    )


def missing_layout(message: str) -> html.Main:
    return html.Main(
        className="page",
        children=[
            dcc.Link("Back to Match Centre", href="/", className="back-link"),
            html.Div(className="empty-state", children=[html.H1("Match preview unavailable"), html.P(message)]),
        ],
    )
