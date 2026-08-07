"""Competition table page."""

from __future__ import annotations

from dash import dash_table, dcc, html

from webapp.presentation import records_from_frame, rows_from_records


DISPLAY_COLUMNS = [
    ("TeamName", "Team"),
    ("Played", "P"),
    ("Won", "W"),
    ("Drawn", "D"),
    ("Lost", "L"),
    ("PointsFor", "PF"),
    ("PointsAgainst", "PA"),
    ("PointsDifference", "PD"),
    ("TablePoints", "Pts"),
]


def layout(records: list[dict]) -> html.Main:
    rows = rows_from_records(records)
    seasons = sorted([str(value) for value in rows.get("Season", []).dropna().unique()], reverse=True) if not rows.empty else []
    selected = seasons[0] if seasons else "All"
    filtered = rows[rows["Season"].astype(str) == selected] if selected != "All" and not rows.empty else rows
    return html.Main(
        className="page",
        children=[
            html.Div(
                className="page-heading",
                children=[
                    html.Div([html.H1("Table"), html.P("Derived from completed Gold results. Bonus points are not available yet.")]),
                ],
            ),
            html.Div(
                className="filter-bar compact-filter-bar",
                children=[
                    dcc.Dropdown(
                        id="table-season-filter",
                        options=[{"label": season, "value": season} for season in seasons],
                        value=selected if seasons else None,
                        clearable=False,
                        className="filter-control",
                    ),
                ],
            ),
            dcc.Store(id="table-records", data=records),
            html.Div(id="table-content", children=table_content(records, selected)),
        ],
    )


def table_content(records: list[dict], season) -> html.Div:
    rows = rows_from_records(records)
    if rows.empty:
        return html.Div(className="empty-state", children=[html.H2("No table data available"), html.P("Completed score data is required before a table can be calculated.")])
    if season not in (None, "", "All"):
        rows = rows[rows["Season"].astype(str) == str(season)]
    rows = rows.sort_values(["TablePoints", "PointsDifference", "PointsFor", "TeamName"], ascending=[False, False, False, True]).reset_index(drop=True)
    rows.insert(0, "Position", range(1, len(rows) + 1))
    columns = [{"name": "#", "id": "Position"}] + [{"name": label, "id": column} for column, label in DISPLAY_COLUMNS]
    return html.Section(
        className="panel",
        children=[
            html.Div(className="section-kicker", children="Win = 4 points, draw = 2 points. Bonus points are not included."),
            dash_table.DataTable(
                data=records_from_frame(rows[["Position"] + [column for column, _ in DISPLAY_COLUMNS]]),
                columns=columns,
                sort_action="native",
                page_size=20,
                style_table={"overflowX": "auto"},
                style_cell={"fontFamily": "Segoe UI, Arial, sans-serif", "fontSize": "14px", "textAlign": "left"},
                style_header={"fontWeight": "800", "backgroundColor": "#F5F7FA"},
            ),
        ],
    )
