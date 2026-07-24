"""
Shared Streamlit UI helpers for consistent page setup and error display.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def configure_page(
    title: str,
    *,
    icon: str = "📊",
    layout: str = "wide",
) -> None:
    """
    Apply standard ``st.set_page_config`` (must run before other Streamlit calls).

    Parameters
    ----------
    title:
        Browser tab / page title.
    icon:
        Emoji or image used as the page icon.
    layout:
        Streamlit layout mode (``wide`` by default for dashboard charts).
    """
    st.set_page_config(
        page_title=title,
        page_icon=icon,
        layout=layout,
        initial_sidebar_state="expanded",
    )


def bootstrap_page(title: str, *, icon: str = "📊") -> None:
    """Configure the page, init session state, and render shared sidebar filters."""
    from utils.loaders import init_session_state, render_global_filters

    configure_page(title, icon=icon)
    init_session_state()
    render_global_filters()


def format_user_error(exc: BaseException, *, context: str = "Operation") -> str:
    """
    Build a short, user-facing error message from an exception.

    Avoids dumping full tracebacks into the UI while keeping the root cause.
    """
    message = str(exc).strip() or exc.__class__.__name__
    return (
        f"**{context} failed.** {message}\n\n"
        "Check that your file is CSV, JSON, or Excel and matches the schema "
        "in the README (required columns, valid statuses, readable dates)."
    )


def show_error(exc: BaseException, *, context: str = "Operation") -> None:
    """Display a friendly error in the main area."""
    st.error(format_user_error(exc, context=context))
    with st.expander("Technical details"):
        st.code(f"{type(exc).__name__}: {exc}")


def show_sidebar_error(exc: BaseException, *, context: str = "Upload") -> None:
    """Display a friendly error in the sidebar (for upload flows)."""
    st.sidebar.error(format_user_error(exc, context=context))


def safe_metric_block(label: str, compute: Any) -> Any:
    """
    Run a metric/chart factory and show an error placeholder on failure.

    ``compute`` should be a zero-arg callable returning the value to display.
    """
    try:
        return compute()
    except Exception as exc:  # noqa: BLE001 — keep the page alive
        show_error(exc, context=label)
        return None
