from __future__ import annotations

import numpy as np
import pandas as pd


def moving_average(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(period, min_periods=period).mean()


def exponential_moving_average(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False, min_periods=period).mean()


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi_series = 100 - (100 / (1 + rs))
    rsi_series = rsi_series.where(avg_loss != 0, 100.0)
    rsi_series = rsi_series.where(avg_gain != 0, 0.0)
    neutral_mask = (avg_gain == 0) & (avg_loss == 0)
    rsi_series = rsi_series.where(~neutral_mask, 50.0)
    return rsi_series


def kdj(frame: pd.DataFrame, k_period: int = 9, d_period: int = 3, smoothing: int = 3) -> pd.DataFrame:
    low_min = frame["low"].rolling(k_period, min_periods=k_period).min()
    high_max = frame["high"].rolling(k_period, min_periods=k_period).max()
    denominator = (high_max - low_min).replace(0, np.nan)
    rsv = ((frame["close"] - low_min) / denominator * 100).clip(0, 100)
    k_value = rsv.ewm(alpha=1 / smoothing, adjust=False, min_periods=d_period).mean()
    d_value = k_value.ewm(alpha=1 / d_period, adjust=False, min_periods=d_period).mean()
    j_value = 3 * k_value - 2 * d_value
    return pd.DataFrame({"k": k_value, "d": d_value, "j": j_value})


def bollinger_bands(series: pd.Series, period: int = 20, std_dev: float = 2.0) -> pd.DataFrame:
    mid = series.rolling(period, min_periods=period).mean()
    std = series.rolling(period, min_periods=period).std(ddof=0)
    upper = mid + std_dev * std
    lower = mid - std_dev * std
    return pd.DataFrame({"mid": mid, "upper": upper, "lower": lower})


def true_range(frame: pd.DataFrame) -> pd.Series:
    previous_close = frame["close"].shift(1)
    ranges = pd.concat(
        [
            frame["high"] - frame["low"],
            (frame["high"] - previous_close).abs(),
            (frame["low"] - previous_close).abs(),
        ],
        axis=1,
    )
    return ranges.max(axis=1)


def atr(frame: pd.DataFrame, period: int = 14) -> pd.Series:
    tr = true_range(frame)
    return tr.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()


def macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    ema_fast = exponential_moving_average(series, fast)
    ema_slow = exponential_moving_average(series, slow)
    dif = ema_fast - ema_slow
    dea = dif.ewm(span=signal, adjust=False, min_periods=signal).mean()
    hist = (dif - dea) * 2
    return pd.DataFrame({"dif": dif, "dea": dea, "hist": hist})


def volume_ratio(series: pd.Series, lookback: int = 5) -> pd.Series:
    baseline = series.rolling(lookback, min_periods=lookback).mean().shift(1)
    return series / baseline.replace(0, np.nan)


def realized_volatility(series: pd.Series, lookback: int = 20) -> pd.Series:
    returns = series.pct_change()
    return returns.rolling(lookback, min_periods=lookback).std(ddof=0) * np.sqrt(252)


def drawdown(series: pd.Series, lookback: int = 60) -> pd.Series:
    rolling_max = series.rolling(lookback, min_periods=1).max()
    return series / rolling_max - 1


def prepare_indicator_frame(frame: pd.DataFrame, thresholds_config: dict) -> pd.DataFrame:
    indicator_cfg = thresholds_config["oversold_scoring"]
    data = frame.sort_values("date").reset_index(drop=True).copy()

    data["ma5"] = moving_average(data["close"], 5)
    data["ma10"] = moving_average(data["close"], 10)
    data["ma20"] = moving_average(data["close"], thresholds_config["data_standard"]["min_periods"]["ma"])
    data["ma60"] = moving_average(data["close"], 60)
    data["rsi14"] = rsi(data["close"], thresholds_config["data_standard"]["min_periods"]["rsi"])

    kdj_frame = kdj(data, 9, 3, 3)
    data["kdj_k"] = kdj_frame["k"]
    data["kdj_d"] = kdj_frame["d"]
    data["kdj_j"] = kdj_frame["j"]

    boll = bollinger_bands(
        data["close"],
        thresholds_config["data_standard"]["min_periods"]["bollinger"],
        2.0,
    )
    data["bb_mid"] = boll["mid"]
    data["bb_upper"] = boll["upper"]
    data["bb_lower"] = boll["lower"]

    data["atr14"] = atr(data, thresholds_config["data_standard"]["min_periods"]["atr"])

    macd_frame = macd(data["close"], 12, 26, 9)
    data["macd_dif"] = macd_frame["dif"]
    data["macd_dea"] = macd_frame["dea"]
    data["macd_hist"] = macd_frame["hist"]

    data["volume_ratio_5"] = volume_ratio(data["volume"], 5)
    data["amount_ma20"] = moving_average(data["amount"], 20)
    data["turnover_ma20"] = moving_average(data["turnover"], 20)
    data["realized_vol_20"] = realized_volatility(data["close"], 20)
    data["drawdown_60"] = drawdown(data["close"], 60)
    data["daily_return"] = data["close"].pct_change()
    data["ma20_deviation_atr"] = (data["close"] - data["ma20"]) / data["atr14"].replace(0, np.nan)
    data["bb_lower_distance"] = (data["close"] - data["bb_lower"]) / data["bb_lower"].replace(0, np.nan)
    data["ma5_slope_3"] = data["ma5"] / data["ma5"].shift(3) - 1
    data["trend_down"] = (data["ma5"] < data["ma10"]) & (data["ma10"] < data["ma20"]) & (data["close"] < data["ma5"])
    return data

