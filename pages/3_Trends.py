"""Trends page — test and defect patterns over time."""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from utils.charts import (
    defects_trend,
    line_duration,
    line_pass_rate,
    stacked_status_over_time,
)
from utils.loaders import (
    apply_defect_filters,
    apply_test_filters,
    init_session_state,
    render_global_filters,
)
from utils.metrics import (
    defects_over_time,
    duration_over_time,
    tests_over_time,
)

st.set_page_config(page_title="Trends", page_icon="📈", layout="wide")
init_session_state()
render_global_filters()

st.title("Trends")
st.caption("Pass rate, duration, execution volume, and defect create/close trends.")

freq_label = st.radio(
    "Aggregation",
    options=["Daily", "Weekly"],
    horizontal=True,
)
freq = "D" if freq_label == "Daily" else "W"

tests_raw = st.session_state.get("tests_df")
defects_raw = st.session_state.get("defects_df")

if tests_raw is None and defects_raw is None:
    st.info("No data loaded. Go to **Home** and load sample data or upload files.")
    st.stop()

tests = apply_test_filters(tests_raw) if tests_raw is not None else None
defects = (
    apply_defect_filters(defects_raw, tests_raw) if defects_raw is not None else None
)

st.subheader("Test trends")
if tests is None or tests.empty:
    st.warning("No filtered test data available.")
else:
    timeline = tests_over_time(tests, freq=freq)
    duration = duration_over_time(tests, freq=freq)
    st.plotly_chart(
        line_pass_rate(timeline, f"Pass rate ({freq_label.lower()})"),
        use_container_width=True,
    )
    c1, c2 = st.columns(2)
    with c1:
        st.plotly_chart(
            stacked_status_over_time(
                timeline, f"Execution volume ({freq_label.lower()})"
            ),
            use_container_width=True,
        )
    with c2:
        st.plotly_chart(
            line_duration(duration, f"Average duration ({freq_label.lower()})"),
            use_container_width=True,
        )

st.subheader("Defect trends")
if defects is None or defects.empty:
    st.warning("No filtered defect data available.")
else:
    dtrend = defects_over_time(defects, freq=freq)
    st.plotly_chart(
        defects_trend(dtrend, f"Defects created vs closed ({freq_label.lower()})"),
        use_container_width=True,
    )
