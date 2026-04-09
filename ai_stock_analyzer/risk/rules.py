from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import numpy as np

from ..utils import clamp


POSITIVE_ACTIONS = {"观察", "满足条件可小仓试错"}


def _percentile(values: Iterable[float], target: float) -> float:
    clean = sorted(value for value in values if value is not None)
    if not clean:
        return 0.5
    return sum(value <= target for value in clean) / len(clean)


def _liquidity_multiplier(percentile: float, risk_config: dict[str, Any]) -> float:
    breaks = risk_config["position_management"]["liquidity_adjustment"]["amount_percentile_breaks"]
    multipliers = risk_config["position_management"]["liquidity_adjustment"]["multipliers"]
    if percentile <= breaks[0]:
        return multipliers[0]
    if percentile <= breaks[1]:
        return multipliers[1]
    if percentile <= breaks[2]:
        return multipliers[2]
    return multipliers[3]


def _earnings_blackout(code: str, report_date: str, events_config: dict[str, Any]) -> bool:
    report_ts = np.datetime64(report_date)
    days_before = events_config["earnings_blackout"]["days_before"]
    days_after = events_config["earnings_blackout"]["days_after"]
    for event in events_config.get("company_events", []):
        if event.get("code") != code:
            continue
        event_ts = np.datetime64(event["date"])
        if event_ts - np.timedelta64(days_before, "D") <= report_ts <= event_ts + np.timedelta64(days_after, "D"):
            return True
    return False


def evaluate_trade_decision(
    stock: dict[str, Any],
    universe_record: dict[str, Any],
    indicator_frame,
    risk_config: dict[str, Any],
    events_config: dict[str, Any],
    market_regime: str,
    report_date: str,
    liquidity_values: list[float],
) -> dict[str, Any]:
    latest = indicator_frame.iloc[-1]
    avg_amount = universe_record["metrics"]["avg_amount_20d"]
    percentile = _percentile(liquidity_values, avg_amount)
    role_limits = risk_config["position_management"]["role_limits"][stock["role"]]
    regime_multiplier = risk_config["position_management"]["market_regime_multipliers"].get(market_regime, 1.0)
    liquidity_multiplier = _liquidity_multiplier(percentile, risk_config)

    suggested_position = min(
        role_limits["recommended"] * liquidity_multiplier * regime_multiplier,
        role_limits["max"] * regime_multiplier,
    )
    suggested_position = round(float(suggested_position), 4)

    atr_cfg = risk_config["stop_loss"]["atr"]
    atr_value = float(latest.get(f"atr{atr_cfg['period']}", latest.get("atr14", 0.0)) or 0.0)
    close = float(latest["close"])
    atr_pct = clamp(atr_cfg["multiplier"] * atr_value / max(close, 1e-6), atr_cfg["floor_pct"], atr_cfg["cap_pct"])
    stop_loss_pct = atr_pct if risk_config["stop_loss"]["primary_mode"] == "atr" else risk_config["stop_loss"]["fixed_pct"]
    stop_loss_price = round(close * (1 - stop_loss_pct), 4)

    risk_flags: list[str] = []
    if latest.get("trend_down"):
        risk_flags.append("trend_down")
    if universe_record["metrics"]["suspension_status"] != "未校验":
        risk_flags.append("suspension_risk")
    if universe_record["metrics"]["avg_amount_20d"] < 1.2 * 80_000_000:
        risk_flags.append("liquidity_thin")
    if abs(float(latest.get("pct_change", 0.0) or 0.0)) >= 9.5 and abs(float(latest.get("high", 0.0) - latest.get("low", 0.0))) < 1e-6:
        risk_flags.append("one_word_board")
    if stock["relative_strength"]["signal"] == "超跌但仍弱":
        risk_flags.append("relative_strength_weak")
    if stock["meta"]["data_source_status"] == "degraded":
        risk_flags.append("data_source_degraded")
    if _earnings_blackout(stock["code"], report_date, events_config):
        risk_flags.append("earnings_blackout")

    checklist = {
        "universe_hard_filters": bool(universe_record["passed_hard_filters"]),
        "data_quality_ok": stock["meta"]["data_source_status"] != "degraded" and universe_record["metrics"]["missing_ratio"] <= 0.10,
        "confirmation_pass": bool(stock["confirmation_pass"]),
        "liquidity_ok": universe_record["metrics"]["avg_amount_20d"] >= 80_000_000,
        "no_earnings_blackout": "earnings_blackout" not in risk_flags,
    }

    action_cfg = risk_config["action_mapping"]
    hard_reject = any(flag in risk_flags for flag in action_cfg["reject_on_flags"])
    all_required = all(checklist[name] for name in risk_config["pre_trade_checklist"]["must_pass"])

    if not universe_record["passed_hard_filters"]:
        action = "不符合策略"
    elif hard_reject:
        action = "观望"
    elif (
        stock["oversold_score_total"] >= action_cfg["small_trial"]["min_oversold_score"]
        and stock["confirmation_pass"]
        and len(risk_flags) <= action_cfg["small_trial"]["max_blocking_risk_flags"]
        and all_required
    ):
        action = "满足条件可小仓试错"
    elif stock["oversold_score_total"] >= action_cfg["observe"]["min_oversold_score"]:
        action = "观察"
    else:
        action = "观望"

    invalidation_conditions = [
        f"收盘跌破止损价 {stop_loss_price}",
        "重新跌破近5日低点且 trend_reversal 再度失效",
        "相对强弱由中性/转强重新恶化为超跌但仍弱",
    ]
    if "earnings_blackout" in risk_flags:
        invalidation_conditions.append("财报窗口风险未释放")

    return {
        "action": action,
        "risk_flags": sorted(set(risk_flags)),
        "pre_trade_checklist": checklist,
        "trade_plan": {
            "suggested_position_pct": suggested_position,
            "stop_loss_pct": round(stop_loss_pct, 4),
            "stop_loss_price": stop_loss_price,
            "batches": risk_config["entry_management"]["batches"],
        },
        "invalidation_conditions": invalidation_conditions,
    }

