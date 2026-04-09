from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from itertools import combinations
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .config import ensure_report_dir, list_stock_entries, load_all_configs
from .data import get_ohlcv
from .indicators import (
    build_sector_context,
    determine_score_band,
    evaluate_confirmations,
    evaluate_relative_strength,
    prepare_indicator_frame,
    score_oversold_components,
)
from .reporting import (
    extract_payload_from_markdown,
    render_analysis_markdown,
    render_conflicts_markdown,
    render_consensus_markdown,
    render_review_markdown,
    validate_analysis_payload,
    validate_consensus_payload,
)
from .risk.rules import POSITIVE_ACTIONS, evaluate_trade_decision
from .universe import detect_market_regime, evaluate_universe
from .utils import (
    aggregate_data_source_status,
    build_analysis_stem,
    iso_date,
    json_dumps,
    latest_report_dates,
    parse_date,
    resolve_report_path,
    safe_float,
    slugify,
)


def _load_price_frames(
    entries: list[dict[str, Any]],
    market_context: dict[str, Any],
    thresholds: dict[str, Any],
    report_date: str,
) -> tuple[dict[tuple[str, str | None], pd.DataFrame], dict[tuple[str, str | None], pd.DataFrame], str]:
    history_days = thresholds["data_standard"]["min_history_days"] + 80
    start_date = iso_date(parse_date(report_date) - timedelta(days=history_days * 2))
    adjust = thresholds["data_standard"]["adjust"]

    price_frames: dict[tuple[str, str | None], pd.DataFrame] = {}
    benchmark_frames: dict[tuple[str, str | None], pd.DataFrame] = {}
    statuses: list[str] = []

    for entry in entries:
        key = (entry["code"], entry.get("exchange"))
        if key in price_frames:
            continue
        frame = get_ohlcv(entry["code"], start_date, report_date, adjust=adjust, exchange=entry.get("exchange"))
        price_frames[key] = frame
        statuses.append(frame.attrs.get("source_status", "unknown"))

    for benchmark_group in market_context["benchmarks"].values():
        for benchmark in benchmark_group:
            key = (benchmark["code"], benchmark.get("exchange"))
            if key in benchmark_frames:
                continue
            frame = get_ohlcv(benchmark["code"], start_date, report_date, adjust=adjust, exchange=benchmark.get("exchange"))
            benchmark_frames[key] = frame
            statuses.append(frame.attrs.get("source_status", "unknown"))

    for entry in entries:
        key = (entry["benchmark"], entry.get("benchmark_exchange"))
        if key not in benchmark_frames:
            frame = get_ohlcv(entry["benchmark"], start_date, report_date, adjust=adjust, exchange=entry.get("benchmark_exchange"))
            benchmark_frames[key] = frame
            statuses.append(frame.attrs.get("source_status", "unknown"))

    return price_frames, benchmark_frames, aggregate_data_source_status(statuses)


def _build_agent_meta(agent_name: str, vendor: str, model: str, toolchain: str, report_date: str) -> dict[str, str]:
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    run_id = f"{slugify(agent_name)}-{slugify(vendor)}-{slugify(model)}-{slugify(toolchain)}-{report_date}-{timestamp}"
    return {
        "name": slugify(agent_name),
        "vendor": slugify(vendor),
        "model": slugify(model),
        "toolchain": slugify(toolchain),
        "run_id": run_id,
    }


def _build_model_risk_notes(
    data_source_status: str,
    universe_records: list[dict[str, Any]],
    indicator_frames: dict[str, pd.DataFrame],
    thresholds_cfg: dict[str, Any],
) -> list[str]:
    notes: list[str] = []
    if "degraded" in data_source_status:
        notes.append("本次存在降级/示例数据，信号仅适合流程验证，不适合作为强结论。")
    elif "cache" in data_source_status:
        notes.append("本次部分数据来自本地缓存，需留意缓存是否覆盖最新交易日。")

    min_history = thresholds_cfg["data_standard"]["min_history_days"]
    insufficient = [code for code, frame in indicator_frames.items() if len(frame) < min_history]
    if insufficient:
        notes.append(f"以下股票历史样本不足 {min_history} 日，长周期统计稳定性下降：{', '.join(sorted(insufficient))}")

    latest_component_columns = ["rsi14", "bb_lower_distance", "ma20_deviation_atr", "drawdown_60"]
    unstable = [
        code
        for code, frame in indicator_frames.items()
        if frame.empty or any(pd.isna(frame.iloc[-1].get(column)) for column in latest_component_columns)
    ]
    if unstable:
        notes.append(f"以下股票在分析日存在主因子缺值，默认总分可能偏保守：{', '.join(sorted(unstable))}")

    notes.append("KDJ 与 volume_ratio 默认仅作提示或确认项，不进入默认总分，以减少强相关与参数过拟合。")

    unvalidated_flags = sorted(
        {
            flag
            for record in universe_records
            for flag in record.get("validation_flags", [])
            if "未校验" in flag or "ST状态" in flag or "停牌状态" in flag
        }
    )
    if unvalidated_flags:
        notes.append(f"以下字段存在未校验项：{'；'.join(unvalidated_flags)}。")
    return notes


def generate_analysis(
    report_date: str | None,
    agent_name: str = "local",
    vendor: str = "local",
    model: str = "baseline",
    toolchain: str = "cli",
    conflict_strategy: str = "suffix",
) -> dict[str, Any]:
    report_date = iso_date(report_date)
    configs = load_all_configs()
    stocks_cfg = configs["stocks"]
    thresholds_cfg = configs["thresholds"]
    risk_cfg = configs["risk_control"]
    market_cfg = configs["market_context"]
    events_cfg = configs["events_calendar"]

    entries = list_stock_entries(stocks_cfg)
    report_dir = ensure_report_dir(report_date)
    price_frames, benchmark_frames, data_source_status = _load_price_frames(entries, market_cfg, thresholds_cfg, report_date)
    market_state = detect_market_regime(benchmark_frames, market_cfg)

    universe_frame, universe_records = evaluate_universe(
        entries,
        price_frames,
        benchmark_frames,
        stocks_cfg,
        thresholds_cfg,
        report_date,
    )
    universe_lookup = {record["code"]: record for record in universe_records}
    liquidity_values = [record["metrics"]["avg_amount_20d"] for record in universe_records if record["passed_hard_filters"]]

    preliminary_records: list[dict[str, Any]] = []
    indicator_frames: dict[str, pd.DataFrame] = {}
    for entry in entries:
        key = (entry["code"], entry.get("exchange"))
        frame = prepare_indicator_frame(price_frames[key], thresholds_cfg)
        indicator_frames[entry["code"]] = frame
        benchmark_key = (entry["benchmark"], entry.get("benchmark_exchange"))
        relative_strength = evaluate_relative_strength(
            frame,
            benchmark_frames.get(benchmark_key),
            thresholds_cfg,
            entry["benchmark"],
            entry["benchmark"],
        )
        components, score_total = score_oversold_components(frame, thresholds_cfg, market_state["regime"])
        preliminary_records.append(
            {
                "code": entry["code"],
                "sector": entry["sector"],
                "passed_hard_filters": universe_lookup[entry["code"]]["passed_hard_filters"],
                "relative_strength": relative_strength,
                "oversold_score_total": score_total,
                "oversold_components": components,
            }
        )

    sector_context = build_sector_context(preliminary_records)
    model_risk_notes = _build_model_risk_notes(data_source_status, universe_records, indicator_frames, thresholds_cfg)
    per_stock: list[dict[str, Any]] = []
    warnings: list[str] = []

    for entry in entries:
        frame = indicator_frames[entry["code"]]
        universe_record = universe_lookup[entry["code"]]
        preliminary = next(item for item in preliminary_records if item["code"] == entry["code"])
        confirmations, confirmation_pass = evaluate_confirmations(frame, thresholds_cfg, sector_context.get(entry["sector"], {}))

        source_status = price_frames[(entry["code"], entry.get("exchange"))].attrs.get("source_status", "unknown")
        meta_for_risk = {
            "code": entry["code"],
            "role": entry["role"],
            "oversold_score_total": preliminary["oversold_score_total"],
            "confirmation_pass": confirmation_pass,
            "relative_strength": preliminary["relative_strength"],
            "meta": {"data_source_status": source_status},
        }
        decision = evaluate_trade_decision(
            meta_for_risk,
            universe_record,
            frame,
            risk_cfg,
            events_cfg,
            market_state["regime"],
            report_date,
            liquidity_values,
        )

        latest = frame.iloc[-1]
        notes = []
        if source_status == "degraded":
            notes.append("OHLCV 数据使用降级示例数据。")
            warnings.append(f"{entry['name']} 使用降级数据。")
        elif source_status == "cache":
            notes.append("OHLCV 数据来自本地缓存。")
        notes.extend(universe_record["validation_flags"])
        if not thresholds_cfg["confirmations"]["volume_confirmation"]["enabled"]:
            notes.append("volume_confirmation 默认为可选提示项，未参与确认通过计数。")
        notes.append("KDJ 默认未纳入总分。")

        stock_payload = {
            "code": entry["code"],
            "name": entry["name"],
            "universe_type": entry["universe_type"],
            "sector": entry["sector"],
            "subsector": entry["subsector"],
            "role": entry["role"],
            "benchmark": entry["benchmark"],
            "benchmark_name": entry["benchmark"],
            "oversold_score_total": preliminary["oversold_score_total"],
            "oversold_components": preliminary["oversold_components"],
            "confirmation_pass": confirmation_pass,
            "confirmations": confirmations,
            "relative_strength": preliminary["relative_strength"],
            "risk_flags": decision["risk_flags"],
            "action": decision["action"],
            "invalidation_conditions": decision["invalidation_conditions"],
            "confidence": "unknown",
            "notes": sorted(set(notes)),
            "data_quality": {
                "data_source_status": source_status,
                "missing_ratio": universe_record["metrics"]["missing_ratio"],
                "score_band": determine_score_band(preliminary["oversold_score_total"], thresholds_cfg),
            },
            "tradeability": {
                "passed_hard_filters": universe_record["passed_hard_filters"],
                "avg_amount_20d": universe_record["metrics"]["avg_amount_20d"],
                "avg_turnover_20d": universe_record["metrics"]["avg_turnover_20d"],
                "listing_days": universe_record["metrics"]["listing_days"],
                "last_close": universe_record["metrics"]["last_close"],
                "suspension_status": universe_record["metrics"]["suspension_status"],
                "st_status": universe_record["metrics"]["st_status"],
                "pct_change": float(latest.get("pct_change", 0.0) or 0.0),
                "deprecated_default_off": ["kdj", "volume_ratio"],
            },
            "pre_trade_checklist": decision["pre_trade_checklist"],
            "trade_plan": decision["trade_plan"],
        }
        per_stock.append(stock_payload)

    agent_meta = _build_agent_meta(agent_name, vendor, model, toolchain, report_date)
    payload = {
        "meta": {
            "date": report_date,
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "agent": agent_meta,
            "theme": stocks_cfg["meta"]["theme"],
            "market_regime": market_state["regime"],
            "macro_score": market_state.get("macro_score"),
            "data_standard": {
                "frequency": thresholds_cfg["data_standard"]["frequency"],
                "adjust": thresholds_cfg["data_standard"]["adjust"],
                "price_field": thresholds_cfg["data_standard"]["price_field"],
                "benchmark_price_field": thresholds_cfg["data_standard"]["benchmark_price_field"],
                "data_source_status": data_source_status,
                "validation_notes": thresholds_cfg["data_sources"]["validation_notes"],
            },
            "warnings": sorted(set(warnings)),
        },
        "model_risk": {"overfitting_risk_notes": model_risk_notes},
        "universe": [
            {
                "code": item["code"],
                "name": item["name"],
                "universe_type": item["universe_type"],
                "sector": item["sector"],
                "subsector": item["subsector"],
                "role": item["role"],
                "passed_hard_filters": item["passed_hard_filters"],
                "suggestion": item["suggestion"],
                "reasons": item["reasons"],
                "validation_flags": item["validation_flags"],
                "metrics": item["metrics"],
            }
            for item in universe_records
        ],
        "per_stock": per_stock,
        "summary": {
            "market_notes": market_state["notes"],
            "small_trial_candidates": [item["code"] for item in per_stock if item["action"] == "满足条件可小仓试错"],
            "watch_candidates": [item["code"] for item in per_stock if item["action"] == "观察"],
            "reject_candidates": [item["code"] for item in per_stock if item["action"] in {"观望", "不符合策略"}],
            "counts_by_action": dict(Counter(item["action"] for item in per_stock)),
            "data_source_status": data_source_status,
            "default_components": thresholds_cfg["oversold_scoring"]["default_components"],
        },
    }
    validated = validate_analysis_payload(payload)
    payload = validated.model_dump()

    stem = build_analysis_stem(agent_meta["name"], agent_meta["vendor"], agent_meta["model"])
    analysis_path = resolve_report_path(report_dir, stem, conflict_strategy=conflict_strategy)
    analysis_path.write_text(render_analysis_markdown(payload), encoding="utf-8")
    (report_dir / "analysis-data.json").write_text(json_dumps(payload), encoding="utf-8")
    universe_frame.to_csv(report_dir / "universe-selection.csv", index=False, encoding="utf-8-sig")

    return {
        "report_dir": report_dir,
        "analysis_path": analysis_path,
        "analysis_json_path": report_dir / "analysis-data.json",
        "universe_csv_path": report_dir / "universe-selection.csv",
        "data_source_status": data_source_status,
    }


def _jaccard_similarity(items: list[set[str]]) -> float:
    if not items:
        return 1.0
    scores: list[float] = []
    for left, right in combinations(items, 2):
        union = left | right
        scores.append(1.0 if not union else len(left & right) / len(union))
    return float(np.mean(scores)) if scores else 1.0


def _agreement_score(items: list[dict[str, Any]]) -> tuple[float, list[str]]:
    reasons: list[str] = []
    action_counter = Counter(item["action"] for item in items)
    action_agreement = max(action_counter.values()) / len(items)

    confirmation_pass_counter = Counter(item["confirmation_pass"] for item in items)
    confirmation_pass_agreement = max(confirmation_pass_counter.values()) / len(items)
    if len(confirmation_pass_counter) > 1:
        reasons.append("confirmation_pass 分歧")

    key_confirmation_names = ["trend_reversal", "price_reclaim", "volume_confirmation", "sector_resonance"]
    confirmation_scores: list[float] = []
    for name in key_confirmation_names:
        values = [item["confirmations"][name]["passed"] for item in items if name in item["confirmations"]]
        if not values:
            continue
        counter = Counter(values)
        agreement = max(counter.values()) / len(values)
        confirmation_scores.append(agreement)
        if len(counter) > 1:
            reasons.append(f"{name} 分歧")
    confirmation_agreement = float(np.mean(confirmation_scores)) if confirmation_scores else 1.0

    risk_sets = [set(item["risk_flags"]) for item in items]
    risk_similarity = _jaccard_similarity(risk_sets)
    if len({tuple(sorted(value)) for value in risk_sets}) > 1:
        reasons.append("risk_flags 分歧")

    invalidation_sets = [set(item["invalidation_conditions"]) for item in items]
    invalidation_similarity = _jaccard_similarity(invalidation_sets)
    if len({tuple(sorted(value)) for value in invalidation_sets}) > 1:
        reasons.append("invalidation_conditions 分歧")

    if len(action_counter) > 1:
        reasons.append("action 分歧")

    score = 100 * (
        0.40 * action_agreement
        + 0.20 * confirmation_pass_agreement
        + 0.20 * confirmation_agreement
        + 0.10 * risk_similarity
        + 0.10 * invalidation_similarity
    )
    return round(score, 2), sorted(set(reasons))


def _strip_suffix(stem: str) -> str:
    return re.sub(r"-\d+$", "", stem)


def aggregate_reports(report_date: str) -> dict[str, Any]:
    report_dir = ensure_report_dir(report_date)
    report_paths = sorted(report_dir.glob("*analysis*.md"))
    if not report_paths:
        raise FileNotFoundError(f"{report_dir} 下没有可聚合的分析报告。")

    participant_payloads: list[dict[str, Any]] = []
    participants: list[str] = []
    filename_stem_groups: defaultdict[str, list[str]] = defaultdict(list)
    meta_groups: defaultdict[tuple[str, ...], list[str]] = defaultdict(list)
    conflicts = {
        "date": report_date,
        "filename_conflicts": [],
        "meta_duplicates": [],
        "json_validation_failures": [],
        "missing_meta_fields": [],
    }

    for path in report_paths:
        filename_stem_groups[_strip_suffix(path.stem)].append(path.name)
        try:
            raw_payload = extract_payload_from_markdown(path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            conflicts["json_validation_failures"].append(f"{path.name}: 无法提取 JSON 区块（{exc}）")
            continue

        meta = raw_payload.get("meta", {})
        agent = meta.get("agent", {})
        missing_fields = [
            field
            for field, value in {
                "meta.date": meta.get("date"),
                "meta.agent.name": agent.get("name"),
                "meta.agent.vendor": agent.get("vendor"),
                "meta.agent.model": agent.get("model"),
                "meta.agent.toolchain": agent.get("toolchain"),
                "meta.agent.run_id": agent.get("run_id"),
            }.items()
            if not value
        ]
        if missing_fields:
            conflicts["missing_meta_fields"].append(f"{path.name}: 缺少 {', '.join(missing_fields)}")
            continue

        try:
            validated = validate_analysis_payload(raw_payload)
        except Exception as exc:  # noqa: BLE001
            conflicts["json_validation_failures"].append(f"{path.name}: schema 校验失败（{exc}）")
            continue

        payload = validated.model_dump()
        expected_stem = build_analysis_stem(
            payload["meta"]["agent"]["name"],
            payload["meta"]["agent"]["vendor"],
            payload["meta"]["agent"]["model"],
        )
        if not _strip_suffix(path.stem).startswith(expected_stem):
            conflicts["filename_conflicts"].append(f"{path.name}: 文件名与 meta 不一致，期望前缀 {expected_stem}")

        meta_key = (
            payload["meta"]["date"],
            payload["meta"]["agent"]["name"],
            payload["meta"]["agent"]["vendor"],
            payload["meta"]["agent"]["model"],
            payload["meta"]["agent"]["toolchain"],
        )
        meta_groups[meta_key].append(path.name)
        participant_key = (
            f"{payload['meta']['agent']['name']}/"
            f"{payload['meta']['agent']['vendor']}/"
            f"{payload['meta']['agent']['model']}"
        )
        if len(meta_groups[meta_key]) > 1:
            continue
        participant_payloads.append({"filename": path.name, **payload})
        participants.append(participant_key)

    for stem, files in filename_stem_groups.items():
        if len(files) > 1:
            conflicts["filename_conflicts"].append(f"{stem}: 检测到多份同名族报告 -> {', '.join(sorted(files))}")
    for meta_key, files in meta_groups.items():
        if len(files) > 1:
            conflicts["meta_duplicates"].append(f"{' | '.join(meta_key)}: {', '.join(sorted(files))}")

    if not participant_payloads:
        conflicts_json_path = report_dir / "conflicts.json"
        conflicts_markdown_path = report_dir / "conflicts.md"
        conflicts_json_path.write_text(json_dumps(conflicts), encoding="utf-8")
        conflicts_markdown_path.write_text(render_conflicts_markdown(conflicts), encoding="utf-8")
        raise ValueError("没有找到可用于聚合的有效结构化分析报告，请先修复 conflicts.md 中的问题。")

    stock_views: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for payload in participant_payloads:
        participant = payload["meta"]["agent"]["name"]
        for stock in payload["per_stock"]:
            stock_views[stock["code"]].append({"participant": participant, **stock})

    consensus_items: list[dict[str, Any]] = []
    divergence_items: list[dict[str, Any]] = []
    for code, items in stock_views.items():
        action_counter = Counter(item["action"] for item in items)
        exact_action, exact_match_count = action_counter.most_common(1)[0]
        positive_votes = sum(item["action"] in POSITIVE_ACTIONS for item in items)
        negative_votes = len(items) - positive_votes
        agreement_score, disagreement_reasons = _agreement_score(items)

        if exact_match_count >= 2 or positive_votes >= 2 or negative_votes >= 2:
            consensus_action = exact_action if exact_match_count >= 2 else "正向共识" if positive_votes >= 2 else "负向共识"
            consensus_items.append(
                {
                    "code": code,
                    "name": items[0]["name"],
                    "sector": items[0]["sector"],
                    "consensus_action": consensus_action,
                    "positive_votes": positive_votes,
                    "negative_votes": negative_votes,
                    "exact_match_count": exact_match_count,
                    "participants": [item["participant"] for item in items],
                    "agreement_score": agreement_score,
                    "disagreement_reasons": disagreement_reasons,
                }
            )

        if disagreement_reasons or len(action_counter) > 1:
            divergence_items.append(
                {
                    "code": code,
                    "name": items[0]["name"],
                    "sector": items[0]["sector"],
                    "actions": {item["participant"]: item["action"] for item in items},
                    "agreement_score": agreement_score,
                    "disagreement_reasons": disagreement_reasons or ["暂无额外分歧说明"],
                }
            )

    consensus_payload = {
        "meta": {
            "date": report_date,
            "participants": participants,
        },
        "consensus": consensus_items,
        "divergences": divergence_items,
        "summary": {
            "participant_count": len(participants),
            "consensus_count": len(consensus_items),
            "divergence_count": len(divergence_items),
        },
    }
    validated = validate_consensus_payload(consensus_payload)
    consensus_payload = validated.model_dump()

    summary_markdown_path = report_dir / "consensus-summary.md"
    summary_json_path = report_dir / "consensus-summary.json"
    conflicts_markdown_path = report_dir / "conflicts.md"
    conflicts_json_path = report_dir / "conflicts.json"

    summary_markdown_path.write_text(render_consensus_markdown(consensus_payload), encoding="utf-8")
    summary_json_path.write_text(json_dumps(consensus_payload), encoding="utf-8")
    conflicts_markdown_path.write_text(render_conflicts_markdown(conflicts), encoding="utf-8")
    conflicts_json_path.write_text(json_dumps(conflicts), encoding="utf-8")

    return {
        "summary_markdown_path": summary_markdown_path,
        "summary_json_path": summary_json_path,
        "conflicts_markdown_path": conflicts_markdown_path,
        "conflicts_json_path": conflicts_json_path,
        "data_source_status": "derived",
    }


def _load_previous_payload(report_dir: Path) -> dict[str, Any]:
    json_path = report_dir / "analysis-data.json"
    if json_path.exists():
        return json.loads(json_path.read_text(encoding="utf-8"))
    markdown_candidates = sorted(report_dir.glob("*analysis*.md"))
    if not markdown_candidates:
        raise FileNotFoundError(f"{report_dir} 下缺少 analysis-data.json 或 markdown 报告。")
    return extract_payload_from_markdown(markdown_candidates[0].read_text(encoding="utf-8"))


def review_metrics(previous_date: str | None = None, current_date: str | None = None) -> dict[str, Any]:
    if not previous_date or not current_date:
        dates = latest_report_dates(limit=2)
        if len(dates) < 2:
            raise ValueError("自动复盘需要至少两个 reports/YYYY-MM-DD 目录。")
        previous_date, current_date = dates[-2], dates[-1]

    previous_dir = ensure_report_dir(previous_date)
    current_dir = ensure_report_dir(current_date)
    previous_payload = _load_previous_payload(previous_dir)
    configs = load_all_configs()
    thresholds_cfg = configs["thresholds"]
    holding_periods = thresholds_cfg["review"]["holding_periods"]
    hit_threshold = thresholds_cfg["review"]["hit_threshold"]
    max_horizon = max(holding_periods)
    adjust = thresholds_cfg["data_standard"]["adjust"]

    rows: list[dict[str, Any]] = []
    statuses: list[str] = []
    candidates = [item for item in previous_payload["per_stock"] if item["action"] in POSITIVE_ACTIONS]
    if not candidates:
        universe_candidates = {
            item["code"]
            for item in previous_payload.get("universe", [])
            if item["suggestion"] in {"建议纳入观察", "继续跟踪", "核心保留但降权观察"}
        }
        candidates = [item for item in previous_payload["per_stock"] if item["code"] in universe_candidates]
    for stock in candidates:
        start_date = iso_date(parse_date(previous_date) - timedelta(days=60))
        frame = get_ohlcv(stock["code"], start_date, current_date, adjust=adjust, exchange=None)
        statuses.append(frame.attrs.get("source_status", "unknown"))
        frame = frame.sort_values("date").reset_index(drop=True)
        eligible = frame[frame["date"] <= pd.Timestamp(previous_date)]
        if eligible.empty:
            continue
        entry_index = int(eligible.index[-1])
        entry_close = float(frame.loc[entry_index, "close"])

        row: dict[str, Any] = {
            "report_date": previous_date,
            "evaluation_date": current_date,
            "code": stock["code"],
            "name": stock["name"],
            "action": stock["action"],
            "confirmation_pass": stock["confirmation_pass"],
            "entry_close": round(entry_close, 4),
        }
        max_end_index = min(len(frame) - 1, entry_index + max_horizon)
        path = frame.loc[entry_index:max_end_index, "close"].reset_index(drop=True)
        running_max = path.cummax()
        row["max_drawdown_to_date"] = round(float((path / running_max - 1).min()), 4)

        for horizon in holding_periods:
            target_index = entry_index + horizon
            return_key = f"return_{horizon}d"
            hit_key = f"hit_{horizon}d"
            if target_index < len(frame):
                target_close = float(frame.loc[target_index, "close"])
                result = target_close / entry_close - 1
                row[return_key] = round(result, 4)
                row[hit_key] = result >= hit_threshold
            else:
                row[return_key] = None
                row[hit_key] = None
        rows.append(row)

    metrics_path = current_dir / "review-metrics.csv"
    review_path = current_dir / "review.md"
    rows_frame = pd.DataFrame(rows)
    if rows_frame.empty:
        rows_frame = pd.DataFrame(columns=["report_date", "evaluation_date", "code", "name", "action", "confirmation_pass"])
    rows_frame.to_csv(metrics_path, index=False, encoding="utf-8-sig")

    def _mean_or_na(series_name: str, group_frame: pd.DataFrame) -> str:
        if series_name not in group_frame or group_frame[series_name].dropna().empty:
            return "n/a"
        return f"{group_frame[series_name].dropna().mean():.2%}"

    confirmed = rows_frame[rows_frame.get("confirmation_pass", False) == True]  # noqa: E712
    unconfirmed = rows_frame[rows_frame.get("confirmation_pass", False) == False]  # noqa: E712
    summary = {
        "sample_count": int(len(rows_frame)),
        "hit_rate_5d": _mean_or_na("hit_5d", rows_frame),
        "avg_return_10d": _mean_or_na("return_10d", rows_frame),
        "confirmed_hit_rate_5d": _mean_or_na("hit_5d", confirmed),
        "unconfirmed_hit_rate_5d": _mean_or_na("hit_5d", unconfirmed),
    }
    review_path.write_text(render_review_markdown(summary, rows, previous_date, current_date), encoding="utf-8")
    return {
        "metrics_path": metrics_path,
        "review_path": review_path,
        "data_source_status": aggregate_data_source_status(statuses),
    }
