"""CSV loading with dates parsed centrally and graceful missing-feed handling."""
from __future__ import annotations

from pathlib import Path
from typing import Iterable

import pandas as pd


DATE_COLUMNS = {
    "date", "snapshot_date", "snapshot_available_date", "month_start",
    "forecast_issue_date", "planner_available_date", "marketing_available_date",
    "planner_consolidated_available_date", "booking_date", "arrival_date",
    "event_date", "week_start", "available_from",
}


def data_path(data_dir: str | Path = "data") -> Path:
    path = Path(data_dir)
    if not path.is_absolute() and not path.exists():
        path = Path(__file__).resolve().parents[1] / path
    return path


def load_datasets(data_dir: str | Path = "data", required: Iterable[str] | None = None) -> dict[str, pd.DataFrame]:
    path = data_path(data_dir)
    files = sorted(path.glob("*.csv"))
    datasets: dict[str, pd.DataFrame] = {}
    for file in files:
        frame = pd.read_csv(file)
        for column in set(frame.columns) & DATE_COLUMNS:
            frame[column] = pd.to_datetime(frame[column], errors="coerce")
        datasets[file.stem] = frame
    for name in required or []:
        if name not in datasets:
            raise FileNotFoundError(f"Missing required dataset {name}.csv; run python generate_data.py")
    return datasets


def read_config_csv(name: str, config_dir: str | Path = "config") -> pd.DataFrame:
    path = Path(config_dir)
    if not path.is_absolute() and not path.exists():
        path = Path(__file__).resolve().parents[1] / path
    return pd.read_csv(path / f"{name}.csv")
