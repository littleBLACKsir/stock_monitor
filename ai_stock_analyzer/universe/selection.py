from __future__ import annotations

from collections import Counter
from typing import Any

import numpy as np
import pandas as pd

from ..indicators.scoring import evaluate_relative_strength
from ..indicators.technical import prepare_indicator_frame
from ..utils import safe_float


def detect_market_regime(
    benchmark_frames: dict[tuple[str, str | None], pd.DataFrame],
    market_context_config: dict[str, Any],
) -> dict[str, Any]:
    override = market_context_config.get("macro_overrides", {})
    if override.get("enabled"):
        return {
            "regime": override.get("regime", "neutral"),
            "macro_score": None,
            "notes": [override.get("note", "使用手工宏观覆盖。")],
        }

    rules = market_context_config["regime_detection"]
    regime_votes: list[float] = []
    notes: list[str] = []
    for benchmark in market_context_config["benchmarks"]["broad_market"]:
        frame = benchmark_frames.get((benchmark["code"], benchmark["exchange"]))
        if frame is None or frame.empty or len(frame) < rules["long_ma"] + 1:
            continue
        close = frame["close"]
        current = close.iloc[-1]
        ma_short = close.rolling(rules["short_ma"], min_periods=rules["short_ma"]).mean().iloc[-1]
        ma_long = close.rolling(rules["long_ma"], min_periods=rules["long_ma"]).mean().iloc[-1]
        lookback_return = current / close.iloc[-1 - rules["return_lookback"]] - 1
        trend_score = 1.0 if current > ma_long and ma_short > ma_long else -1.0 if current < ma_long else 0.0
        regime_votes.append((lookback_return * 4) + trend_score)
        notes.append(
            f"{benchmark['name']} 20日收益={lookback_return:.2%}，"
            f"短均线/长均线={'偏强' if trend_score > 0 else '偏弱' if trend_score < 0 else '中性'}。"
        )

    if not regime_votes:
        return {"regime": "neutral", "macro_score": None, "notes": ["基准指数数据不足，默认中性。"]}

    macro_score = float(np.mean(regime_votes))
    if macro_score <= rules["crisis_return_threshold"] * 4:
        regime = "crisis"
    elif macro_score <= rules["risk_off_return_threshold"] * 4:
        regime = "risk_off"
    elif macro_score >= rules["risk_on_return_threshold"] * 4:
        regime = "risk_on"
    else:
        regime = "neutral"
    return {"regime": regime, "macro_score": round(macro_score, 4), "notes": notes}


def _missing_ratio(frame: pd.DataFrame, lookback: int = 60) -> float:
    if frame.empty:
        return 1.0
    tail = frame.tail(lookback)
    observed = tail["close"].notna().sum()
    return round(max(0.0, 1 - observed / lookback), 4)


def _liquidity_quality(avg_amount: float, minimum: float) -> float:
    if minimum <= 0:
        return 1.0
    return max(0.0, min(1.0, avg_amount / (minimum * 3)))


def _drawdown_quality(drawdown_60: float) -> float:
    depth = abs(drawdown_60)
    score = 1 - abs(depth - 0.18) / 0.22
    return max(0.0, min(1.0, score))


def _volatility_quality(volatility_20: float, max_volatility: float) -> float:
    if max_volatility <= 0:
        return 1.0
    return max(0.0, min(1.0, 1 - volatility_20 / max_volatility))


def evaluate_universe(
    entries: list[dict[str, Any]],
    price_frames: dict[tuple[str, str | None], pd.DataFrame],
    benchmark_frames: dict[tuple[str, str | None], pd.DataFrame],
    stocks_config: dict[str, Any],
    thresholds_config: dict[str, Any],
    as_of_date: str,
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    rules = stocks_config["rules"]
    hard_cfg = rules["hard_filters"]
    soft_cfg = rules["soft_scoring"]
    prepared_frames: dict[tuple[str, str | None], pd.DataFrame] = {}
    records: list[dict[str, Any]] = []

    for entry in entries:
        key = (entry["code"], entry.get("exchange"))
        raw_frame = price_frames[key]
        prepared_frames[key] = prepare_indicator_frame(raw_frame, thresholds_config)

    sector_counter = Counter(entry["sector"] for entry in entries)
    for entry in entries:
        key = (entry["code"], entry.get("exchange"))
        frame = prepared_frames[key]
        benchmark_key = (entry["benchmark"], entry.get("benchmark_exchange"))
        benchmark_frame = benchmark_frames.get(benchmark_key)

        latest = frame.iloc[-1] if not frame.empty else pd.Series(dtype=float)
        listing_days = int(len(frame))
        avg_amount_20d = safe_float(frame["amount"].tail(20).mean(), 0.0) or 0.0
        avg_turnover_20d = safe_float(frame["turnover"].tail(20).mean())
        last_close = safe_float(latest.get("close"), 0.0) or 0.0
        vol_20 = safe_float(latest.get("realized_vol_20"), 0.0) or 0.0
        drawdown_60 = safe_float(latest.get("drawdown_60"), 0.0) or 0.0
        missing_ratio = _missing_ratio(frame)

        st_unverified = "未校验"
        st_flag = False
        if "ST" in entry["name"].upper():
            st_unverified = "命中名称"
            st_flag = True

        suspension_status = "未校验"
        if not frame.empty:
            last_date = frame["date"].max().date()
            delta_days = (pd.Timestamp(as_of_date).date() - last_date).days
            if delta_days > 10:
                suspension_status = "疑似停牌/长期无交易"

        price_ok = hard_cfg["price_range"]["min"] <= last_close <= hard_cfg["price_range"]["max"]
        listing_ok = listing_days >= hard_cfg["min_listing_days"]
        amount_ok = avg_amount_20d >= hard_cfg["min_avg_amount_20d"]
        turnover_ok = (
            avg_turnover_20d is None
            or avg_turnover_20d >= hard_cfg["min_avg_turnover_20d"] * 100
            or avg_turnover_20d >= hard_cfg["min_avg_turnover_20d"]
        )
        missing_ok = missing_ratio <= hard_cfg["max_missing_ratio"]
        volatility_ok = vol_20 <= hard_cfg["max_realized_volatility_20d"] if vol_20 else True
        st_ok = not (hard_cfg["exclude_st"] and st_flag)
        suspended_ok = not (hard_cfg["exclude_suspended"] and suspension_status == "疑似停牌/长期无交易")

        passed_hard_filters = all([price_ok, listing_ok, amount_ok, missing_ok, volatility_ok, st_ok, suspended_ok, turnover_ok])
        reasons: list[str] = []
        if not listing_ok:
            reasons.append(f"上市天数不足 {hard_cfg['min_listing_days']} 天")
        if not amount_ok:
            reasons.append("20日平均成交额不足")
        if not price_ok:
            reasons.append("当前价格超出允许区间")
        if not missing_ok:
            reasons.append("数据缺失率过高")
        if not volatility_ok:
            reasons.append("20日实现波动率过高")
        if not st_ok:
            reasons.append("名称命中 ST 风险")
        if not suspended_ok:
            reasons.append("疑似停牌或长期无交易")
        if avg_turnover_20d is None:
            reasons.append("换手率未校验")
        elif not turnover_ok:
            reasons.append("20日平均换手率不足")

        relative_strength = evaluate_relative_strength(
            frame,
            benchmark_frame,
            thresholds_config,
            entry["benchmark"],
            entry["benchmark"],
        )
        soft_factors = {
            "theme_relevance": entry.get("theme_score", 0.5),
            "liquidity_quality": _liquidity_quality(avg_amount_20d, hard_cfg["min_avg_amount_20d"]),
            "market_performance": max(
                0.0,
                min(1.0, ((relative_strength.get("return_diff_20d") or 0.0) + 0.12) / 0.24),
            ),
            "drawdown_quality": _drawdown_quality(drawdown_60),
            "volatility_quality": _volatility_quality(vol_20, hard_cfg["max_realized_volatility_20d"]),
            "concentration_penalty": max(
                0.0,
                min(1.0, 1 - max(0, sector_counter[entry["sector"]] - rules["concentration"]["max_total_recommended_per_sector"]) * 0.20),
            ),
        }
        soft_score = round(
            sum(soft_cfg["weights"][name] * safe_float(value, 0.0) for name, value in soft_factors.items()),
            4,
        )

        if entry["universe_type"] == "core_universe":
            if passed_hard_filters and soft_score >= soft_cfg["retain_threshold"]:
                suggestion = "保留核心"
            elif passed_hard_filters:
                suggestion = "核心保留但降权观察"
            else:
                suggestion = "核心保留但不满足当前可交易性"
        else:
            if passed_hard_filters and soft_score >= soft_cfg["promote_threshold"]:
                suggestion = "建议纳入观察"
            elif passed_hard_filters and soft_score >= soft_cfg["retain_threshold"]:
                suggestion = "继续跟踪"
            else:
                suggestion = "建议剔除"

        validation_flags = list(frame.attrs.get("validation_flags", []))
        if not st_flag:
            validation_flags.append("ST状态未校验")
        if suspension_status == "未校验":
            validation_flags.append("停牌状态未校验")

        record = {
            "code": entry["code"],
            "name": entry["name"],
            "universe_type": entry["universe_type"],
            "sector": entry["sector"],
            "subsector": entry["subsector"],
            "role": entry["role"],
            "passed_hard_filters": passed_hard_filters,
            "suggestion": suggestion,
            "reasons": reasons or ["通过可交易性检查"],
            "validation_flags": sorted(set(validation_flags)),
            "metrics": {
                "listing_days": listing_days,
                "last_close": round(last_close, 4),
                "avg_amount_20d": round(avg_amount_20d, 2),
                "avg_turnover_20d": round(avg_turnover_20d, 4) if avg_turnover_20d is not None else None,
                "realized_vol_20d": round(vol_20, 4),
                "drawdown_60d": round(drawdown_60, 4),
                "missing_ratio": missing_ratio,
                "st_status": "命中名称" if st_flag else st_unverified,
                "suspension_status": suspension_status,
                "relative_strength_20d": relative_strength.get("return_diff_20d"),
            },
            "soft_score": soft_score,
            "soft_factors": soft_factors,
        }
        records.append(record)

    frame = pd.DataFrame(
        [
            {
                "code": record["code"],
                "name": record["name"],
                "universe_type": record["universe_type"],
                "sector": record["sector"],
                "subsector": record["subsector"],
                "role": record["role"],
                "passed_hard_filters": record["passed_hard_filters"],
                "suggestion": record["suggestion"],
                "soft_score": record["soft_score"],
                "reasons": "；".join(record["reasons"]),
                "validation_flags": "；".join(record["validation_flags"]),
                **record["metrics"],
            }
            for record in records
        ]
    )
    return frame, records

