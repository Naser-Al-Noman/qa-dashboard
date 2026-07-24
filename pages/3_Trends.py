"""Trends page — heatmaps, Pareto, failure–defect correlation, CSV export."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from utils.charts import browser_pass_rate_heatmap, pareto_chart
from utils.loaders import (
    apply_defect_filters,
    apply_test_filters,
    init_session_state,
    render_global_filters,
)
from utils.metrics import get_top_failing_modules

st.set_page_config(page_title="Trends", page_icon="📈", layout="wide")
init_session_state()
render_global_filters()

st.title("Trends & correlations")
st.caption(
    "Suite × browser pass rates, failing-module Pareto, and links between "
    "test failures and open high-severity defects."
)

tests_raw = st.session_state.get("tests_df")
defects_raw = st.session_state.get("defects_df")

if tests_raw is None and defects_raw is None:
    st.info(
        "No data loaded yet. Go to **QA Analytics Dashboard** (Home) and "
        "click **Load demo data** or upload files."
    )
    st.stop()

tests = apply_test_filters(tests_raw) if tests_raw is not None else pd.DataFrame()
defects = (
    apply_defect_filters(defects_raw, tests_raw)
    if defects_raw is not None
    else pd.DataFrame()
)

if tests.empty and defects.empty:
    st.warning("Nothing matches the current sidebar filters.")
    st.stop()


def _failure_defect_correlation(
    tests_df: pd.DataFrame,
    defects_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Join failing test suites with defect modules of the same name.

    Highlights modules that have both a high failure count and open/in-progress
    defects at critical/high severity.
    """
    empty_cols = [
        "module",
        "test_failures",
        "test_runs",
        "fail_rate",
        "open_defects",
        "open_high_severity",
        "open_critical",
        "open_high",
        "risk_flag",
    ]
    if tests_df is None or tests_df.empty:
        return pd.DataFrame(columns=empty_cols)

    work = tests_df.copy()
    work["status"] = work["status"].astype(str).str.strip().str.lower()
    fail_summary = (
        work.groupby("test_suite", dropna=False)
        .agg(
            test_runs=("status", "size"),
            test_failures=("status", lambda s: int((s == "fail").sum())),
        )
        .reset_index()
        .rename(columns={"test_suite": "module"})
    )
    fail_summary["fail_rate"] = (
        100.0 * fail_summary["test_failures"] / fail_summary["test_runs"]
    ).round(2)

    if defects_df is None or defects_df.empty or "module" not in defects_df.columns:
        fail_summary["open_defects"] = 0
        fail_summary["open_high_severity"] = 0
        fail_summary["open_critical"] = 0
        fail_summary["open_high"] = 0
        fail_summary["risk_flag"] = "failures only (no defect data)"
        return fail_summary.sort_values(
            ["test_failures", "fail_rate"], ascending=False
        ).reset_index(drop=True)

    d = defects_df.copy()
    d["status"] = d["status"].astype(str).str.strip().str.lower()
    d["severity"] = d["severity"].astype(str).str.strip().str.lower()
    d["module"] = d["module"].astype(str).str.strip()

    active = d[d["status"].isin(["open", "in-progress"])].copy()
    if active.empty:
        defect_summary = pd.DataFrame(
            columns=["module", "open_defects", "open_critical", "open_high", "open_high_severity"]
        )
    else:
        defect_summary = (
            active.groupby("module", dropna=False)
            .agg(
                open_defects=("defect_id", "count"),
                open_critical=("severity", lambda s: int((s == "critical").sum())),
                open_high=("severity", lambda s: int((s == "high").sum())),
            )
            .reset_index()
        )
        defect_summary["open_high_severity"] = (
            defect_summary["open_critical"] + defect_summary["open_high"]
        )

    merged = fail_summary.merge(defect_summary, on="module", how="left")
    for col in ["open_defects", "open_critical", "open_high", "open_high_severity"]:
        merged[col] = merged[col].fillna(0).astype(int)

    def _flag(row: pd.Series) -> str:
        if row["test_failures"] <= 0:
            return "no failures"
        if row["open_high_severity"] > 0:
            return "⚠ high risk — failures + open critical/high defects"
        if row["open_defects"] > 0:
            return "failures + open defects"
        return "failures only"

    merged["risk_flag"] = merged.apply(_flag, axis=1)
    return (
        merged.sort_values(
            ["open_high_severity", "test_failures", "fail_rate"],
            ascending=False,
        )
        .reset_index(drop=True)
    )


def _filtered_report_csv(
    tests_df: pd.DataFrame,
    defects_df: pd.DataFrame,
    correlation_df: pd.DataFrame,
    failing_modules_df: pd.DataFrame,
) -> bytes:
    """Bundle filtered tables into one UTF-8 CSV with section headers."""
    parts: list[str] = []
    sections = [
        ("TEST_RUNS", tests_df),
        ("DEFECTS", defects_df),
        ("FAILING_MODULES", failing_modules_df),
        ("FAILURE_DEFECT_CORRELATION", correlation_df),
    ]
    for name, frame in sections:
        parts.append(f"# {name}")
        if frame is None or frame.empty:
            parts.append("(empty)")
        else:
            parts.append(frame.to_csv(index=False).rstrip("\n"))
        parts.append("")
    return "\n".join(parts).encode("utf-8")


# ---------------------------------------------------------------------------
# Heatmap
# ---------------------------------------------------------------------------
st.subheader("Pass rate heatmap — test suite × browser")
if tests.empty:
    st.warning("No filtered test data for the heatmap.")
else:
    st.plotly_chart(browser_pass_rate_heatmap(tests), use_container_width=True)

# ---------------------------------------------------------------------------
# Pareto
# ---------------------------------------------------------------------------
st.subheader("Pareto — top failing modules")
failing_modules = (
    get_top_failing_modules(tests, top_n=10) if not tests.empty else pd.DataFrame()
)
if failing_modules.empty:
    st.info("No failing modules in the current filter window.")
else:
    st.plotly_chart(pareto_chart(failing_modules), use_container_width=True)
    st.dataframe(failing_modules, use_container_width=True, hide_index=True)

# ---------------------------------------------------------------------------
# Failure ↔ defect correlation
# ---------------------------------------------------------------------------
st.subheader("Failure ↔ defect correlation")
st.markdown(
    """
Modules (test suites) are matched to defect **module** names.  
**High risk** = the suite has test failures **and** at least one **open/in-progress**
defect with severity **critical** or **high**. That pattern often means product
issues are still open while automation keeps failing in the same area.
    """
)

correlation = _failure_defect_correlation(tests, defects)
high_risk = (
    correlation[correlation["risk_flag"].str.startswith("⚠")]
    if not correlation.empty
    else correlation
)

m1, m2, m3 = st.columns(3)
m1.metric(
    "Modules with failures",
    f"{int((correlation['test_failures'] > 0).sum()) if not correlation.empty else 0}",
)
m2.metric("High-risk modules", f"{len(high_risk):,}")
m3.metric(
    "Open high-severity defects (linked modules)",
    f"{int(correlation['open_high_severity'].sum()) if not correlation.empty else 0}",
)

if correlation.empty:
    st.info("Not enough data to correlate failures with defects.")
else:
    st.dataframe(
        correlation,
        use_container_width=True,
        hide_index=True,
        column_config={
            "fail_rate": st.column_config.NumberColumn("fail_rate", format="%.2f%%"),
            "risk_flag": st.column_config.TextColumn("risk_flag", width="large"),
        },
    )
    if not high_risk.empty:
        st.warning(
            "High-risk modules (failures + open critical/high defects): "
            + ", ".join(high_risk["module"].astype(str).tolist())
        )
    else:
        st.success(
            "No module currently combines test failures with open critical/high defects."
        )

# ---------------------------------------------------------------------------
# Download filtered report
# ---------------------------------------------------------------------------
st.subheader("Download filtered report")
st.caption(
    "Exports the current sidebar-filtered test runs, defects, failing-module "
    "Pareto table, and correlation summary as one CSV (section headers start with #)."
)

st.download_button(
    "Download filtered report as CSV",
    data=_filtered_report_csv(tests, defects, correlation, failing_modules),
    file_name="qa_filtered_report.csv",
    mime="text/csv",
    type="primary",
    use_container_width=True,
)
