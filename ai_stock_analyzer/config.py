from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml


ROOT_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT_DIR / "config"
REPORTS_DIR = ROOT_DIR / "reports"
CACHE_DIR = ROOT_DIR / ".cache"
PORTFOLIO_DIR = ROOT_DIR / "portfolio"
TEMPLATES_DIR = ROOT_DIR / "templates"


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


@lru_cache(maxsize=None)
def load_config(name: str) -> dict[str, Any]:
    return load_yaml(CONFIG_DIR / name)


def load_all_configs() -> dict[str, Any]:
    return {
        "stocks": load_config("stocks.yaml"),
        "thresholds": load_config("thresholds.yaml"),
        "risk_control": load_config("risk-control.yaml"),
        "market_context": load_config("market-context.yaml"),
        "events_calendar": load_config("events-calendar.yaml"),
    }


def list_stock_entries(stocks_config: dict[str, Any]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for universe_type in ("core_universe", "candidate_universe"):
        for raw_entry in stocks_config.get(universe_type, []):
            entry = dict(raw_entry)
            entry["universe_type"] = universe_type
            entries.append(entry)
    return entries


def ensure_report_dir(report_date: str) -> Path:
    report_dir = REPORTS_DIR / report_date
    report_dir.mkdir(parents=True, exist_ok=True)
    return report_dir

