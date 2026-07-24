"""Generate realistic fake QA test and defect data with Faker."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from faker import Faker

SAMPLES_DIR = Path(__file__).resolve().parent / "samples"

WEBSITES = {
    "ShopFlow": ["Checkout", "Catalog", "Auth", "Cart"],
    "MediCare Portal": ["Appointments", "Records", "Auth", "Billing"],
    "FinLedger": ["Accounts", "Transfers", "Reports", "Auth"],
}

TEST_STATUSES = ["pass", "fail", "skip", "blocked"]
TEST_STATUS_WEIGHTS = [0.72, 0.16, 0.07, 0.05]

SEVERITIES = ["critical", "high", "medium", "low"]
SEVERITY_WEIGHTS = [0.10, 0.28, 0.40, 0.22]

PRIORITIES = ["P0", "P1", "P2", "P3"]
PRIORITY_WEIGHTS = [0.08, 0.25, 0.42, 0.25]

DEFECT_STATUSES = ["open", "in-progress", "closed"]
DEFECT_STATUS_WEIGHTS = [0.28, 0.22, 0.50]

BROWSERS = ["Chrome", "Firefox", "Edge", "Safari"]
ENVIRONMENTS = ["staging", "production", "qa", "dev"]


def _choice(rng: np.random.Generator, options: list, weights: list):
    probs = np.array(weights, dtype=float)
    probs /= probs.sum()
    return rng.choice(options, p=probs)


def generate_sample_data(
    n_tests: int = 550,
    n_defects: int = 55,
    days: int = 90,
    seed: int = 42,
    save_csv: bool = True,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Build linked sample test execution and defect DataFrames.

    Returns
    -------
    tests_df, defects_df
    """
    fake = Faker()
    Faker.seed(seed)
    rng = np.random.default_rng(seed)

    now = datetime.now().replace(microsecond=0)
    start = now - timedelta(days=days)

    # --- Defects first so failed tests can reference them ---
    defect_rows: list[dict] = []
    website_names = list(WEBSITES.keys())

    for i in range(1, n_defects + 1):
        website = rng.choice(website_names)
        module = rng.choice(WEBSITES[website])
        severity = _choice(rng, SEVERITIES, SEVERITY_WEIGHTS)
        priority = _choice(rng, PRIORITIES, PRIORITY_WEIGHTS)
        status = _choice(rng, DEFECT_STATUSES, DEFECT_STATUS_WEIGHTS)

        created = fake.date_time_between(start_date=start, end_date=now)
        closed_date = pd.NaT
        if status == "closed":
            resolve_hours = int(rng.integers(6, 14 * 24))
            closed_candidate = created + timedelta(hours=resolve_hours)
            closed_date = min(closed_candidate, now)

        verb = fake.word()
        noun = fake.word()
        defect_rows.append(
            {
                "defect_id": f"DEF-{i:04d}",
                "title": f"[{website}] {module}: {verb} {noun} issue",
                "severity": severity,
                "priority": priority,
                "status": status,
                "created_date": created,
                "closed_date": closed_date,
                "module": module,
            }
        )

    defects_df = pd.DataFrame(defect_rows)

    # Index open-ish defects by module for linking to failures
    defects_by_module: dict[str, list[dict]] = {}
    for _, row in defects_df.iterrows():
        defects_by_module.setdefault(row["module"], []).append(row.to_dict())

    # --- Test executions ---
    test_rows: list[dict] = []
    for i in range(1, n_tests + 1):
        website = rng.choice(website_names)
        suite = rng.choice(WEBSITES[website])
        status = _choice(rng, TEST_STATUSES, TEST_STATUS_WEIGHTS)
        timestamp = fake.date_time_between(start_date=start, end_date=now)

        # Realistic duration: most short, some slow
        duration = float(np.clip(rng.lognormal(mean=1.9, sigma=0.6), 0.4, 240.0))
        if status == "fail":
            duration *= float(rng.uniform(1.05, 1.4))
        elif status == "skip":
            duration *= float(rng.uniform(0.05, 0.25))
        elif status == "blocked":
            duration *= float(rng.uniform(0.3, 0.8))

        defect_id = None
        severity = None
        if status in {"fail", "blocked"}:
            candidates = defects_by_module.get(suite, [])
            if candidates and rng.random() < 0.7:
                chosen = candidates[int(rng.integers(0, len(candidates)))]
                defect_id = chosen["defect_id"]
                severity = chosen["severity"]

        test_name = (
            f"test_{suite.lower().replace(' ', '_')}_"
            f"{fake.word()}_{int(rng.integers(1, 20)):02d}"
        )

        test_rows.append(
            {
                "run_id": f"RUN-{i:05d}",
                "timestamp": timestamp,
                "website": website,
                "test_suite": suite,
                "test_name": test_name,
                "status": status,
                "duration_sec": round(duration, 2),
                "browser": rng.choice(BROWSERS),
                "environment": rng.choice(ENVIRONMENTS),
                "defect_id": defect_id,
                "severity": severity,
            }
        )

    tests_df = (
        pd.DataFrame(test_rows)
        .sort_values("timestamp")
        .reset_index(drop=True)
    )
    defects_df = defects_df.sort_values("created_date").reset_index(drop=True)

    if save_csv:
        save_sample_csvs(tests_df, defects_df)

    return tests_df, defects_df


def save_sample_csvs(
    tests_df: pd.DataFrame,
    defects_df: pd.DataFrame,
    output_dir: Path | None = None,
) -> Path:
    """Persist sample dataframes as CSVs under data/samples."""
    out = output_dir or SAMPLES_DIR
    out.mkdir(parents=True, exist_ok=True)
    tests_df.to_csv(out / "test_results.csv", index=False)
    defects_df.to_csv(out / "defects.csv", index=False)
    return out


if __name__ == "__main__":
    tests, defects = generate_sample_data()
    print(f"Wrote {len(tests)} test rows and {len(defects)} defect rows to {SAMPLES_DIR}")
    print(f"Linked failures: {tests['defect_id'].notna().sum()}")
