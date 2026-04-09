from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import requests

from ..config import CACHE_DIR
from ..utils import iso_date


EASTMONEY_KLINE_URL = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
FIELD_NAMES = [
    "date",
    "open",
    "close",
    "high",
    "low",
    "volume",
    "amount",
    "amplitude",
    "pct_change",
    "change",
    "turnover",
]


EXCHANGE_PREFIX = {
    "SH": "1",
    "SH_INDEX": "1",
    "SZ": "0",
    "SZ_INDEX": "0",
    "BJ": "0",
}


def _cache_path(symbol: str, adjust: str, exchange: str | None) -> Path:
    exchange_label = (exchange or "AUTO").lower()
    return CACHE_DIR / "ohlcv" / f"{exchange_label}_{symbol}_{adjust}_daily.csv"


def _with_attrs(frame: pd.DataFrame, status: str, flags: list[str]) -> pd.DataFrame:
    result = frame.copy()
    result.attrs["source_status"] = status
    result.attrs["validation_flags"] = flags
    return result


def _build_secid(symbol: str, exchange: str | None = None) -> str:
    if exchange:
        prefix = EXCHANGE_PREFIX.get(exchange.upper())
        if prefix is None:
            raise ValueError(f"Unsupported exchange: {exchange}")
        return f"{prefix}.{symbol}"
    if symbol.startswith(("600", "601", "603", "605", "688", "689", "510", "511", "512", "513", "515", "588")):
        return f"1.{symbol}"
    if symbol.startswith(("159", "300", "301", "000", "001", "002", "003", "399")):
        return f"0.{symbol}"
    return f"1.{symbol}"


def _adjust_flag(adjust: str) -> str:
    mapping = {"none": "0", "qfq": "1", "hfq": "2"}
    return mapping.get(adjust, "1")


def _read_cache(cache_path: Path) -> pd.DataFrame | None:
    if not cache_path.exists():
        return None
    frame = pd.read_csv(cache_path, parse_dates=["date"])
    if frame.empty:
        return None
    return frame


def _write_cache(cache_path: Path, frame: pd.DataFrame) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    frame.sort_values("date").drop_duplicates(subset=["date"], keep="last").to_csv(cache_path, index=False)


def _fetch_from_eastmoney(symbol: str, start: str, end: str, adjust: str, exchange: str | None) -> pd.DataFrame:
    params = {
        "fields1": "f1,f2,f3,f4,f5,f6",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
        "klt": "101",
        "fqt": _adjust_flag(adjust),
        "beg": pd.Timestamp(start).strftime("%Y%m%d"),
        "end": pd.Timestamp(end).strftime("%Y%m%d"),
        "secid": _build_secid(symbol, exchange),
    }
    response = requests.get(EASTMONEY_KLINE_URL, params=params, timeout=10)
    response.raise_for_status()
    payload = response.json()
    data = payload.get("data") or {}
    klines = data.get("klines") or []
    if not klines:
        return pd.DataFrame(columns=FIELD_NAMES)

    rows: list[list[Any]] = [line.split(",") for line in klines]
    frame = pd.DataFrame(rows, columns=FIELD_NAMES)
    frame["date"] = pd.to_datetime(frame["date"])
    numeric_columns = [column for column in FIELD_NAMES if column != "date"]
    for column in numeric_columns:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame


def _generate_sample_data(symbol: str, start: str, end: str) -> pd.DataFrame:
    dates = pd.bdate_range(start=pd.Timestamp(start), end=pd.Timestamp(end))
    if len(dates) == 0:
        return pd.DataFrame(columns=FIELD_NAMES)

    digest = hashlib.sha256(symbol.encode("utf-8")).hexdigest()
    seed = int(digest[:8], 16)
    rng = np.random.default_rng(seed)
    base_price = 20 + (seed % 1000) / 10
    drift = ((seed % 11) - 5) / 2000
    returns = rng.normal(loc=drift, scale=0.02, size=len(dates))
    close = base_price * np.exp(np.cumsum(returns))
    open_ = close * (1 + rng.normal(0, 0.004, size=len(dates)))
    high = np.maximum(open_, close) * (1 + rng.uniform(0.002, 0.018, size=len(dates)))
    low = np.minimum(open_, close) * (1 - rng.uniform(0.002, 0.018, size=len(dates)))
    volume = rng.integers(2_000_000, 20_000_000, size=len(dates))
    amount = volume * close * rng.uniform(0.9, 1.1, size=len(dates))
    pct_change = np.insert(np.diff(close) / close[:-1], 0, 0.0) * 100
    change = np.insert(np.diff(close), 0, 0.0)
    amplitude = (high - low) / np.maximum(low, 1e-6) * 100
    turnover = rng.uniform(0.5, 5.5, size=len(dates))
    frame = pd.DataFrame(
        {
            "date": dates,
            "open": open_,
            "close": close,
            "high": high,
            "low": low,
            "volume": volume,
            "amount": amount,
            "amplitude": amplitude,
            "pct_change": pct_change,
            "change": change,
            "turnover": turnover,
        }
    )
    return frame


def get_ohlcv(
    symbol: str,
    start: str,
    end: str,
    adjust: str = "qfq",
    exchange: str | None = None,
) -> pd.DataFrame:
    start_ts = pd.Timestamp(start)
    end_ts = pd.Timestamp(end)
    cache_path = _cache_path(symbol, adjust, exchange)
    cached = _read_cache(cache_path)
    if cached is not None:
        if cached["date"].min() <= start_ts and cached["date"].max() >= end_ts:
            subset = cached[(cached["date"] >= start_ts) & (cached["date"] <= end_ts)].reset_index(drop=True)
            return _with_attrs(subset, "cache", ["使用本地缓存数据。"])

    last_error: str | None = None
    try:
        fetched = _fetch_from_eastmoney(symbol, start, end, adjust, exchange)
        if not fetched.empty:
            if cached is not None and not cached.empty:
                fetched = pd.concat([cached, fetched], ignore_index=True)
            _write_cache(cache_path, fetched)
            subset = fetched[(fetched["date"] >= start_ts) & (fetched["date"] <= end_ts)].reset_index(drop=True)
            return _with_attrs(subset, "real", [])
        last_error = "东方财富接口返回空数据"
    except Exception as exc:  # noqa: BLE001
        last_error = str(exc)

    if cached is not None and not cached.empty:
        subset = cached[(cached["date"] >= start_ts) & (cached["date"] <= end_ts)].reset_index(drop=True)
        if not subset.empty:
            return _with_attrs(subset, "cache", [f"实时拉取失败，回退缓存：{last_error}"])

    synthetic = _generate_sample_data(symbol, iso_date(start_ts), iso_date(end_ts))
    flags = ["数据源降级：使用可复现示例数据。"]
    if last_error:
        flags.append(last_error)
    return _with_attrs(synthetic, "degraded", flags)

