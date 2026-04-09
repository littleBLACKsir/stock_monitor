from __future__ import annotations

import argparse

from .utils import print_capability_summary
from .workflows import aggregate_reports, generate_analysis, review_metrics


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AI 股票研究 / 监控系统")
    subparsers = parser.add_subparsers(dest="command", required=True)

    generate_parser = subparsers.add_parser("generate-analysis", help="生成分析报告")
    generate_parser.add_argument("--date", required=False, help="报告日期，格式 YYYY-MM-DD")
    generate_parser.add_argument("--agent-name", default="local", help="AI 名称")
    generate_parser.add_argument("--vendor", default="local", help="AI 供应商")
    generate_parser.add_argument("--model", default="baseline", help="模型标识")
    generate_parser.add_argument("--toolchain", default="cli", help="工具链标识")
    generate_parser.add_argument(
        "--conflict-strategy",
        default="suffix",
        choices=["suffix", "overwrite", "error"],
        help="同名报告冲突处理策略",
    )

    aggregate_parser = subparsers.add_parser("aggregate-ai-reports", help="聚合多 AI 报告")
    aggregate_parser.add_argument("--date", required=True, help="报告日期，格式 YYYY-MM-DD")

    review_parser = subparsers.add_parser("review-metrics", help="生成周度复盘指标")
    review_parser.add_argument("--previous-date", required=False, help="上一期日期")
    review_parser.add_argument("--current-date", required=False, help="当前期日期")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "generate-analysis":
        result = generate_analysis(
            args.date,
            agent_name=args.agent_name,
            vendor=args.vendor,
            model=args.model,
            toolchain=args.toolchain,
            conflict_strategy=args.conflict_strategy,
        )
        print(f"分析报告已生成：{result['analysis_path']}")
        print(f"结构化 JSON：{result['analysis_json_path']}")
        print(f"股票池筛选：{result['universe_csv_path']}")
        print()
        print_capability_summary(result["data_source_status"])
        return 0

    if args.command == "aggregate-ai-reports":
        result = aggregate_reports(args.date)
        print(f"共识汇总已生成：{result['summary_markdown_path']}")
        print(f"结构化共识：{result['summary_json_path']}")
        print(f"冲突报告：{result['conflicts_markdown_path']}")
        print(f"冲突 JSON：{result['conflicts_json_path']}")
        print()
        print_capability_summary(result["data_source_status"])
        return 0

    if args.command == "review-metrics":
        result = review_metrics(args.previous_date, args.current_date)
        print(f"复盘指标已生成：{result['metrics_path']}")
        print(f"复盘摘要已生成：{result['review_path']}")
        print()
        print_capability_summary(result["data_source_status"])
        return 0

    parser.error("未知命令")
    return 2
