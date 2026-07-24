"""Test Execution page — trends, run table, duration, and flaky tests."""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from utils.charts import line_duration, pass_fail_trend_chart
from utils.loaders import apply_test_filters, dataframe_to_csv_bytes
from utils.metrics import (
    calculate_execution_trends,
    detect_flaky_tests,
    duration_over_time,
    test_execution_kpis,
)
from utils.ui import bootstrap_page, show_error

# Status badges aligned with the dashboard color scheme
STATUS_BADGES: dict[str, str] = {
    "pass": "🟢 pass",
    "fail": "🔴 fail",
    "skip": "⚪ skip",
    "blocked": "🟠 blocked",
}

bootstrap_page("Test Execution · QA Analytics", icon="🧪")


def _render() -> None:
    """Render the Test Execution page body."""
    st.title("Test Execution")
    st.caption("Status trends, run history, duration drift, and flaky tests.")

    tests_raw = st.session_state.get("tests_df")
    if tests_raw is None:
        st.info(
            "No test data loaded yet. Go to **QA Analytics Dashboard** (Home) and "
            "click **Load demo data** or upload test results."
        )
        return

    tests = apply_test_filters(tests_raw)
    if tests.empty:
        st.warning("No test rows match the current sidebar filters.")
        return

    kpis = test_execution_kpis(tests)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total runs", f"{kpis['total']:,}")
    c2.metric("Pass rate", f"{kpis['pass_rate']:.1f}%")
    c3.metric("Fail rate", f"{kpis['fail_rate']:.1f}%")
    c4.metric("Avg duration", f"{kpis['avg_duration']:.1f}s")

    st.subheader("Pass / fail / skip trend")
    freq_label = st.radio(
        "Trend aggregation",
        options=["Daily", "Weekly"],
        horizontal=True,
        key="exec_trend_freq",
    )
    freq = "D" if freq_label == "Daily" else "W"
    trend_df = calculate_execution_trends(tests, freq=freq)
    trend_fig = pass_fail_trend_chart(trend_df)
    trend_fig.update_layout(title=f"Executions by status ({freq_label.lower()})")
    st.plotly_chart(trend_fig, use_container_width=True)

    st.subheader("Duration trend")
    st.caption(
        "Average run duration over time. A rising line suggests tests are getting slower "
        "(heavier suites, waits, or environmental lag)."
    )
    duration_df = duration_over_time(tests, freq=freq)
    duration_fig = line_duration(
        duration_df, title=f"Average duration ({freq_label.lower()})"
    )
    st.plotly_chart(duration_fig, use_container_width=True)

    if len(duration_df) >= 4:
        mid = len(duration_df) // 2
        early = float(duration_df["avg_duration_sec"].iloc[:mid].mean())
        late = float(duration_df["avg_duration_sec"].iloc[mid:].mean())
        delta = late - early
        if abs(delta) < 0.25:
            st.caption(f"Recent vs earlier period: roughly flat ({delta:+.2f}s).")
        elif delta > 0:
            st.caption(
                f"Recent period averages **{delta:.2f}s slower** than the earlier half "
                f"({early:.2f}s → {late:.2f}s)."
            )
        else:
            st.caption(
                f"Recent period averages **{abs(delta):.2f}s faster** than the earlier half "
                f"({early:.2f}s → {late:.2f}s)."
            )

    st.subheader("Test runs")
    st.caption("Use the controls below to filter rows. Click column headers to sort.")

    f1, f2, f3, f4 = st.columns([1.2, 1.2, 1.2, 1.4])
    status_options = sorted(
        tests["status"].dropna().astype(str).str.lower().unique().tolist()
    )
    suite_options = sorted(tests["test_suite"].dropna().astype(str).unique().tolist())
    browser_options = sorted(tests["browser"].dropna().astype(str).unique().tolist())

    with f1:
        status_filter = st.multiselect(
            "Status",
            options=status_options,
            default=status_options,
            key="exec_table_status",
        )
    with f2:
        suite_filter = st.multiselect(
            "Test suite",
            options=suite_options,
            default=[],
            key="exec_table_suite",
            help="Leave empty to include all suites.",
        )
    with f3:
        browser_filter = st.multiselect(
            "Browser",
            options=browser_options,
            default=[],
            key="exec_table_browser",
            help="Leave empty to include all browsers.",
        )
    with f4:
        name_query = st.text_input(
            "Search test name",
            value="",
            placeholder="Contains…",
            key="exec_table_search",
        )

    table_df = tests.copy()
    table_df["status"] = table_df["status"].astype(str).str.strip().str.lower()

    if status_filter:
        table_df = table_df[table_df["status"].isin(status_filter)]
    if suite_filter:
        table_df = table_df[table_df["test_suite"].isin(suite_filter)]
    if browser_filter:
        table_df = table_df[table_df["browser"].isin(browser_filter)]
    if name_query.strip():
        q = name_query.strip().lower()
        table_df = table_df[
            table_df["test_name"].astype(str).str.lower().str.contains(q, na=False)
        ]

    display_cols = [
        c
        for c in [
            "run_id",
            "timestamp",
            "website",
            "test_suite",
            "test_name",
            "status",
            "duration_sec",
            "browser",
            "environment",
            "defect_id",
        ]
        if c in table_df.columns
    ]
    view = (
        table_df[display_cols]
        .sort_values("timestamp", ascending=False)
        .reset_index(drop=True)
    )
    view["status"] = view["status"].map(lambda s: STATUS_BADGES.get(s, s))

    st.caption(f"Showing **{len(view):,}** of **{len(tests):,}** filtered runs.")
    st.dataframe(
        view,
        use_container_width=True,
        hide_index=True,
        height=420,
        column_config={
            "timestamp": st.column_config.DatetimeColumn(
                "timestamp", format="YYYY-MM-DD HH:mm"
            ),
            "duration_sec": st.column_config.NumberColumn(
                "duration_sec", format="%.2f s"
            ),
            "status": st.column_config.TextColumn(
                "status",
                help="🟢 pass · 🔴 fail · ⚪ skip · 🟠 blocked",
            ),
        },
    )
    st.download_button(
        "Download table view (CSV)",
        data=dataframe_to_csv_bytes(
            table_df[display_cols].sort_values("timestamp", ascending=False)
        ),
        file_name="test_runs_view.csv",
        mime="text/csv",
    )

    st.subheader("Flaky tests")
    with st.expander("What does “flaky” mean?", expanded=True):
        st.markdown(
            """
A **flaky test** is one that does not fail for a stable reason — its result
**alternates between pass and fail** across runs of the same test (same website,
suite, and test name), even when the product under test may not have changed.

This dashboard flags a test as flaky when, ordered by time, it has at least one
**pass ↔ fail** transition (skip/blocked runs are ignored for this check).

Flakes waste triage time: treat them as signal to stabilize the test (waits,
selectors, test data) rather than only filing product bugs.
            """
        )

    flaky = detect_flaky_tests(tests)
    if flaky.empty:
        st.success("No flaky tests detected in the current filter window.")
    else:
        st.metric("Flaky tests found", f"{len(flaky):,}")
        st.dataframe(
            flaky,
            use_container_width=True,
            hide_index=True,
            column_config={
                "transitions": st.column_config.NumberColumn(
                    "transitions",
                    help="Number of adjacent pass↔fail flips over time",
                ),
                "flaky_score": st.column_config.NumberColumn(
                    "flaky_score",
                    help="transitions / (pass-fail runs − 1); closer to 1 = more unstable",
                    format="%.3f",
                ),
                "runs_pass_fail": st.column_config.NumberColumn(
                    "runs_pass_fail",
                    help="Count of pass+fail observations used for detection",
                ),
            },
        )


try:
    _render()
except Exception as exc:  # noqa: BLE001
    show_error(exc, context="Test Execution page")
