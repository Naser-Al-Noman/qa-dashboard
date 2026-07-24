"""
Plotly chart builders for the QA Analytics Dashboard.

Color scheme (status):
  pass=green, fail=red, skip=gray, blocked=orange
"""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# ---------------------------------------------------------------------------
# Shared palette
# ---------------------------------------------------------------------------

STATUS_COLORS: dict[str, str] = {
    "pass": "#2e7d32",      # green
    "fail": "#c62828",      # red
    "skip": "#9e9e9e",      # gray
    "blocked": "#ef6c00",   # orange
}

DEFECT_STATUS_COLORS: dict[str, str] = {
    "open": "#c62828",
    "in-progress": "#ef6c00",
    "closed": "#2e7d32",
}

SEVERITY_COLORS: dict[str, str] = {
    "critical": "#b71c1c",
    "high": "#e53935",
    "medium": "#fb8c00",
    "low": "#9e9e9e",
}

SEVERITY_ORDER = ["critical", "high", "medium", "low"]
PRIORITY_ORDER = ["P0", "P1", "P2", "P3"]

_LAYOUT_DEFAULTS = dict(
    height=400,
    margin=dict(l=40, r=30, t=55, b=40),
    hovermode="closest",
    plot_bgcolor="rgba(0,0,0,0)",
    paper_bgcolor="rgba(0,0,0,0)",
    font=dict(family="Source Sans Pro, sans-serif", size=13),
)


def _empty_fig(message: str = "No data for the current filters") -> go.Figure:
    """Placeholder figure when a chart has nothing to render."""
    fig = go.Figure()
    fig.add_annotation(
        text=message,
        xref="paper",
        yref="paper",
        x=0.5,
        y=0.5,
        showarrow=False,
        font=dict(size=14, color="#666"),
    )
    fig.update_layout(
        xaxis=dict(visible=False),
        yaxis=dict(visible=False),
        **_LAYOUT_DEFAULTS,
    )
    return fig


def _apply_layout(fig: go.Figure, **overrides) -> go.Figure:
    """Apply shared layout + optional overrides; keep tooltips interactive."""
    layout = {**_LAYOUT_DEFAULTS, **overrides}
    fig.update_layout(**layout)
    fig.update_xaxes(showgrid=True, gridcolor="rgba(0,0,0,0.06)")
    fig.update_yaxes(showgrid=True, gridcolor="rgba(0,0,0,0.06)")
    return fig


# ---------------------------------------------------------------------------
# Requested chart functions
# ---------------------------------------------------------------------------

def pass_fail_trend_chart(trend_df: pd.DataFrame) -> go.Figure:
    """
    Interactive stacked area of pass / fail / skip / blocked counts over time.

    Expects the output of ``calculate_execution_trends`` (columns: ``date``,
    ``pass``, ``fail``, ``skip``, and optionally ``blocked``).
    """
    if trend_df is None or trend_df.empty or "date" not in trend_df.columns:
        return _empty_fig("No execution trend data")

    value_vars = [c for c in ["pass", "fail", "skip", "blocked"] if c in trend_df.columns]
    if not value_vars:
        return _empty_fig("Trend data has no status columns")

    melted = trend_df.melt(
        id_vars=["date"],
        value_vars=value_vars,
        var_name="status",
        value_name="count",
    )

    fig = px.area(
        melted,
        x="date",
        y="count",
        color="status",
        title="Pass / fail / skip trend",
        color_discrete_map=STATUS_COLORS,
        category_orders={"status": ["pass", "fail", "skip", "blocked"]},
        hover_data={"count": True, "status": True, "date": "|%Y-%m-%d"},
    )
    fig.update_traces(
        hovertemplate="<b>%{fullData.name}</b><br>Date=%{x|%Y-%m-%d}<br>Count=%{y}<extra></extra>",
        line=dict(width=0.5),
    )
    return _apply_layout(
        fig,
        xaxis_title="Date",
        yaxis_title="Executions",
        legend_title_text="Status",
    )


def defect_severity_donut(defects_df: pd.DataFrame) -> go.Figure:
    """
    Donut chart of defect counts by severity.

    Accepts a raw defects DataFrame with a ``severity`` column.
    """
    if defects_df is None or defects_df.empty or "severity" not in defects_df.columns:
        return _empty_fig("No defect severity data")

    counts = (
        defects_df["severity"]
        .astype(str)
        .str.strip()
        .str.lower()
        .value_counts()
        .reindex(SEVERITY_ORDER)
        .dropna()
        .astype(int)
        .reset_index()
    )
    counts.columns = ["severity", "count"]
    if counts.empty:
        return _empty_fig("No defect severity data")

    fig = go.Figure(
        data=[
            go.Pie(
                labels=counts["severity"],
                values=counts["count"],
                hole=0.55,
                marker=dict(
                    colors=[SEVERITY_COLORS.get(s, "#90a4ae") for s in counts["severity"]],
                    line=dict(color="#ffffff", width=2),
                ),
                hovertemplate="<b>%{label}</b><br>Count=%{value}<br>Share=%{percent}<extra></extra>",
                textinfo="label+percent",
                textposition="outside",
            )
        ]
    )
    return _apply_layout(
        fig,
        title="Defects by severity",
        showlegend=True,
        legend_title_text="Severity",
        height=420,
    )


def defect_burnup_chart(defects_df: pd.DataFrame) -> go.Figure:
    """
    Burn-up style chart: cumulative defects opened vs closed over time.

    Uses ``created_date`` for openings and ``closed_date`` for closures.
    Open backlog at any point is implied by the gap between the two curves.
    """
    if defects_df is None or defects_df.empty or "created_date" not in defects_df.columns:
        return _empty_fig("No defect burn-up data")

    work = defects_df.copy()
    work["created_date"] = pd.to_datetime(work["created_date"], errors="coerce")
    opened = (
        work.dropna(subset=["created_date"])
        .assign(date=lambda d: d["created_date"].dt.normalize())
        .groupby("date")
        .size()
        .rename("opened")
        .sort_index()
    )

    if "closed_date" in work.columns:
        work["closed_date"] = pd.to_datetime(work["closed_date"], errors="coerce")
        closed = (
            work.dropna(subset=["closed_date"])
            .assign(date=lambda d: d["closed_date"].dt.normalize())
            .groupby("date")
            .size()
            .rename("closed")
            .sort_index()
        )
    else:
        closed = pd.Series(dtype=int, name="closed")

    if opened.empty and closed.empty:
        return _empty_fig("No defect burn-up data")

    timeline = pd.concat([opened, closed], axis=1).fillna(0).astype(int).sort_index()
    timeline["cum_opened"] = timeline.get("opened", 0).cumsum()
    timeline["cum_closed"] = timeline.get("closed", 0).cumsum()
    timeline = timeline.reset_index().rename(columns={"index": "date"})
    if "date" not in timeline.columns:
        timeline = timeline.rename(columns={timeline.columns[0]: "date"})

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=timeline["date"],
            y=timeline["cum_opened"],
            mode="lines+markers",
            name="Cumulative opened",
            line=dict(color=STATUS_COLORS["fail"], width=2.5),
            marker=dict(size=6),
            hovertemplate="Opened to date: <b>%{y}</b><br>%{x|%Y-%m-%d}<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=timeline["date"],
            y=timeline["cum_closed"],
            mode="lines+markers",
            name="Cumulative closed",
            line=dict(color=STATUS_COLORS["pass"], width=2.5),
            marker=dict(size=6),
            hovertemplate="Closed to date: <b>%{y}</b><br>%{x|%Y-%m-%d}<extra></extra>",
        )
    )
    # Fill gap to emphasize remaining open work
    fig.add_trace(
        go.Scatter(
            x=list(timeline["date"]) + list(timeline["date"][::-1]),
            y=list(timeline["cum_opened"]) + list(timeline["cum_closed"][::-1]),
            fill="toself",
            fillcolor="rgba(198, 40, 40, 0.08)",
            line=dict(color="rgba(0,0,0,0)"),
            hoverinfo="skip",
            showlegend=True,
            name="Open backlog",
        )
    )
    return _apply_layout(
        fig,
        title="Defect burn-up (opened vs closed)",
        xaxis_title="Date",
        yaxis_title="Cumulative defects",
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        hovermode="x unified",
    )


def browser_pass_rate_heatmap(df: pd.DataFrame) -> go.Figure:
    """
    Heatmap of pass rate (%) with ``test_suite`` on Y and ``browser`` on X.

    Pass rate = passes / all runs in that suite×browser cell.
    """
    required = {"test_suite", "browser", "status"}
    if df is None or df.empty or not required.issubset(df.columns):
        return _empty_fig("No suite × browser data")

    work = df.copy()
    work["status"] = work["status"].astype(str).str.strip().str.lower()

    grouped = (
        work.groupby(["test_suite", "browser"], dropna=False)
        .agg(
            runs=("status", "size"),
            passes=("status", lambda s: int((s == "pass").sum())),
        )
        .reset_index()
    )
    grouped["pass_rate"] = grouped.apply(
        lambda r: round(100.0 * r["passes"] / r["runs"], 2) if r["runs"] else 0.0,
        axis=1,
    )

    pivot = grouped.pivot(index="test_suite", columns="browser", values="pass_rate")
    runs_pivot = grouped.pivot(index="test_suite", columns="browser", values="runs")

    if pivot.empty:
        return _empty_fig("No suite × browser data")

    # Customdata carries run counts for richer hover tooltips
    custom = runs_pivot.reindex(index=pivot.index, columns=pivot.columns).fillna(0).values

    fig = go.Figure(
        data=go.Heatmap(
            z=pivot.values,
            x=list(pivot.columns),
            y=list(pivot.index),
            colorscale=[
                [0.0, STATUS_COLORS["fail"]],
                [0.5, "#fff59d"],
                [1.0, STATUS_COLORS["pass"]],
            ],
            zmin=0,
            zmax=100,
            colorbar=dict(title="Pass %"),
            customdata=custom,
            hovertemplate=(
                "Suite=<b>%{y}</b><br>"
                "Browser=<b>%{x}</b><br>"
                "Pass rate=<b>%{z:.1f}%</b><br>"
                "Runs=%{customdata:.0f}"
                "<extra></extra>"
            ),
        )
    )
    return _apply_layout(
        fig,
        title="Pass rate by test suite × browser",
        xaxis_title="Browser",
        yaxis_title="Test suite",
        height=max(380, 48 * len(pivot.index) + 120),
    )


def pareto_chart(failing_modules_df: pd.DataFrame) -> go.Figure:
    """
    Pareto chart of failing modules: failure bars + cumulative % line.

    Expects output from ``get_top_failing_modules`` with columns
    ``module``, ``failures``, and preferably ``cumulative_pct``.
    """
    if failing_modules_df is None or failing_modules_df.empty:
        return _empty_fig("No failing module data")

    work = failing_modules_df.copy()
    if "module" not in work.columns or "failures" not in work.columns:
        return _empty_fig("Pareto data needs module and failures columns")

    work = work.sort_values("failures", ascending=False).reset_index(drop=True)
    if "cumulative_pct" not in work.columns:
        total = work["failures"].sum()
        work["cumulative_pct"] = (
            (100.0 * work["failures"].cumsum() / total).round(2) if total else 0.0
        )

    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(
        go.Bar(
            x=work["module"],
            y=work["failures"],
            name="Failures",
            marker_color=STATUS_COLORS["fail"],
            hovertemplate="Module=<b>%{x}</b><br>Failures=<b>%{y}</b><extra></extra>",
        ),
        secondary_y=False,
    )
    fig.add_trace(
        go.Scatter(
            x=work["module"],
            y=work["cumulative_pct"],
            name="Cumulative %",
            mode="lines+markers",
            line=dict(color=STATUS_COLORS["blocked"], width=2.5),
            marker=dict(size=7, color=STATUS_COLORS["blocked"]),
            hovertemplate="Module=<b>%{x}</b><br>Cumulative=<b>%{y:.1f}%</b><extra></extra>",
        ),
        secondary_y=True,
    )
    fig.update_yaxes(title_text="Failure count", secondary_y=False)
    fig.update_yaxes(title_text="Cumulative %", range=[0, 105], secondary_y=True)
    return _apply_layout(
        fig,
        title="Pareto — top failing modules",
        xaxis_title="Module / suite",
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        height=420,
    )


# ---------------------------------------------------------------------------
# Legacy helpers still used by Streamlit pages
# ---------------------------------------------------------------------------

def status_pie(df: pd.DataFrame, title: str = "Status breakdown") -> go.Figure:
    if df is None or df.empty:
        return _empty_fig()
    work = df.copy()
    work["status"] = work["status"].astype(str).str.lower()
    color_map = {**STATUS_COLORS, **DEFECT_STATUS_COLORS}
    fig = px.pie(
        work,
        names="status",
        values="count",
        title=title,
        color="status",
        color_discrete_map=color_map,
        hole=0.45,
    )
    fig.update_traces(
        textposition="inside",
        textinfo="percent+label",
        hovertemplate="<b>%{label}</b><br>Count=%{value}<br>Share=%{percent}<extra></extra>",
    )
    return _apply_layout(fig, height=380)


def bar_breakdown(
    df: pd.DataFrame,
    x: str,
    y: str = "count",
    title: str = "",
    color: str | None = None,
    category_orders: dict | None = None,
) -> go.Figure:
    if df is None or df.empty:
        return _empty_fig()
    fig = px.bar(
        df,
        x=x,
        y=y,
        title=title,
        color=color or x,
        category_orders=category_orders,
        text=y,
    )
    fig.update_traces(
        textposition="outside",
        hovertemplate=f"<b>%{{x}}</b><br>{y}=%{{y}}<extra></extra>",
    )
    return _apply_layout(
        fig,
        showlegend=False,
        xaxis_title=x.replace("_", " ").title(),
        yaxis_title=y.replace("_", " ").title(),
        height=380,
    )


def stacked_status_over_time(
    df: pd.DataFrame, title: str = "Executions over time"
) -> go.Figure:
    """Backward-compatible wrapper around ``pass_fail_trend_chart``."""
    fig = pass_fail_trend_chart(df)
    if title:
        fig.update_layout(title=title)
    return fig


def line_pass_rate(df: pd.DataFrame, title: str = "Pass rate over time") -> go.Figure:
    if df is None or df.empty:
        return _empty_fig()
    fig = px.line(df, x="date", y="pass_rate", markers=True, title=title)
    fig.update_traces(
        line_color=STATUS_COLORS["pass"],
        hovertemplate="Date=%{x|%Y-%m-%d}<br>Pass rate=<b>%{y:.1f}%</b><extra></extra>",
    )
    return _apply_layout(
        fig,
        yaxis_title="Pass rate (%)",
        yaxis=dict(range=[0, 100]),
        height=380,
    )


def line_duration(
    df: pd.DataFrame, title: str = "Average duration over time"
) -> go.Figure:
    if df is None or df.empty:
        return _empty_fig()
    fig = px.line(df, x="date", y="avg_duration_sec", markers=True, title=title)
    fig.update_traces(
        line_color=STATUS_COLORS["blocked"],
        hovertemplate="Date=%{x|%Y-%m-%d}<br>Avg duration=<b>%{y:.2f}s</b><extra></extra>",
    )
    return _apply_layout(fig, yaxis_title="Avg duration (sec)", height=380)


def severity_bar(df: pd.DataFrame, title: str = "Defects by severity") -> go.Figure:
    if df is None or df.empty:
        return _empty_fig()
    # Prefer donut when raw defects are passed; this helper still supports counts
    if "count" not in df.columns and "severity" in df.columns:
        return defect_severity_donut(df)
    ordered = df.copy()
    ordered["severity"] = pd.Categorical(
        ordered["severity"], categories=SEVERITY_ORDER, ordered=True
    )
    ordered = ordered.sort_values("severity")
    fig = px.bar(
        ordered,
        x="severity",
        y="count",
        title=title,
        color="severity",
        color_discrete_map=SEVERITY_COLORS,
        category_orders={"severity": SEVERITY_ORDER},
        text="count",
    )
    fig.update_traces(
        textposition="outside",
        hovertemplate="Severity=<b>%{x}</b><br>Count=%{y}<extra></extra>",
    )
    return _apply_layout(fig, showlegend=False, height=380)


def priority_bar(df: pd.DataFrame, title: str = "Defects by priority") -> go.Figure:
    if df is None or df.empty:
        return _empty_fig()
    ordered = df.copy()
    ordered["priority"] = pd.Categorical(
        ordered["priority"], categories=PRIORITY_ORDER, ordered=True
    )
    ordered = ordered.sort_values("priority")
    return bar_breakdown(
        ordered,
        x="priority",
        title=title,
        category_orders={"priority": PRIORITY_ORDER},
    )


def defects_trend(df: pd.DataFrame, title: str = "Defects created vs closed") -> go.Figure:
    """Daily created vs closed counts (non-cumulative). Prefer burn-up for backlog view."""
    if df is None or df.empty:
        return _empty_fig()
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=df["date"],
            y=df["created"],
            mode="lines+markers",
            name="Created",
            line=dict(color=STATUS_COLORS["fail"]),
            hovertemplate="Created=<b>%{y}</b><br>%{x|%Y-%m-%d}<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=df["date"],
            y=df["closed"],
            mode="lines+markers",
            name="Closed",
            line=dict(color=STATUS_COLORS["pass"]),
            hovertemplate="Closed=<b>%{y}</b><br>%{x|%Y-%m-%d}<extra></extra>",
        )
    )
    return _apply_layout(
        fig,
        title=title,
        yaxis_title="Count",
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        hovermode="x unified",
    )


def suite_duration_bar(
    df: pd.DataFrame, title: str = "Avg duration by suite"
) -> go.Figure:
    if df is None or df.empty:
        return _empty_fig()
    fig = px.bar(
        df,
        x="avg_duration_sec",
        y="test_suite",
        orientation="h",
        title=title,
        text="avg_duration_sec",
    )
    fig.update_traces(
        textposition="outside",
        marker_color=STATUS_COLORS["skip"],
        hovertemplate="Suite=<b>%{y}</b><br>Avg duration=<b>%{x:.2f}s</b><extra></extra>",
    )
    return _apply_layout(
        fig,
        height=max(360, 40 * len(df) + 80),
        xaxis_title="Avg duration (sec)",
        yaxis_title="",
    )
