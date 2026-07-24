"""
Metric calculations for the QA Analytics Dashboard.

New analysis helpers (pass rate, trends, flakiness, MTTR, failing modules)
sit alongside existing KPI helpers used by the Streamlit pages.
"""

from __future__ import annotations

from typing import Sequence

import pandas as pd

# ---------------------------------------------------------------------------
# Requested analysis functions
# ---------------------------------------------------------------------------

def calculate_pass_rate(
    df: pd.DataFrame,
    group_by: str | Sequence[str] | None = None,
) -> float | pd.DataFrame:
    """
    Compute pass rate as a percentage of all recorded executions.

    Logic
    -----
    ``pass_rate = 100 * (rows with status == "pass") / (all rows in scope)``.

    Assumptions
    -----------
    - ``df`` has a ``status`` column with values like pass/fail/skip/blocked.
    - Skip and blocked runs **count in the denominator** (they are executions
      that did not pass). If you prefer pass/(pass+fail) only, filter the
      frame before calling this function.
    - Empty input returns ``0.0`` (or an empty DataFrame when grouping).

    Parameters
    ----------
    df:
        Test execution DataFrame.
    group_by:
        Optional column name or list of columns. When provided, returns one
        row per group with ``runs``, ``passes``, and ``pass_rate``.

    Returns
    -------
    float | pd.DataFrame
        Overall pass rate (0–100) or a grouped summary table.
    """
    empty_grouped = pd.DataFrame(columns=_as_list(group_by) + ["runs", "passes", "pass_rate"])
    if df is None or df.empty or "status" not in df.columns:
        return empty_grouped if group_by is not None else 0.0

    work = df.copy()
    work["status"] = work["status"].astype(str).str.strip().str.lower()

    if group_by is None:
        total = len(work)
        if total == 0:
            return 0.0
        passes = int((work["status"] == "pass").sum())
        return round(100.0 * passes / total, 2)

    groups = _as_list(group_by)
    missing = [c for c in groups if c not in work.columns]
    if missing:
        raise ValueError(f"group_by column(s) not found: {', '.join(missing)}")

    summary = (
        work.groupby(groups, dropna=False)
        .agg(
            runs=("status", "size"),
            passes=("status", lambda s: int((s == "pass").sum())),
        )
        .reset_index()
    )
    summary["pass_rate"] = summary.apply(
        lambda r: round(100.0 * r["passes"] / r["runs"], 2) if r["runs"] else 0.0,
        axis=1,
    )
    return summary.sort_values("pass_rate", ascending=False).reset_index(drop=True)


def calculate_execution_trends(df: pd.DataFrame, freq: str = "D") -> pd.DataFrame:
    """
    Aggregate pass / fail / skip (and blocked) counts over time.

    Logic
    -----
    1. Floor each ``timestamp`` to the period start implied by ``freq``
       (e.g. ``D`` = calendar day, ``W`` = week).
    2. Count executions per period and status.
    3. Return a wide table with one row per period.

    Assumptions
    -----------
    - Requires ``timestamp`` (datetime-like) and ``status``.
    - Status values are normalized to lower-case before counting.
    - Periods with no data are omitted (not zero-filled across the full range).
    - ``blocked`` is included when present so trends stay schema-complete;
      pass/fail/skip columns are always present (0 if absent).

    Parameters
    ----------
    df:
        Test execution DataFrame.
    freq:
        Pandas offset alias passed to ``Series.dt.to_period`` (default ``D``).

    Returns
    -------
    pd.DataFrame
        Columns: ``date``, ``pass``, ``fail``, ``skip``, ``blocked``,
        ``total``, ``pass_rate``.
    """
    columns = ["date", "pass", "fail", "skip", "blocked", "total", "pass_rate"]
    if df is None or df.empty:
        return pd.DataFrame(columns=columns)
    if "timestamp" not in df.columns or "status" not in df.columns:
        return pd.DataFrame(columns=columns)

    tmp = df.copy()
    tmp["timestamp"] = pd.to_datetime(tmp["timestamp"], errors="coerce")
    tmp = tmp.dropna(subset=["timestamp"])
    if tmp.empty:
        return pd.DataFrame(columns=columns)

    tmp["status"] = tmp["status"].astype(str).str.strip().str.lower()
    tmp["date"] = tmp["timestamp"].dt.to_period(freq).dt.to_timestamp()

    pivot = (
        tmp.pivot_table(
            index="date",
            columns="status",
            values="timestamp",
            aggfunc="count",
            fill_value=0,
        )
        .reset_index()
    )
    pivot.columns.name = None

    for col in ["pass", "fail", "skip", "blocked"]:
        if col not in pivot.columns:
            pivot[col] = 0

    pivot["total"] = pivot[["pass", "fail", "skip", "blocked"]].sum(axis=1)
    pivot["pass_rate"] = pivot.apply(
        lambda r: round(100.0 * r["pass"] / r["total"], 2) if r["total"] else 0.0,
        axis=1,
    )
    return pivot[columns].sort_values("date").reset_index(drop=True)


def detect_flaky_tests(df: pd.DataFrame) -> pd.DataFrame:
    """
    Find tests whose outcomes alternate between pass and fail across runs.

    Logic
    -----
    1. Identify a test by ``(website, test_suite, test_name)`` when those
       columns exist; otherwise by ``test_name`` alone.
    2. Sort each test's runs by ``timestamp``.
    3. Keep only ``pass`` and ``fail`` outcomes (skip/blocked are ignored for
       flakiness — they are not treated as a pass/fail flip).
    4. Count adjacent transitions where status changes between pass and fail.
    5. A test is flaky if it has **at least one** such transition and at least
       two pass/fail observations.

    Assumptions
    -----------
    - Flakiness here means **outcome instability over time**, not merely a
      mix of statuses in an unordered bag. A test that fails twice then
      always passes has one transition and is flagged; a test that only
      ever fails is not.
    - Requires ``test_name``, ``status``, and preferably ``timestamp``.
      Without timestamps, original row order is used (less reliable).

    Parameters
    ----------
    df:
        Test execution DataFrame.

    Returns
    -------
    pd.DataFrame
        Flaky tests with ``transitions``, ``runs_pass_fail``, ``passes``,
        ``fails``, and identity columns — sorted by transitions descending.
    """
    id_cols = [c for c in ["website", "test_suite", "test_name"] if df is not None and c in df.columns]
    base_cols = id_cols + ["transitions", "runs_pass_fail", "passes", "fails", "flaky_score"]
    if df is None or df.empty or "test_name" not in df.columns or "status" not in df.columns:
        return pd.DataFrame(columns=base_cols if id_cols else ["test_name"] + base_cols[1:])

    if not id_cols:
        id_cols = ["test_name"]

    work = df.copy()
    work["status"] = work["status"].astype(str).str.strip().str.lower()
    if "timestamp" in work.columns:
        work["timestamp"] = pd.to_datetime(work["timestamp"], errors="coerce")
        work = work.sort_values(["timestamp"], kind="mergesort")
    else:
        work = work.reset_index(drop=True)

    # Only pass/fail contribute to flip detection
    pf = work[work["status"].isin(["pass", "fail"])].copy()
    if pf.empty:
        return pd.DataFrame(columns=id_cols + ["transitions", "runs_pass_fail", "passes", "fails", "flaky_score"])

    rows: list[dict] = []
    for keys, group in pf.groupby(id_cols, dropna=False):
        if not isinstance(keys, tuple):
            keys = (keys,)
        statuses = group["status"].tolist()
        if len(statuses) < 2:
            continue

        transitions = sum(
            1
            for a, b in zip(statuses, statuses[1:])
            if a != b and {a, b} == {"pass", "fail"}
        )
        if transitions < 1:
            continue

        passes = statuses.count("pass")
        fails = statuses.count("fail")
        runs_pf = len(statuses)
        record = dict(zip(id_cols, keys))
        record.update(
            {
                "transitions": int(transitions),
                "runs_pass_fail": runs_pf,
                "passes": passes,
                "fails": fails,
                # Simple 0–1 score: more flips relative to opportunities
                "flaky_score": round(transitions / max(runs_pf - 1, 1), 3),
            }
        )
        rows.append(record)

    if not rows:
        return pd.DataFrame(
            columns=id_cols + ["transitions", "runs_pass_fail", "passes", "fails", "flaky_score"]
        )

    return (
        pd.DataFrame(rows)
        .sort_values(["transitions", "flaky_score"], ascending=False)
        .reset_index(drop=True)
    )


def calculate_mttr(defects_df: pd.DataFrame) -> pd.DataFrame:
    """
    Mean time to resolution (MTTR) in days, grouped by severity.

    Logic
    -----
    1. Keep defects with ``status == "closed"`` and both ``created_date`` and
       ``closed_date`` present.
    2. ``resolution_days = (closed_date - created_date)`` in fractional days.
    3. Negative intervals (data errors) are clipped to 0.
    4. Aggregate mean (and median / count) per ``severity``.

    Assumptions
    -----------
    - Open / in-progress defects are excluded (no resolution yet).
    - Closed defects missing ``closed_date`` are excluded.
    - MTTR is calendar time, not business hours.
    - Severity labels are lower-cased for grouping.

    Parameters
    ----------
    defects_df:
        Defect DataFrame with severity and date columns.

    Returns
    -------
    pd.DataFrame
        Columns: ``severity``, ``defect_count``, ``mttr_days``,
        ``median_days``.
    """
    columns = ["severity", "defect_count", "mttr_days", "median_days"]
    needed = {"status", "severity", "created_date", "closed_date"}
    if defects_df is None or defects_df.empty or not needed.issubset(defects_df.columns):
        return pd.DataFrame(columns=columns)

    work = defects_df.copy()
    work["status"] = work["status"].astype(str).str.strip().str.lower()
    work["severity"] = work["severity"].astype(str).str.strip().str.lower()
    work["created_date"] = pd.to_datetime(work["created_date"], errors="coerce")
    work["closed_date"] = pd.to_datetime(work["closed_date"], errors="coerce")

    closed = work[
        (work["status"] == "closed")
        & work["created_date"].notna()
        & work["closed_date"].notna()
    ].copy()
    if closed.empty:
        return pd.DataFrame(columns=columns)

    closed["resolution_days"] = (
        (closed["closed_date"] - closed["created_date"]).dt.total_seconds() / 86400.0
    ).clip(lower=0)

    summary = (
        closed.groupby("severity", dropna=False)
        .agg(
            defect_count=("resolution_days", "size"),
            mttr_days=("resolution_days", "mean"),
            median_days=("resolution_days", "median"),
        )
        .reset_index()
    )
    summary["mttr_days"] = summary["mttr_days"].round(2)
    summary["median_days"] = summary["median_days"].round(2)

    severity_order = ["critical", "high", "medium", "low"]
    summary["severity"] = pd.Categorical(
        summary["severity"], categories=severity_order, ordered=True
    )
    return summary.sort_values("severity").reset_index(drop=True)


def get_top_failing_modules(df: pd.DataFrame, top_n: int = 10) -> pd.DataFrame:
    """
    Pareto-style ranking of modules / suites by failure count.

    Logic
    -----
    1. Treat ``test_suite`` as the module dimension for test results (falls
       back to ``module`` if ``test_suite`` is absent).
    2. Count rows with ``status == "fail"`` per module.
    3. Sort highest failure count first and take ``top_n``.
    4. Add cumulative failure share (%) for a simple Pareto view.

    Assumptions
    -----------
    - Only ``fail`` counts toward the ranking (not skip/blocked).
    - ``top_n`` truncates the chart/table; cumulative % is computed on the
      **full** failure distribution, then the top rows are returned (so the
      last visible cumulative % may be < 100 if more modules exist).

    Parameters
    ----------
    df:
        Test execution DataFrame.
    top_n:
        Maximum rows to return (default 10).

    Returns
    -------
    pd.DataFrame
        Columns: ``module``, ``failures``, ``runs``, ``fail_rate``,
        ``cumulative_pct``.
    """
    columns = ["module", "failures", "runs", "fail_rate", "cumulative_pct"]
    if df is None or df.empty or "status" not in df.columns:
        return pd.DataFrame(columns=columns)

    module_col = "test_suite" if "test_suite" in df.columns else (
        "module" if "module" in df.columns else None
    )
    if module_col is None:
        return pd.DataFrame(columns=columns)

    work = df.copy()
    work["status"] = work["status"].astype(str).str.strip().str.lower()

    summary = (
        work.groupby(module_col, dropna=False)
        .agg(
            runs=("status", "size"),
            failures=("status", lambda s: int((s == "fail").sum())),
        )
        .reset_index()
        .rename(columns={module_col: "module"})
    )
    summary = summary[summary["failures"] > 0].copy()
    if summary.empty:
        return pd.DataFrame(columns=columns)

    summary["fail_rate"] = (100.0 * summary["failures"] / summary["runs"]).round(2)
    summary = summary.sort_values(["failures", "fail_rate"], ascending=False)
    total_failures = summary["failures"].sum()
    summary["cumulative_pct"] = (
        100.0 * summary["failures"].cumsum() / total_failures
    ).round(2)

    return summary[columns].head(top_n).reset_index(drop=True)


def _as_list(value: str | Sequence[str] | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    return list(value)


# ---------------------------------------------------------------------------
# Existing helpers used by Streamlit pages
# ---------------------------------------------------------------------------

def empty_test_kpis() -> dict:
    return {
        "total": 0,
        "pass": 0,
        "fail": 0,
        "skip": 0,
        "blocked": 0,
        "pass_rate": 0.0,
        "fail_rate": 0.0,
        "avg_duration": 0.0,
        "median_duration": 0.0,
    }


def test_execution_kpis(df: pd.DataFrame) -> dict:
    """Overview KPIs for the home and test-execution pages."""
    if df is None or df.empty:
        return empty_test_kpis()

    total = len(df)
    counts = df["status"].astype(str).str.lower().value_counts()
    passed = int(counts.get("pass", 0))
    failed = int(counts.get("fail", 0))
    skipped = int(counts.get("skip", 0))
    blocked = int(counts.get("blocked", 0))

    return {
        "total": total,
        "pass": passed,
        "fail": failed,
        "skip": skipped,
        "blocked": blocked,
        "pass_rate": calculate_pass_rate(df),
        "fail_rate": round(100.0 * failed / total, 2) if total else 0.0,
        "avg_duration": round(float(df["duration_sec"].mean()), 2)
        if "duration_sec" in df.columns
        else 0.0,
        "median_duration": round(float(df["duration_sec"].median()), 2)
        if "duration_sec" in df.columns
        else 0.0,
    }


def status_breakdown(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=["status", "count"])
    out = (
        df["status"]
        .astype(str)
        .str.lower()
        .value_counts()
        .rename_axis("status")
        .reset_index(name="count")
    )
    return out


def duration_by_suite(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty or "test_suite" not in df.columns:
        return pd.DataFrame(columns=["test_suite", "avg_duration_sec", "runs"])
    return (
        df.groupby("test_suite", as_index=False)
        .agg(avg_duration_sec=("duration_sec", "mean"), runs=("run_id", "count"))
        .assign(avg_duration_sec=lambda x: x["avg_duration_sec"].round(2))
        .sort_values("avg_duration_sec", ascending=False)
    )


def flaky_or_failing_tests(df: pd.DataFrame, top_n: int = 10) -> pd.DataFrame:
    """Highest fail-count tests (distinct from transition-based flaky detection)."""
    if df is None or df.empty:
        return pd.DataFrame(
            columns=["test_name", "test_suite", "website", "fails", "runs", "fail_rate"]
        )
    grouped = (
        df.groupby(["website", "test_suite", "test_name"], as_index=False)
        .agg(
            runs=("run_id", "count"),
            fails=("status", lambda s: int((s.astype(str).str.lower() == "fail").sum())),
        )
    )
    grouped["fail_rate"] = (100.0 * grouped["fails"] / grouped["runs"]).round(2)
    return (
        grouped[grouped["fails"] > 0]
        .sort_values(["fails", "fail_rate"], ascending=False)
        .head(top_n)
        .reset_index(drop=True)
    )


def tests_over_time(df: pd.DataFrame, freq: str = "D") -> pd.DataFrame:
    """Alias for :func:`calculate_execution_trends` (used by chart pages)."""
    return calculate_execution_trends(df, freq=freq)


def duration_over_time(df: pd.DataFrame, freq: str = "D") -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=["date", "avg_duration_sec"])
    tmp = df.copy()
    tmp["timestamp"] = pd.to_datetime(tmp["timestamp"], errors="coerce")
    tmp = tmp.dropna(subset=["timestamp"])
    tmp["date"] = tmp["timestamp"].dt.to_period(freq).dt.to_timestamp()
    return (
        tmp.groupby("date", as_index=False)
        .agg(avg_duration_sec=("duration_sec", "mean"))
        .assign(avg_duration_sec=lambda x: x["avg_duration_sec"].round(2))
        .sort_values("date")
    )


def empty_defect_kpis() -> dict:
    return {
        "total": 0,
        "open": 0,
        "in_progress": 0,
        "closed": 0,
        "avg_resolution_days": 0.0,
        "median_resolution_days": 0.0,
    }


def defect_kpis(df: pd.DataFrame) -> dict:
    if df is None or df.empty:
        return empty_defect_kpis()

    counts = df["status"].astype(str).str.lower().value_counts()
    mttr = calculate_mttr(df)
    overall_mttr = 0.0
    overall_median = 0.0
    if not mttr.empty:
        # Weighted mean across severities
        overall_mttr = round(
            float((mttr["mttr_days"] * mttr["defect_count"]).sum() / mttr["defect_count"].sum()),
            2,
        )
        # Approximate overall median via pooled closed defects
        closed = df.copy()
        closed["status"] = closed["status"].astype(str).str.lower()
        closed = closed[closed["status"] == "closed"].dropna(subset=["created_date", "closed_date"])
        if not closed.empty:
            days = (
                (
                    pd.to_datetime(closed["closed_date"], errors="coerce")
                    - pd.to_datetime(closed["created_date"], errors="coerce")
                ).dt.total_seconds()
                / 86400.0
            ).clip(lower=0)
            overall_median = round(float(days.median()), 2)

    return {
        "total": len(df),
        "open": int(counts.get("open", 0)),
        "in_progress": int(counts.get("in-progress", 0)),
        "closed": int(counts.get("closed", 0)),
        "avg_resolution_days": overall_mttr,
        "median_resolution_days": overall_median,
    }


def defect_breakdown(df: pd.DataFrame, column: str) -> pd.DataFrame:
    if df is None or df.empty or column not in df.columns:
        return pd.DataFrame(columns=[column, "count"])
    return (
        df[column]
        .value_counts()
        .rename_axis(column)
        .reset_index(name="count")
    )


def defects_over_time(df: pd.DataFrame, freq: str = "D") -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=["date", "created", "closed"])

    created = df.copy()
    created["created_date"] = pd.to_datetime(created["created_date"], errors="coerce")
    created = created.dropna(subset=["created_date"])
    created["date"] = created["created_date"].dt.to_period(freq).dt.to_timestamp()
    created_counts = created.groupby("date").size().rename("created")

    closed = df.dropna(subset=["closed_date"]).copy() if "closed_date" in df.columns else pd.DataFrame()
    if closed.empty:
        closed_counts = pd.Series(dtype=int, name="closed")
    else:
        closed["closed_date"] = pd.to_datetime(closed["closed_date"], errors="coerce")
        closed = closed.dropna(subset=["closed_date"])
        closed["date"] = closed["closed_date"].dt.to_period(freq).dt.to_timestamp()
        closed_counts = closed.groupby("date").size().rename("closed")

    out = pd.concat([created_counts, closed_counts], axis=1).fillna(0).astype(int)
    out = out.reset_index().rename(columns={"index": "date"})
    if "date" not in out.columns:
        out = out.rename(columns={out.columns[0]: "date"})
    return out.sort_values("date").reset_index(drop=True)


def linked_failure_summary(tests: pd.DataFrame, defects: pd.DataFrame) -> pd.DataFrame:
    """Failures/blocked runs that reference a known defect."""
    empty = pd.DataFrame(
        columns=[
            "defect_id",
            "title",
            "severity",
            "priority",
            "status",
            "linked_runs",
        ]
    )
    if tests is None or tests.empty or defects is None or defects.empty:
        return empty

    linked = tests[tests["defect_id"].notna()].copy()
    if linked.empty:
        return empty

    counts = linked.groupby("defect_id").size().rename("linked_runs").reset_index()
    merged = counts.merge(
        defects[["defect_id", "title", "severity", "priority", "status"]],
        on="defect_id",
        how="left",
    )
    return merged.sort_values("linked_runs", ascending=False).reset_index(drop=True)
