"""Performance and usage statistics derived from the event history, using Pandas."""

from __future__ import annotations

import pandas as pd

from core.event_logger import Event


def events_to_dataframe(events: list[Event]) -> pd.DataFrame:
    if not events:
        return pd.DataFrame(columns=["timestamp", "gesture", "command", "status"])
    df = pd.DataFrame([{
        "timestamp": pd.to_datetime(e.timestamp, unit="s"),
        "gesture": e.gesture,
        "command": e.command,
        "status": e.status,
    } for e in events])
    return df


def summarize(df: pd.DataFrame) -> dict:
    if df.empty:
        return {
            "total_recognized": 0,
            "total_executed": 0,
            "by_command": pd.Series(dtype=int),
        }
    executed = df[df["status"] == "executed"]
    return {
        "total_recognized": len(df),
        "total_executed": len(executed),
        "by_command": executed["command"].value_counts(),
    }
