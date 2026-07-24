"""Defect Metrics page — severity, priority, MTTR, burn-up, and open defects."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from utils.charts import defect_burnup_chart, defect_severity_donut, priority_bar
from utils.loaders import apply_defect_filters, dataframe_to_csv_bytes
from utils.metrics import calculate_mttr, defect_breakdown, defect_kpis
from utils.ui import bootstrap_page, show_error

SEVERITY_ORDER: list[str] = ["critical", "high", "medium", "low"]
PRIORITY_ORDER: list[str] = ["P0", "P1", "P2", "P3"]
SEVERITY_RANK: dict[str, int] = {s: i for i, s in enumerate(SEVERITY_ORDER)}
PRIORITY_RANK: dict[str, int] = {p: i for i, p in enumerate(PRIORITY_ORDER)}

bootstrap_page("Defect Metrics · QA Analytics", icon="🐛")


def _render() -> None:
    """Render the Defect Metrics page body."""
    st.title("Defect Metrics")
    st.caption("Severity, priority, resolution time (MTTR), burn-up, and open defects.")

    defects_raw = st.session_state.get("defects_df")
    tests_raw = st.session_state.get("tests_df")

    if defects_raw is None:
        st.info(
            "No defect data loaded yet. Go to **QA Analytics Dashboard** (Home) and "
            "click **Load demo data** or upload a defects file."
        )
        return

    defects = apply_defect_filters(defects_raw, tests_raw)
    if defects.empty:
        st.warning("No defect rows match the current sidebar filters.")
        return

    kpis = defect_kpis(defects)
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Total defects", f"{kpis['total']:,}")
    c2.metric("Open", f"{kpis['open']:,}")
    c3.metric("In progress", f"{kpis['in_progress']:,}")
    c4.metric("Closed", f"{kpis['closed']:,}")
    c5.metric("Avg MTTR (days)", f"{kpis['avg_resolution_days']:.1f}")

    left, right = st.columns(2)
    with left:
        st.subheader("Severity")
        st.plotly_chart(defect_severity_donut(defects), use_container_width=True)
    with right:
        st.subheader("Priority")
        priority_counts = defect_breakdown(defects, "priority")
        if not priority_counts.empty:
            priority_counts["priority"] = (
                priority_counts["priority"].astype(str).str.strip().str.upper()
            )
        st.plotly_chart(
            priority_bar(priority_counts, title="Defects by priority"),
            use_container_width=True,
        )

    st.subheader("MTTR by severity")
    st.caption(
        "Mean time to resolution in days for **closed** defects only "
        "(created_date → closed_date), grouped by severity."
    )
    mttr = calculate_mttr(defects)
    if mttr.empty:
        st.info(
            "Not enough closed defects with both created and closed dates to compute MTTR."
        )
    else:
        mttr_view = mttr.copy()
        mttr_view["severity"] = pd.Categorical(
            mttr_view["severity"], categories=SEVERITY_ORDER, ordered=True
        )
        mttr_view = mttr_view.sort_values("severity")

        fig = px.bar(
            mttr_view,
            x="severity",
            y="mttr_days",
            color="severity",
            text="mttr_days",
            title="Mean time to resolution (days)",
            color_discrete_map={
                "critical": "#b71c1c",
                "high": "#e53935",
                "medium": "#fb8c00",
                "low": "#9e9e9e",
            },
            hover_data={"defect_count": True, "median_days": True, "mttr_days": ":.2f"},
            category_orders={"severity": SEVERITY_ORDER},
        )
        fig.update_traces(
            texttemplate="%{text:.2f}d",
            textposition="outside",
            customdata=mttr_view[["defect_count", "median_days"]].to_numpy(),
            hovertemplate=(
                "Severity=<b>%{x}</b><br>"
                "MTTR=<b>%{y:.2f}</b> days<br>"
                "Median=%{customdata[1]:.2f} days<br>"
                "Closed defects=%{customdata[0]}<extra></extra>"
            ),
        )
        fig.update_layout(
            showlegend=False,
            yaxis_title="Days",
            xaxis_title="Severity",
            height=400,
            margin=dict(l=40, r=30, t=55, b=40),
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
        )
        st.plotly_chart(fig, use_container_width=True)
        st.dataframe(mttr_view, use_container_width=True, hide_index=True)

    st.subheader("Defect burn-up (opened vs closed)")
    st.caption(
        "Cumulative defects opened vs closed over time. The gap between the curves "
        "is the remaining open backlog."
    )
    st.plotly_chart(defect_burnup_chart(defects), use_container_width=True)

    st.subheader("Open defects")
    st.caption(
        "Active defects (`open` and `in-progress`), sorted by severity then priority "
        "(critical/P0 first)."
    )

    active = defects[
        defects["status"].astype(str).str.lower().isin(["open", "in-progress"])
    ].copy()

    if active.empty:
        st.success("No open or in-progress defects in the current filter window.")
        return

    active["severity_norm"] = active["severity"].astype(str).str.strip().str.lower()
    active["priority_norm"] = active["priority"].astype(str).str.strip().str.upper()
    active["_sev_rank"] = active["severity_norm"].map(SEVERITY_RANK).fillna(99)
    active["_pri_rank"] = active["priority_norm"].map(PRIORITY_RANK).fillna(99)
    active = active.sort_values(
        ["_sev_rank", "_pri_rank", "created_date"],
        ascending=[True, True, True],
    )

    display_cols = [
        c
        for c in [
            "defect_id",
            "title",
            "severity",
            "priority",
            "status",
            "module",
            "created_date",
        ]
        if c in active.columns
    ]
    open_view = active[display_cols].reset_index(drop=True)

    st.metric("Active defects", f"{len(open_view):,}")
    st.dataframe(
        open_view,
        use_container_width=True,
        hide_index=True,
        height=420,
        column_config={
            "created_date": st.column_config.DatetimeColumn(
                "created_date", format="YYYY-MM-DD"
            ),
            "severity": st.column_config.TextColumn("severity"),
            "priority": st.column_config.TextColumn("priority"),
            "status": st.column_config.TextColumn("status"),
        },
    )
    st.download_button(
        "Download open defects (CSV)",
        data=dataframe_to_csv_bytes(open_view),
        file_name="open_defects.csv",
        mime="text/csv",
    )


try:
    _render()
except Exception as exc:  # noqa: BLE001
    show_error(exc, context="Defect Metrics page")
