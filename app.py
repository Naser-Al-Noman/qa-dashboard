"""
QA Analytics Dashboard — main entry point.

Sidebar: upload test/defect files or load demo data, plus shared filters.
Main area: summary metrics when data is loaded, otherwise a welcome screen.
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from data.sample_data import generate_sample_data
from utils.loaders import (
    apply_defect_filters,
    apply_test_filters,
    dataframe_to_csv_bytes,
    friendly_load_error,
    init_session_state,
    load_defects,
    load_test_results,
    render_global_filters,
    reset_filters,
)
from utils.metrics import (
    calculate_pass_rate,
    defect_kpis,
    detect_flaky_tests,
    linked_failure_summary,
    test_execution_kpis,
)
from utils.ui import configure_page, format_user_error, show_error

configure_page("QA Analytics Dashboard", icon="📊")
init_session_state()

# ---------------------------------------------------------------------------
# Sidebar — data source
# ---------------------------------------------------------------------------
st.sidebar.title("QA Analytics")
st.sidebar.markdown("Upload results or explore with demo data.")

st.sidebar.header("Data source")

if st.sidebar.button("Load demo data", type="primary", use_container_width=True):
    try:
        tests, defects = generate_sample_data(save_csv=False)
        st.session_state["tests_df"] = tests
        st.session_state["defects_df"] = defects
        st.session_state["data_source"] = "demo"
        reset_filters()
        st.sidebar.success(f"Demo loaded: {len(tests):,} runs, {len(defects):,} defects.")
        st.rerun()
    except Exception as exc:  # noqa: BLE001
        st.sidebar.error(format_user_error(exc, context="Demo data"))

st.sidebar.caption("Or upload your own files (CSV, JSON, or Excel):")

up_tests = st.sidebar.file_uploader(
    "Test results",
    type=["csv", "json", "xlsx", "xls"],
    key="upload_tests",
    help="Standard test execution schema — one row per run.",
)
up_defects = st.sidebar.file_uploader(
    "Defects",
    type=["csv", "json", "xlsx", "xls"],
    key="upload_defects",
    help="Standard defect schema — one row per defect.",
)

if st.sidebar.button("Apply uploads", use_container_width=True):
    if up_tests is None and up_defects is None:
        st.sidebar.warning("Choose at least one file first.")
    else:
        errors: list[str] = []
        loaded_any = False

        if up_tests is not None:
            try:
                tests, warns = load_test_results(up_tests)
                st.session_state["tests_df"] = tests
                loaded_any = True
                for w in warns:
                    st.sidebar.warning(w)
                st.sidebar.success(f"Loaded {len(tests):,} test rows.")
            except Exception as exc:  # noqa: BLE001
                errors.append(friendly_load_error(exc, kind="test results"))

        if up_defects is not None:
            try:
                defects, warns = load_defects(up_defects)
                st.session_state["defects_df"] = defects
                loaded_any = True
                for w in warns:
                    st.sidebar.warning(w)
                st.sidebar.success(f"Loaded {len(defects):,} defect rows.")
            except Exception as exc:  # noqa: BLE001
                errors.append(friendly_load_error(exc, kind="defects"))

        for err in errors:
            st.sidebar.error(err)

        if loaded_any:
            st.session_state["data_source"] = "upload"
            reset_filters()
            if not errors:
                st.rerun()

if st.sidebar.button("Clear data", use_container_width=True):
    st.session_state["tests_df"] = None
    st.session_state["defects_df"] = None
    st.session_state["data_source"] = None
    reset_filters()
    st.rerun()

render_global_filters()

# ---------------------------------------------------------------------------
# Main page
# ---------------------------------------------------------------------------
st.title("QA Analytics Dashboard")
st.caption(
    "Data-source agnostic insights for test execution and defects — "
    "works with any website’s results in the standard schema."
)

try:
    tests_raw = st.session_state.get("tests_df")
    defects_raw = st.session_state.get("defects_df")
    has_data = tests_raw is not None or defects_raw is not None

    if not has_data:
        st.markdown("### Welcome")
        st.info(
            "No data loaded yet. Use the **sidebar** to get started:\n\n"
            "1. Click **Load demo data** to explore with realistic sample results, or\n"
            "2. Upload **test results** and/or **defects** as CSV, JSON, or Excel, "
            "then click **Apply uploads**.\n\n"
            "After data is loaded, use the sidebar filters (website, environment, "
            "browser, date range) and open **Test Execution**, **Defect Metrics**, "
            "or **Trends** for deeper charts."
        )
        with st.expander("Expected file schemas", expanded=False):
            st.markdown(
                """
**Test results** (one row per execution):  
`run_id`, `timestamp`, `website`, `test_suite`, `test_name`, `status`
(`pass` / `fail` / `skip` / `blocked`), `duration_sec`, `browser`,
`environment`, optional `defect_id`, `severity`

**Defects** (one row per defect):  
`defect_id`, `title`, `severity`, `priority`, `status`
(`open` / `in-progress` / `closed`), `created_date`, optional `closed_date`,
`module`
                """
            )
        st.stop()

    tests = apply_test_filters(tests_raw)
    defects = apply_defect_filters(defects_raw, tests_raw)

    source = st.session_state.get("data_source") or "loaded"
    st.caption(
        f"Source: **{source}** · "
        f"Showing **{len(tests):,}** test runs and **{len(defects):,}** defects "
        "after filters."
    )

    tk = test_execution_kpis(tests)
    dk = defect_kpis(defects)
    pass_pct = float(calculate_pass_rate(tests)) if not tests.empty else 0.0
    flaky_count = len(detect_flaky_tests(tests)) if not tests.empty else 0
    avg_duration = tk["avg_duration"] if not tests.empty else 0.0

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Total runs", f"{tk['total']:,}")
    m2.metric("Pass %", f"{pass_pct:.1f}%")
    m3.metric("Avg duration", f"{avg_duration:.1f}s")
    m4.metric("Flaky tests", f"{flaky_count:,}")
    m5.metric("Open defects", f"{dk['open']:,}")

    if tests.empty and defects.empty:
        st.warning(
            "Nothing matches the current filters. Clear or widen the sidebar filters."
        )
        st.stop()

    left, right = st.columns(2)
    with left:
        st.subheader("Test snapshot")
        if tests.empty:
            st.caption("No test rows in the current filter set.")
        else:
            st.write(
                {
                    "Pass": tk["pass"],
                    "Fail": tk["fail"],
                    "Skip": tk["skip"],
                    "Blocked": tk["blocked"],
                }
            )
            st.download_button(
                "Export filtered tests (CSV)",
                data=dataframe_to_csv_bytes(tests),
                file_name="filtered_test_results.csv",
                mime="text/csv",
                use_container_width=True,
            )

    with right:
        st.subheader("Defect snapshot")
        if defects.empty:
            st.caption("No defect rows in the current filter set.")
        else:
            st.write(
                {
                    "Open": dk["open"],
                    "In progress": dk["in_progress"],
                    "Closed": dk["closed"],
                    "Avg MTTR (days)": dk["avg_resolution_days"],
                }
            )
            st.download_button(
                "Export filtered defects (CSV)",
                data=dataframe_to_csv_bytes(defects),
                file_name="filtered_defects.csv",
                mime="text/csv",
                use_container_width=True,
            )

    st.subheader("Linked failures")
    linked = linked_failure_summary(
        tests, defects_raw if defects_raw is not None else defects
    )
    if linked.empty:
        st.caption("No filtered test runs reference a known defect_id.")
    else:
        st.dataframe(linked, use_container_width=True, hide_index=True)

    st.markdown("---")
    st.markdown(
        "Next: open **Test Execution**, **Defect Metrics**, or **Trends** in the sidebar."
    )
except Exception as exc:  # noqa: BLE001
    show_error(exc, context="Home page")
