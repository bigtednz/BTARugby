"""Model Performance foundation page."""

from __future__ import annotations

from dash import dash_table, html

from webapp.presentation import records_from_frame


def layout(model_summary, performance, calibration) -> html.Main:
    return html.Main(
        className="page",
        children=[
            html.Div(className="page-heading", children=[html.Div([html.H1("Model Performance"), html.P("Champion registry, evaluation metrics, and calibration from Gold views.")])]),
            html.Section(className="panel", children=[html.H2("Champion Registry"), table(model_summary)]),
            html.Section(className="panel", children=[html.H2("Performance Comparison"), table(performance)]),
            html.Section(className="panel", children=[html.H2("Calibration"), table(calibration)]),
        ],
    )


def table(frame):
    records = records_from_frame(frame)
    columns = [{"name": column, "id": column} for column in frame.columns]
    if not records:
        return html.Div("No rows available.", className="empty-inline")
    return dash_table.DataTable(
        data=records,
        columns=columns,
        page_size=10,
        sort_action="native",
        filter_action="native",
        style_table={"overflowX": "auto"},
        style_cell={"fontFamily": "Segoe UI, Arial, sans-serif", "fontSize": "13px", "textAlign": "left"},
    )
