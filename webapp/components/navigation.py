"""Application navigation."""

from __future__ import annotations

from dash import dcc, html


def navigation(pathname: str | None) -> html.Nav:
    links = [
        ("/", "Match Centre"),
        ("/results", "Results"),
        ("/table", "Table"),
        ("/players", "Players"),
        ("/models", "Model Performance"),
        ("/pipeline", "Pipeline Status"),
    ]
    return html.Nav(
        className="app-nav",
        children=[
            dcc.Link(label, href=href, className="active" if pathname == href or (href == "/" and (pathname or "/").startswith("/match/")) else "")
            for href, label in links
        ],
    )
