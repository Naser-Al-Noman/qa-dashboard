"""
Load, validate, and normalize QA dashboard datasets.

Supports Streamlit uploads and local file paths for CSV, JSON, and Excel.
Schema checks fail with clear messages; row-level issues (dates, missing
values, bad statuses) are coerced or dropped with warnings instead of crashing.
"""

from __future__ import annotations

from io import BytesIO, StringIO
from pathlib import Path
from typing import Any, BinaryIO, Iterable, Sequence, Union

import pandas as pd
import streamlit as st

# ---------------------------------------------------------------------------
# Schema constants
# ---------------------------------------------------------------------------

TEST_REQUIRED_COLUMNS: list[str] = [
    "run_id",
    "timestamp",
    "website",
    "test_suite",
    "test_name",
    "status",
    "duration_sec",
    "browser",
    "environment",
]
TEST_OPTIONAL_COLUMNS: list[str] = ["defect_id", "severity"]

DEFECT_REQUIRED_COLUMNS: list[str] = [
    "defect_id",
    "title",
    "severity",
    "priority",
    "status",
    "created_date",
    "module",
]
DEFECT_OPTIONAL_COLUMNS: list[str] = ["closed_date"]

TEST_STATUSES: set[str] = {"pass", "fail", "skip", "blocked"}
DEFECT_STATUSES: set[str] = {"open", "in-progress", "closed"}

UploadedFileLike = Union[BinaryIO, Any]  # Streamlit UploadedFile or file-like
FileInput = Union[str, Path, UploadedFileLike]


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------

def validate_schema(
    df: pd.DataFrame,
    required_columns: Sequence[str],
) -> list[str]:
    """
    Check that a DataFrame contains all required columns.

    Column names are compared after light normalization (strip, lower-case,
    spaces to underscores) so ``Test Name`` matches ``test_name``.

    Parameters
    ----------
    df:
        DataFrame to validate.
    required_columns:
        Column names that must be present.

    Returns
    -------
    list[str]
        Human-readable error messages. An empty list means the schema is valid.

    Examples
    --------
    >>> validate_schema(pd.DataFrame(columns=["a", "b"]), ["a", "c"])
    ["Missing required column(s): c. Found columns: a, b."]
    """
    errors: list[str] = []

    if df is None:
        return ["No data provided (DataFrame is None)."]

    if not isinstance(df, pd.DataFrame):
        return [f"Expected a pandas DataFrame, got {type(df).__name__}."]

    if df.empty and len(df.columns) == 0:
        return ["DataFrame is empty and has no columns."]

    normalized_existing = {_normalize_name(c) for c in df.columns}
    missing = [
        col for col in required_columns if _normalize_name(col) not in normalized_existing
    ]

    if missing:
        found = ", ".join(sorted(normalized_existing)) or "(none)"
        errors.append(
            "Missing required column(s): "
            + ", ".join(missing)
            + f". Found columns: {found}."
        )

    return errors


def _normalize_name(name: str) -> str:
    """Normalize a column name for schema comparison."""
    return str(name).strip().lower().replace(" ", "_")


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Return a copy with normalized column names."""
    out = df.copy()
    out.columns = [_normalize_name(c) for c in out.columns]
    # Drop duplicate columns that collapse after normalization (keep first)
    out = out.loc[:, ~pd.Index(out.columns).duplicated()].copy()
    return out


# ---------------------------------------------------------------------------
# File reading
# ---------------------------------------------------------------------------

def _file_label(file: FileInput) -> str:
    """Best-effort filename for error messages and extension detection."""
    if isinstance(file, (str, Path)):
        return str(file)
    name = getattr(file, "name", None)
    return str(name) if name else "uploaded_file"


def _extension(file: FileInput) -> str:
    label = _file_label(file).lower()
    return Path(label).suffix


def _raw_bytes(file: FileInput) -> bytes:
    """Read bytes from a path or file-like / Streamlit upload."""
    if isinstance(file, (str, Path)):
        return Path(file).read_bytes()

    if hasattr(file, "getvalue"):
        data = file.getvalue()
        return data if isinstance(data, bytes) else bytes(data)

    if hasattr(file, "read"):
        # Allow re-reads from Streamlit buffers when possible
        if hasattr(file, "seek"):
            try:
                file.seek(0)
            except Exception:  # noqa: BLE001 — best-effort rewind
                pass
        data = file.read()
        return data if isinstance(data, bytes) else str(data).encode("utf-8")

    raise TypeError(
        f"Unsupported file input type: {type(file).__name__}. "
        "Pass a path, Streamlit UploadedFile, or binary file object."
    )


def read_tabular_file(file: FileInput) -> pd.DataFrame:
    """
    Load a tabular file into a DataFrame.

    Supported extensions: ``.csv``, ``.json``, ``.xlsx``, ``.xls``.

    Parameters
    ----------
    file:
        Local path, Streamlit ``UploadedFile``, or file-like object.

    Returns
    -------
    pd.DataFrame

    Raises
    ------
    ValueError
        If the extension is unsupported, the file is empty, or parsing fails.
    """
    ext = _extension(file)
    label = _file_label(file)

    try:
        raw = _raw_bytes(file)
    except OSError as exc:
        raise ValueError(
            f"Could not read '{label}'. Check that the file exists and is not locked. "
            f"Details: {exc}"
        ) from exc
    except TypeError as exc:
        raise ValueError(str(exc)) from exc

    if not raw:
        raise ValueError(
            f"'{label}' is empty. Upload a file that contains header + data rows."
        )

    if not ext:
        raise ValueError(
            f"'{label}' has no file extension. Rename it to .csv, .json, .xlsx, or .xls."
        )

    try:
        if ext == ".csv":
            try:
                df = pd.read_csv(BytesIO(raw))
            except UnicodeDecodeError:
                df = pd.read_csv(BytesIO(raw), encoding="latin-1")
        elif ext == ".json":
            try:
                text = raw.decode("utf-8-sig")
            except UnicodeDecodeError as exc:
                raise ValueError(
                    f"'{label}' is not valid UTF-8 JSON. Re-export as UTF-8."
                ) from exc
            try:
                df = pd.read_json(StringIO(text))
            except ValueError:
                df = pd.read_json(StringIO(text), lines=True)
        elif ext in {".xlsx", ".xls"}:
            engine = "openpyxl" if ext == ".xlsx" else None
            try:
                df = pd.read_excel(BytesIO(raw), engine=engine)
            except ImportError as exc:
                raise ValueError(
                    "Excel support requires the openpyxl package. "
                    "Run: pip install openpyxl"
                ) from exc
        else:
            raise ValueError(
                f"Unsupported file type '{ext}' for '{label}'. "
                "Please upload a .csv, .json, .xlsx, or .xls file."
            )
    except ValueError:
        raise
    except Exception as exc:  # noqa: BLE001 — surface parse errors clearly
        raise ValueError(
            f"Could not parse '{label}' as {ext}. "
            "The file may be corrupted, password-protected, or not tabular. "
            f"Details: {exc}"
        ) from exc

    if df is None or not isinstance(df, pd.DataFrame):
        raise ValueError(f"'{label}' did not produce a table of rows and columns.")

    if df.empty and len(df.columns) == 0:
        raise ValueError(
            f"'{label}' has no columns. Ensure the first row contains headers."
        )

    return df


def friendly_load_error(exc: BaseException, *, kind: str = "file") -> str:
    """Return a concise message suitable for Streamlit error banners."""
    detail = str(exc).strip() or type(exc).__name__
    return (
        f"Could not load {kind}: {detail} "
        "See the README schema for required columns and allowed status values."
    )


# ---------------------------------------------------------------------------
# Value coercion helpers (graceful — no crashes)
# ---------------------------------------------------------------------------

def _coerce_datetime(series: pd.Series) -> pd.Series:
    """Parse datetimes; invalid values become NaT."""
    return pd.to_datetime(series, errors="coerce", utc=False)


def _blank_to_na(series: pd.Series) -> pd.Series:
    """Treat empty / placeholder strings as missing."""
    cleaned = series.replace(
        {
            "": pd.NA,
            "nan": pd.NA,
            "NaN": pd.NA,
            "none": pd.NA,
            "None": pd.NA,
            "NULL": pd.NA,
            "null": pd.NA,
        }
    )
    return cleaned


def _ensure_optional_columns(
    df: pd.DataFrame,
    optional: Iterable[str],
    warnings: list[str],
    fill_value: Any = pd.NA,
) -> pd.DataFrame:
    """Add missing optional columns and record warnings."""
    out = df.copy()
    for col in optional:
        if col not in out.columns:
            out[col] = fill_value
            warnings.append(f"Optional column '{col}' was missing — filled with nulls.")
    return out


def _drop_with_warning(
    df: pd.DataFrame,
    mask: pd.Series,
    warnings: list[str],
    message: str,
) -> pd.DataFrame:
    """Drop rows where ``mask`` is True and append a warning if any were removed."""
    bad = int(mask.sum())
    if bad:
        warnings.append(message.format(n=bad))
        return df.loc[~mask].copy()
    return df


# ---------------------------------------------------------------------------
# Public loaders
# ---------------------------------------------------------------------------

def load_test_results(file: FileInput) -> tuple[pd.DataFrame, list[str]]:
    """
    Load and normalize test execution results from CSV, JSON, or Excel.

    Validates the standard test schema, coerces timestamps and durations,
    normalizes status casing, and drops irreparable rows with warnings.

    Parameters
    ----------
    file:
        Path or uploaded file (``.csv``, ``.json``, ``.xlsx``, ``.xls``).

    Returns
    -------
    tuple[pd.DataFrame, list[str]]
        Cleaned DataFrame and a list of non-fatal warning messages.

    Raises
    ------
    ValueError
        If the file cannot be read or required columns are missing.
    """
    warnings: list[str] = []
    try:
        df = _normalize_columns(read_tabular_file(file))
    except ValueError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise ValueError(friendly_load_error(exc, kind="test results")) from exc

    schema_errors = validate_schema(df, TEST_REQUIRED_COLUMNS)
    if schema_errors:
        raise ValueError(
            "Test results schema validation failed. "
            + " ".join(schema_errors)
            + " Required: "
            + ", ".join(TEST_REQUIRED_COLUMNS)
            + "."
        )

    df = _ensure_optional_columns(df, TEST_OPTIONAL_COLUMNS, warnings)
    df = df[TEST_REQUIRED_COLUMNS + TEST_OPTIONAL_COLUMNS].copy()

    # Timestamps
    df["timestamp"] = _coerce_datetime(df["timestamp"])
    df = _drop_with_warning(
        df,
        df["timestamp"].isna(),
        warnings,
        "{n} row(s) had missing or unparseable timestamps and were dropped.",
    )

    # Status
    df["status"] = df["status"].astype(str).str.strip().str.lower()
    df = _drop_with_warning(
        df,
        ~df["status"].isin(TEST_STATUSES),
        warnings,
        "{n} row(s) had invalid status values and were dropped. "
        f"Allowed: {', '.join(sorted(TEST_STATUSES))}.",
    )

    # Duration
    df["duration_sec"] = pd.to_numeric(df["duration_sec"], errors="coerce")
    df = _drop_with_warning(
        df,
        df["duration_sec"].isna(),
        warnings,
        "{n} row(s) had missing or non-numeric duration_sec and were dropped.",
    )

    # String fields — keep rows even if some text is blank; just clean them
    for col in ["run_id", "website", "test_suite", "test_name", "browser", "environment"]:
        df[col] = df[col].astype(str).str.strip()

    df["defect_id"] = _blank_to_na(df["defect_id"].astype(str))
    df["severity"] = _blank_to_na(
        df["severity"].astype(str).str.strip().str.lower()
    )

    if df.empty:
        warnings.append("No valid test result rows remained after cleaning.")

    return df.sort_values("timestamp").reset_index(drop=True), warnings


def load_defects(file: FileInput) -> tuple[pd.DataFrame, list[str]]:
    """
    Load and normalize defect records from CSV, JSON, or Excel.

    Validates the standard defect schema, coerces dates, normalizes status
    aliases (e.g. ``in_progress`` → ``in-progress``), and drops irreparable
    rows with warnings.

    Parameters
    ----------
    file:
        Path or uploaded file (``.csv``, ``.json``, ``.xlsx``, ``.xls``).

    Returns
    -------
    tuple[pd.DataFrame, list[str]]
        Cleaned DataFrame and a list of non-fatal warning messages.

    Raises
    ------
    ValueError
        If the file cannot be read or required columns are missing.
    """
    warnings: list[str] = []
    try:
        df = _normalize_columns(read_tabular_file(file))
    except ValueError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise ValueError(friendly_load_error(exc, kind="defects")) from exc

    schema_errors = validate_schema(df, DEFECT_REQUIRED_COLUMNS)
    if schema_errors:
        raise ValueError(
            "Defects schema validation failed. "
            + " ".join(schema_errors)
            + " Required: "
            + ", ".join(DEFECT_REQUIRED_COLUMNS)
            + "."
        )

    df = _ensure_optional_columns(df, DEFECT_OPTIONAL_COLUMNS, warnings, fill_value=pd.NaT)
    df = df[DEFECT_REQUIRED_COLUMNS + DEFECT_OPTIONAL_COLUMNS].copy()

    df["created_date"] = _coerce_datetime(df["created_date"])
    df["closed_date"] = _coerce_datetime(df["closed_date"])

    df = _drop_with_warning(
        df,
        df["created_date"].isna(),
        warnings,
        "{n} defect row(s) had missing or unparseable created_date and were dropped.",
    )

    df["status"] = (
        df["status"]
        .astype(str)
        .str.strip()
        .str.lower()
        .replace(
            {
                "in_progress": "in-progress",
                "in progress": "in-progress",
                "resolved": "closed",
                "done": "closed",
                "fixed": "closed",
            }
        )
    )
    df = _drop_with_warning(
        df,
        ~df["status"].isin(DEFECT_STATUSES),
        warnings,
        "{n} defect row(s) had invalid status values and were dropped. "
        f"Allowed: {', '.join(sorted(DEFECT_STATUSES))}.",
    )

    df["severity"] = df["severity"].astype(str).str.strip().str.lower()
    df["priority"] = df["priority"].astype(str).str.strip().str.upper()
    for col in ["defect_id", "title", "module"]:
        df[col] = df[col].astype(str).str.strip()

    # Closed defects without closed_date stay loaded; resolution metrics skip them
    missing_closed = (df["status"] == "closed") & df["closed_date"].isna()
    if missing_closed.any():
        warnings.append(
            f"{int(missing_closed.sum())} closed defect(s) have no closed_date; "
            "they are kept but excluded from resolution-time averages."
        )

    if df.empty:
        warnings.append("No valid defect rows remained after cleaning.")

    return df.sort_values("created_date").reset_index(drop=True), warnings


# ---------------------------------------------------------------------------
# Session / filter helpers used by the Streamlit app
# ---------------------------------------------------------------------------

def init_session_state() -> None:
    """Initialize dashboard keys in ``st.session_state`` if missing."""
    defaults: dict[str, Any] = {
        "tests_df": None,
        "defects_df": None,
        "data_source": None,
        "filter_websites": [],
        "filter_environments": [],
        "filter_browsers": [],
        "filter_date_range": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def apply_test_filters(df: pd.DataFrame | None) -> pd.DataFrame:
    """Apply shared sidebar filters to a test-results DataFrame."""
    if df is None or df.empty:
        return pd.DataFrame()

    out = df.copy()
    websites = st.session_state.get("filter_websites") or []
    environments = st.session_state.get("filter_environments") or []
    browsers = st.session_state.get("filter_browsers") or []
    date_range = st.session_state.get("filter_date_range")

    if websites:
        out = out[out["website"].isin(websites)]
    if environments:
        out = out[out["environment"].isin(environments)]
    if browsers:
        out = out[out["browser"].isin(browsers)]
    if date_range and len(date_range) == 2 and date_range[0] and date_range[1]:
        start, end = pd.Timestamp(date_range[0]), pd.Timestamp(date_range[1])
        end = end + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
        out = out[(out["timestamp"] >= start) & (out["timestamp"] <= end)]
    return out.reset_index(drop=True)


def apply_defect_filters(
    df: pd.DataFrame | None,
    tests_df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """
    Apply shared filters to defects.

    Date range filters on ``created_date``. Website filter uses linked
    ``defect_id`` values and title matches when test data is available.
    """
    if df is None or df.empty:
        return pd.DataFrame()

    out = df.copy()
    date_range = st.session_state.get("filter_date_range")
    websites = st.session_state.get("filter_websites") or []

    if date_range and len(date_range) == 2 and date_range[0] and date_range[1]:
        start, end = pd.Timestamp(date_range[0]), pd.Timestamp(date_range[1])
        end = end + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
        out = out[(out["created_date"] >= start) & (out["created_date"] <= end)]

    if websites and tests_df is not None and not tests_df.empty:
        linked_ids = (
            tests_df.loc[
                tests_df["website"].isin(websites) & tests_df["defect_id"].notna(),
                "defect_id",
            ]
            .dropna()
            .unique()
        )
        pattern = "|".join(map(str, websites))
        title_mask = out["title"].str.contains(pattern, case=False, na=False)
        id_mask = out["defect_id"].isin(linked_ids)
        out = out[id_mask | title_mask]

    return out.reset_index(drop=True)


def reset_filters() -> None:
    """Clear shared filter selections (call after loading new data)."""
    st.session_state["filter_websites"] = []
    st.session_state["filter_environments"] = []
    st.session_state["filter_browsers"] = []
    st.session_state["filter_date_range"] = None


def render_global_filters() -> None:
    """
    Render sidebar filters shared across pages via ``st.session_state``.

    Only shows filter widgets for dimensions that exist in the loaded data,
    and only offers values present in that data.
    """
    tests = st.session_state.get("tests_df")
    defects = st.session_state.get("defects_df")

    st.sidebar.header("Filters")
    if tests is None and defects is None:
        st.sidebar.caption("Load data to enable filters.")
        return

    websites: list[str] = []
    environments: list[str] = []
    browsers: list[str] = []
    min_date = max_date = None

    if tests is not None and not tests.empty:
        websites = sorted(tests["website"].dropna().astype(str).unique().tolist())
        environments = sorted(tests["environment"].dropna().astype(str).unique().tolist())
        browsers = sorted(tests["browser"].dropna().astype(str).unique().tolist())
        min_date = tests["timestamp"].min().date()
        max_date = tests["timestamp"].max().date()
    elif defects is not None and not defects.empty:
        min_date = defects["created_date"].min().date()
        max_date = defects["created_date"].max().date()
    else:
        st.sidebar.warning("Loaded datasets are empty.")
        return

    def _valid_selection(key: str, options: list[str]) -> list[str]:
        previous = st.session_state.get(key) or []
        return [v for v in previous if v in options]

    if websites:
        st.session_state["filter_websites"] = st.sidebar.multiselect(
            "Website / project",
            options=websites,
            default=_valid_selection("filter_websites", websites),
            help="Only websites present in the loaded test data.",
        )
    else:
        st.session_state["filter_websites"] = []

    if environments:
        st.session_state["filter_environments"] = st.sidebar.multiselect(
            "Environment",
            options=environments,
            default=_valid_selection("filter_environments", environments),
            help="Only environments present in the loaded test data.",
        )
    else:
        st.session_state["filter_environments"] = []

    if browsers:
        st.session_state["filter_browsers"] = st.sidebar.multiselect(
            "Browser",
            options=browsers,
            default=_valid_selection("filter_browsers", browsers),
            help="Only browsers present in the loaded test data.",
        )
    else:
        st.session_state["filter_browsers"] = []

    if min_date is not None and max_date is not None:
        current = st.session_state.get("filter_date_range")
        if (
            not current
            or not isinstance(current, (list, tuple))
            or len(current) != 2
            or current[0] is None
            or current[1] is None
        ):
            default_range = (min_date, max_date)
        else:
            start = max(min_date, min(current[0], max_date))
            end = min(max_date, max(current[1], min_date))
            if start > end:
                start, end = min_date, max_date
            default_range = (start, end)

        st.session_state["filter_date_range"] = st.sidebar.date_input(
            "Date range",
            value=default_range,
            min_value=min_date,
            max_value=max_date,
            help="Filters test timestamps and defect created dates.",
        )
    else:
        st.session_state["filter_date_range"] = None


def dataframe_to_csv_bytes(df: pd.DataFrame) -> bytes:
    """Serialize a DataFrame to UTF-8 CSV bytes for Streamlit downloads."""
    return df.to_csv(index=False).encode("utf-8")
