from __future__ import annotations

from collections import defaultdict
from typing import Any

import numpy as np
import pandas as pd

from ..utils import clamp, safe_float, standardized_score


def score_oversold_components(
    indicator_frame: pd.DataFrame,
    thresholds_config: dict[str, Any],
    market_regime: str,
) -> tuple[dict[str, dict[str, Any]], float]:
    latest = indicator_frame.iloc[-1]
    oversold_cfg = thresholds_config["oversold_scoring"]
    active_components = oversold_cfg["default_components"]
    factor_cfg = oversold_cfg["factors"]
    total_weight = sum(factor_cfg[name]["weight"] for name in active_components)
    normalized_weights = {name: factor_cfg[name]["weight"] / total_weight for name in active_components}

    raw_values = {
        "rsi": safe_float(latest["rsi14"]),
        "bollinger": safe_float(latest["bb_lower_distance"]),
        "ma_deviation_atr": safe_float(latest["ma20_deviation_atr"]),
        "drawdown_position": safe_float(latest["drawdown_60"]),
        "kdj": safe_float(latest["kdj_k"]),
        "volume_ratio": safe_float(latest["volume_ratio_5"]),
    }

    regime_multiplier = thresholds_config["market_regime"]["oversold_score_multiplier"].get(market_regime, 1.0)
    components: dict[str, dict[str, Any]] = {}
    for name in active_components:
        config = factor_cfg[name]
        norm = standardized_score(raw_values[name], config["center"], config["scale"], config["direction"])
        score = norm * normalized_weights[name] * 100
        components[name] = {
            "raw_value": raw_values[name],
            "score": round(score, 2),
            "normalized_score": round(norm, 4),
            "weight": round(normalized_weights[name], 4),
            "explanation": config["explanation"],
        }

    total_score = sum(component["score"] for component in components.values())
    total_score = clamp(total_score * regime_multiplier, 0.0, 100.0)
    return components, round(total_score, 2)


def determine_score_band(score: float, thresholds_config: dict[str, Any]) -> str:
    bands = thresholds_config["oversold_scoring"]["score_bands"]
    if score >= bands["strong_candidate"]:
        return "强超跌"
    if score >= bands["candidate"]:
        return "超跌候选"
    if score >= bands["watch"]:
        return "观察"
    return "常规"


def evaluate_relative_strength(
    stock_frame: pd.DataFrame,
    benchmark_frame: pd.DataFrame | None,
    thresholds_config: dict[str, Any],
    benchmark_code: str,
    benchmark_name: str,
) -> dict[str, Any]:
    cfg = thresholds_config["relative_strength"]
    if benchmark_frame is None or benchmark_frame.empty:
        return {
            "benchmark": benchmark_code,
            "benchmark_name": benchmark_name,
            "return_diff_5d": None,
            "return_diff_20d": None,
            "ratio_vs_ma10": None,
            "signal": "未校验",
        }

    merged = pd.merge(
        stock_frame[["date", "close"]],
        benchmark_frame[["date", "close"]],
        on="date",
        how="inner",
        suffixes=("_stock", "_benchmark"),
    )
    if len(merged) < max(cfg["long_lookback"], cfg["ratio_ma_period"]) + 1:
        return {
            "benchmark": benchmark_code,
            "benchmark_name": benchmark_name,
            "return_diff_5d": None,
            "return_diff_20d": None,
            "ratio_vs_ma10": None,
            "signal": "未校验",
        }

    long_n = cfg["long_lookback"]
    short_n = cfg["short_lookback"]
    stock_ret_20 = merged["close_stock"].iloc[-1] / merged["close_stock"].iloc[-1 - long_n] - 1
    bench_ret_20 = merged["close_benchmark"].iloc[-1] / merged["close_benchmark"].iloc[-1 - long_n] - 1
    stock_ret_5 = merged["close_stock"].iloc[-1] / merged["close_stock"].iloc[-1 - short_n] - 1
    bench_ret_5 = merged["close_benchmark"].iloc[-1] / merged["close_benchmark"].iloc[-1 - short_n] - 1

    ratio = merged["close_stock"] / merged["close_benchmark"].replace(0, np.nan)
    ratio_ma = ratio.rolling(cfg["ratio_ma_period"], min_periods=cfg["ratio_ma_period"]).mean()
    ratio_vs_ma = ratio.iloc[-1] / ratio_ma.iloc[-1] - 1 if pd.notna(ratio_ma.iloc[-1]) else None

    diff_20 = stock_ret_20 - bench_ret_20
    diff_5 = stock_ret_5 - bench_ret_5
    if diff_20 <= cfg["negative_threshold"] and diff_5 <= 0:
        signal = "超跌但仍弱"
    elif diff_5 >= cfg["positive_threshold"] and (ratio_vs_ma or 0.0) > 0:
        signal = "超跌且相对转强"
    else:
        signal = "中性"

    return {
        "benchmark": benchmark_code,
        "benchmark_name": benchmark_name,
        "return_diff_5d": round(diff_5, 4),
        "return_diff_20d": round(diff_20, 4),
        "ratio_vs_ma10": round(float(ratio_vs_ma), 4) if ratio_vs_ma is not None else None,
        "signal": signal,
    }


def build_sector_context(preliminary_records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, dict[str, list[float]]] = defaultdict(lambda: {"oversold": [], "rs20": []})
    for record in preliminary_records:
        if not record["passed_hard_filters"]:
            continue
        grouped[record["sector"]]["oversold"].append(record["oversold_score_total"])
        rs_value = record["relative_strength"].get("return_diff_20d")
        if rs_value is not None:
            grouped[record["sector"]]["rs20"].append(rs_value)

    context: dict[str, dict[str, Any]] = {}
    for sector, values in grouped.items():
        oversold = values["oversold"]
        rs20 = values["rs20"]
        context[sector] = {
            "avg_oversold_score": round(float(np.mean(oversold)), 2) if oversold else None,
            "avg_relative_strength_20d": round(float(np.mean(rs20)), 4) if rs20 else None,
            "count": len(oversold),
        }
    return context


def evaluate_confirmations(
    indicator_frame: pd.DataFrame,
    thresholds_config: dict[str, Any],
    sector_context: dict[str, Any],
) -> tuple[dict[str, dict[str, Any]], bool]:
    latest = indicator_frame.iloc[-1]
    previous = indicator_frame.iloc[-2] if len(indicator_frame) >= 2 else latest
    cfg = thresholds_config["confirmations"]

    hist_rising_days = cfg["trend_reversal"]["macd_histogram_rising_days"]
    recent_hist = indicator_frame["macd_hist"].tail(hist_rising_days + 1).dropna()
    hist_rising = len(recent_hist) == hist_rising_days + 1 and recent_hist.diff().iloc[1:].gt(0).all()
    dif_cross = latest["macd_dif"] > latest["macd_dea"] and previous["macd_dif"] <= previous["macd_dea"]
    ma_period = cfg["trend_reversal"]["ma_period"]
    ma_column = f"ma{ma_period}"
    ma_slope = safe_float(latest.get("ma5_slope_3"))
    close_above_ma = bool(pd.notna(latest[ma_column]) and latest["close"] >= latest[ma_column])
    ma_slope_non_negative = ma_slope is not None and ma_slope >= 0
    trend_pass = bool((hist_rising or dif_cross) and (close_above_ma or ma_slope_non_negative))

    candle_range = max(float(latest["high"] - latest["low"]), 1e-6)
    lower_shadow_ratio = float(min(latest["open"], latest["close"]) - latest["low"]) / candle_range
    body_ratio = abs(float(latest["close"] - latest["open"])) / candle_range
    hammer = lower_shadow_ratio >= cfg["price_reclaim"]["lower_shadow_ratio_min"] and body_ratio <= cfg["price_reclaim"]["body_ratio_max"]
    low_lookback = cfg["price_reclaim"]["low_lookback"]
    recent_low = indicator_frame["low"].tail(low_lookback).min()
    reclaim = latest["close"] >= recent_low * (1 + cfg["price_reclaim"]["reclaim_ratio"])
    price_reclaim_pass = bool(hammer or reclaim)

    volume_ratio_value = safe_float(latest["volume_ratio_5"], 0.0) or 0.0
    daily_return = safe_float(latest["daily_return"], 0.0) or 0.0
    volume_enabled = bool(cfg["volume_confirmation"]["enabled"])
    volume_pass = bool(
        volume_ratio_value >= cfg["volume_confirmation"]["volume_ratio_threshold"]
        and daily_return >= cfg["volume_confirmation"]["min_positive_return"]
    )

    sector_pass = False
    if sector_context:
        sector_pass = bool(
            (sector_context.get("avg_oversold_score") or -999) >= cfg["sector_resonance"]["min_sector_avg_oversold_score"]
            and (sector_context.get("avg_relative_strength_20d") or -999) >= cfg["sector_resonance"]["min_sector_avg_relative_strength_20d"]
        )

    confirmations = {
        "trend_reversal": {
            "passed": trend_pass,
            "raw_value": {
                "macd_hist": safe_float(latest["macd_hist"]),
                "hist_rising": hist_rising,
                "dif": safe_float(latest["macd_dif"]),
                "dea": safe_float(latest["macd_dea"]),
                "close": safe_float(latest["close"]),
                ma_column: safe_float(latest[ma_column]),
                "ma_slope": ma_slope,
                "close_above_ma": close_above_ma,
            },
            "threshold": {
                "logic": "MACD 改善 且 (收盘站上 MA5 或 MA5 走平/向上)",
                "ma_period": ma_period,
                "macd_histogram_rising_days": hist_rising_days,
                "used_in_pass_count": True,
            },
            "explanation": cfg["trend_reversal"]["explanation"],
        },
        "price_reclaim": {
            "passed": price_reclaim_pass,
            "raw_value": {
                "lower_shadow_ratio": round(lower_shadow_ratio, 4),
                "body_ratio": round(body_ratio, 4),
                "hammer": hammer,
                "recent_low": safe_float(recent_low),
                "reclaim": reclaim,
            },
            "threshold": {
                "logic": "长下影止跌 或 收盘重新站回近 N 日低点上方",
                "low_lookback": low_lookback,
                "reclaim_ratio": cfg["price_reclaim"]["reclaim_ratio"],
                "used_in_pass_count": True,
            },
            "explanation": cfg["price_reclaim"]["explanation"],
        },
        "volume_confirmation": {
            "passed": volume_pass,
            "raw_value": {"volume_ratio": round(volume_ratio_value, 4), "daily_return": round(daily_return, 4)},
            "threshold": {
                "logic": "量比达到阈值且当日收益不为明显负值",
                "volume_ratio_threshold": cfg["volume_confirmation"]["volume_ratio_threshold"],
                "min_positive_return": cfg["volume_confirmation"]["min_positive_return"],
                "enabled": volume_enabled,
                "used_in_pass_count": volume_enabled,
            },
            "explanation": cfg["volume_confirmation"]["explanation"],
        },
        "sector_resonance": {
            "passed": sector_pass,
            "raw_value": sector_context,
            "threshold": {
                "logic": "同赛道平均超跌分与相对强弱达到最低阈值",
                "min_sector_avg_oversold_score": cfg["sector_resonance"]["min_sector_avg_oversold_score"],
                "min_sector_avg_relative_strength_20d": cfg["sector_resonance"]["min_sector_avg_relative_strength_20d"],
                "used_in_pass_count": True,
            },
            "explanation": cfg["sector_resonance"]["explanation"],
        },
    }
    pass_count = sum(
        1
        for item in confirmations.values()
        if item["passed"] and item["threshold"].get("used_in_pass_count", True)
    )
    return confirmations, pass_count >= cfg["minimum_pass_count"]

