from __future__ import annotations

import json
import re
import unicodedata
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd

from .config import REPORTS_DIR


REPORT_MARKER_START = "<!-- REPORT_PAYLOAD_START -->"
REPORT_MARKER_END = "<!-- REPORT_PAYLOAD_END -->"
CONSENSUS_MARKER_START = "<!-- CONSENSUS_PAYLOAD_START -->"
CONSENSUS_MARKER_END = "<!-- CONSENSUS_PAYLOAD_END -->"


def parse_date(value: Any | None) -> date:
    if value is None:
        return datetime.now().date()
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    return pd.Timestamp(value).date()


def iso_date(value: Any | None) -> str:
    return parse_date(value).isoformat()


def clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def safe_float(value: Any, default: float | None = None) -> float | None:
    if value is None:
        return default
    try:
        if pd.isna(value):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def piecewise_linear_score(value: float | None, anchor_points: Iterable[Iterable[float]]) -> float:
    if value is None:
        return 0.0
    try:
        numeric_value = float(value)
    except (TypeError, ValueError):
        return 0.0

    points = sorted((float(x), float(y)) for x, y in anchor_points)
    xs = np.array([x for x, _ in points], dtype=float)
    ys = np.array([y for _, y in points], dtype=float)
    score = float(np.interp(numeric_value, xs, ys, left=ys[0], right=ys[-1]))
    return clamp(score, 0.0, 1.0)


def standardized_score(value: float | None, center: float, scale: float, direction: str = "lower_better") -> float:
    if value is None or scale <= 0:
        return 0.0
    numeric_value = safe_float(value)
    if numeric_value is None:
        return 0.0
    z_value = (center - numeric_value) / scale if direction == "lower_better" else (numeric_value - center) / scale
    score = 1 / (1 + np.exp(-z_value))
    return clamp(float(score), 0.0, 1.0)


def json_default(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"Object of type {type(value)!r} is not JSON serializable")


def json_dumps(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, default=json_default)


def aggregate_data_source_status(statuses: Iterable[str]) -> str:
    normalized = {status for status in statuses if status}
    if not normalized:
        return "unknown"
    if len(normalized) == 1:
        return next(iter(normalized))
    return "mixed(" + ",".join(sorted(normalized)) + ")"


def latest_report_dates(limit: int = 2) -> list[str]:
    if not REPORTS_DIR.exists():
        return []
    dates = sorted(path.name for path in REPORTS_DIR.iterdir() if path.is_dir())
    return dates[-limit:]


def slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    normalized = normalized.lower().strip()
    normalized = re.sub(r"[^a-z0-9_-]+", "-", normalized)
    normalized = re.sub(r"-{2,}", "-", normalized).strip("-_")
    return normalized or "unknown"


def build_analysis_stem(agent_name: str, vendor: str, model: str) -> str:
    return f"{slugify(agent_name)}-{slugify(vendor)}-{slugify(model)}-analysis"


def resolve_report_path(report_dir: Path, stem: str, conflict_strategy: str = "suffix") -> Path:
    candidate = report_dir / f"{stem}.md"
    if not candidate.exists() or conflict_strategy == "overwrite":
        return candidate
    if conflict_strategy == "error":
        raise FileExistsError(f"报告文件已存在：{candidate}")
    version = 2
    while True:
        candidate = report_dir / f"{stem}-{version}.md"
        if not candidate.exists():
            return candidate
        version += 1


def print_capability_summary(data_source_status: str) -> None:
    print()
    print("当前仓库能力清单（精简版）")
    print("工作流：单AI分析 / 多AI落盘 / 共识与冲突检测 / 周度复盘")
    print("命令：python scripts\\generate_analysis.py | python scripts\\aggregate_ai_reports.py | python scripts\\review_metrics.py")
    print("命名：{agent}-{vendor}-{model}-analysis.md（自动 slugify）")
    print("多AI接入：按 templates\\agent-instruction.md 输出 Markdown + JSON")
    print("冲突策略：suffix(默认) / overwrite / error")
    print(f"数据源状态：{data_source_status}")

