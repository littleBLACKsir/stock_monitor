from __future__ import annotations

import json
import re
from typing import Any

from ..utils import (
    CONSENSUS_MARKER_END,
    CONSENSUS_MARKER_START,
    REPORT_MARKER_END,
    REPORT_MARKER_START,
    json_dumps,
)


def _table_row(values: list[Any]) -> str:
    return "| " + " | ".join(str(value) for value in values) + " |"


def render_analysis_markdown(payload: dict[str, Any]) -> str:
    meta = payload["meta"]
    lines = [
        "# AI 算力产业链分析报告",
        "",
        f"**分析日期**：{meta['date']}",
        f"**分析 AI**：{meta['agent']['name']}",
        f"**供应商 / 模型**：{meta['agent']['vendor']} / {meta['agent']['model']}",
        f"**工具链**：{meta['agent']['toolchain']}",
        f"**运行标识**：{meta['agent']['run_id']}",
        f"**市场环境**：{meta['market_regime']}",
        (
            f"**数据口径**：{meta['data_standard']['frequency']} / {meta['data_standard']['adjust']} / "
            f"{meta['data_standard']['price_field']}"
        ),
        f"**数据源状态**：{meta['data_standard']['data_source_status']}",
        "",
        "## 一、模型风险提示",
        *[f"- {note}" for note in payload["model_risk"]["overfitting_risk_notes"]],
        "",
        "## 二、股票池筛选摘要",
        "",
        _table_row(["股票", "池类型", "是否通过", "建议", "关键原因"]),
        _table_row(["---", "---", "---", "---", "---"]),
    ]

    for item in payload["universe"]:
        lines.append(
            _table_row(
                [
                    f"{item['name']}({item['code']})",
                    item["universe_type"],
                    "是" if item["passed_hard_filters"] else "否",
                    item["suggestion"],
                    "；".join(item["reasons"][:2]),
                ]
            )
        )

    lines.extend(["", "## 三、重点股票", ""])
    for stock in payload["per_stock"]:
        lines.extend(
            [
                f"### {stock['name']} ({stock['code']})",
                "",
                f"- 所属赛道：{stock['sector']} / {stock['subsector']}",
                f"- 超跌总分：**{stock['oversold_score_total']}**",
                f"- 确认信号：{'通过' if stock['confirmation_pass'] else '未通过'}",
                (
                    f"- 相对强弱：{stock['relative_strength']['signal']} "
                    f"(20日超额={stock['relative_strength'].get('return_diff_20d')}, "
                    f"5日超额={stock['relative_strength'].get('return_diff_5d')})"
                ),
                f"- 风险旗标：{', '.join(stock['risk_flags']) if stock['risk_flags'] else '无'}",
                f"- 最终动作：**{stock['action']}**",
                f"- 否证条件：{'；'.join(stock['invalidation_conditions'])}",
                "",
                _table_row(["组件", "原始值", "分数", "说明"]),
                _table_row(["---", "---", "---", "---"]),
            ]
        )
        for name, component in stock["oversold_components"].items():
            lines.append(
                _table_row([name, component.get("raw_value"), component.get("score"), component.get("explanation")])
            )

        lines.extend(["", _table_row(["确认项", "是否通过", "关键值", "逻辑"]), _table_row(["---", "---", "---", "---"])])
        for name, confirmation in stock["confirmations"].items():
            raw_value = json_dumps(confirmation["raw_value"]).replace("\n", "")
            logic = confirmation["threshold"].get("logic", confirmation["explanation"])
            lines.append(_table_row([name, "是" if confirmation["passed"] else "否", raw_value, logic]))

        lines.extend(["", _table_row(["检查项", "结果"]), _table_row(["---", "---"])])
        for check_name, check_value in stock["pre_trade_checklist"].items():
            lines.append(_table_row([check_name, "通过" if check_value else "未通过"]))
        lines.append("")

    lines.extend(
        [
            "## 四、汇总",
            "",
            f"- 满足条件可小仓试错：{payload['summary'].get('small_trial_candidates', [])}",
            f"- 观察：{payload['summary'].get('watch_candidates', [])}",
            f"- 观望 / 不符合策略：{payload['summary'].get('reject_candidates', [])}",
            "",
            REPORT_MARKER_START,
            "```json",
            json_dumps(payload),
            "```",
            REPORT_MARKER_END,
            "",
        ]
    )
    return "\n".join(lines)


def extract_payload_from_markdown(markdown_text: str) -> dict[str, Any]:
    pattern = re.compile(
        rf"{re.escape(REPORT_MARKER_START)}\s*```json\s*(\{{.*?\}})\s*```\s*{re.escape(REPORT_MARKER_END)}",
        re.DOTALL,
    )
    match = pattern.search(markdown_text)
    if not match:
        raise ValueError("未找到 REPORT_PAYLOAD JSON 区块。")
    return json.loads(match.group(1))


def render_consensus_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# 多 AI 共识汇总",
        "",
        f"**分析日期**：{payload['meta']['date']}",
        f"**参与方**：{', '.join(payload['meta'].get('participants', [])) or '无'}",
        "",
        "## 一、共识名单",
        "",
        _table_row(["股票", "赛道", "共识动作", "一致度", "分歧原因"]),
        _table_row(["---", "---", "---", "---", "---"]),
    ]
    for item in payload["consensus"]:
        lines.append(
            _table_row(
                [
                    f"{item['name']}({item['code']})",
                    item["sector"],
                    item["consensus_action"],
                    f"{item['agreement_score']:.1f}",
                    "；".join(item["disagreement_reasons"]) or "-",
                ]
            )
        )

    lines.extend(["", "## 二、分歧名单", "", _table_row(["股票", "动作分布", "一致度", "分歧点"]), _table_row(["---", "---", "---", "---"])])
    for item in payload["divergences"]:
        action_text = "；".join(f"{name}:{action}" for name, action in item["actions"].items())
        lines.append(
            _table_row([f"{item['name']}({item['code']})", action_text, f"{item['agreement_score']:.1f}", "；".join(item["disagreement_reasons"])])
        )

    lines.extend(
        [
            "",
            CONSENSUS_MARKER_START,
            "```json",
            json_dumps(payload),
            "```",
            CONSENSUS_MARKER_END,
            "",
        ]
    )
    return "\n".join(lines)


def render_conflicts_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# 报告冲突与校验异常",
        "",
        f"**分析日期**：{payload['date']}",
        "",
        "## 一、冲突摘要",
        f"- 文件名冲突：{len(payload['filename_conflicts'])}",
        f"- 元数据重复：{len(payload['meta_duplicates'])}",
        f"- JSON 校验失败：{len(payload['json_validation_failures'])}",
        f"- 缺字段：{len(payload['missing_meta_fields'])}",
        "",
    ]
    sections = [
        ("文件名冲突", payload["filename_conflicts"]),
        ("元数据重复", payload["meta_duplicates"]),
        ("JSON 校验失败", payload["json_validation_failures"]),
        ("缺字段", payload["missing_meta_fields"]),
    ]
    for title, items in sections:
        lines.extend([f"## {title}", ""])
        if not items:
            lines.append("- 无")
            lines.append("")
            continue
        for item in items:
            lines.append(f"- {item}")
        lines.append("")
    return "\n".join(lines)


def render_review_markdown(summary: dict[str, Any], rows: list[dict[str, Any]], previous_date: str, current_date: str) -> str:
    lines = [
        "# 周度复盘",
        "",
        f"**上一期**：{previous_date}",
        f"**当前期**：{current_date}",
        "",
        "## 一、统计摘要",
        f"- 样本数量：{summary.get('sample_count', 0)}",
        f"- 5日命中率：{summary.get('hit_rate_5d', 'n/a')}",
        f"- 10日平均收益：{summary.get('avg_return_10d', 'n/a')}",
        f"- 确认通过组 5 日命中率：{summary.get('confirmed_hit_rate_5d', 'n/a')}",
        f"- 未确认组 5 日命中率：{summary.get('unconfirmed_hit_rate_5d', 'n/a')}",
        "",
        "## 二、样本明细",
        "",
        _table_row(["股票", "动作", "确认通过", "1D", "5D", "10D", "20D", "最大回撤"]),
        _table_row(["---", "---", "---", "---", "---", "---", "---", "---"]),
    ]
    for row in rows:
        lines.append(
            _table_row(
                [
                    f"{row['name']}({row['code']})",
                    row["action"],
                    "是" if row["confirmation_pass"] else "否",
                    row.get("return_1d"),
                    row.get("return_5d"),
                    row.get("return_10d"),
                    row.get("return_20d"),
                    row.get("max_drawdown_to_date"),
                ]
            )
        )
    return "\n".join(lines) + "\n"
