"""Pipeline Status foundation page."""

from __future__ import annotations

from dash import dash_table, html

from webapp.presentation import records_from_frame


def layout(data_quality, pipeline_runs) -> html.Main:
    critical = int((data_quality.get("Severity") == "Critical").sum()) if "Severity" in data_quality.columns else 0
    warnings = int((data_quality.get("Severity") == "Warning").sum()) if "Severity" in data_quality.columns else 0
    errors = int(pipeline_runs.get("ErrorCount", []).sum()) if "ErrorCount" in pipeline_runs.columns else 0
    return html.Main(
        className="page",
        children=[
            html.Div(className="page-heading", children=[html.Div([html.H1("Pipeline Status"), html.P("Read-only production data-quality and run status.")])]),
            html.Div(
                className="summary-grid",
                children=[
                    html.Div([html.Span("Critical issues"), html.Strong(str(critical))], className="summary-card"),
                    html.Div([html.Span("Warnings"), html.Strong(str(warnings))], className="summary-card"),
                    html.Div([html.Span("Pipeline errors"), html.Strong(str(errors))], className="summary-card"),
                ],
            ),
            html.Section(className="panel", children=[html.H2("Data Quality"), table(data_quality)]),
            html.Section(className="panel", children=[html.H2("Pipeline Runs"), table(pipeline_runs)]),
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
