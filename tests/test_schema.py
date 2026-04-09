from __future__ import annotations

import unittest

from ai_stock_analyzer.reporting.schema import validate_analysis_payload


class SchemaTests(unittest.TestCase):
    def test_analysis_payload_schema_validation(self) -> None:
        payload = {
            "meta": {
                "date": "2026-04-10",
                "generated_at": "2026-04-10T08:00:00",
                "agent": {
                    "name": "test",
                    "vendor": "github",
                    "model": "gpt41",
                    "toolchain": "copilot-cli",
                    "run_id": "test-github-gpt41-copilot-cli-20260410080000",
                },
                "theme": "AI算力产业链",
                "market_regime": "neutral",
                "macro_score": 0.1,
                "data_standard": {
                    "frequency": "daily",
                    "adjust": "qfq",
                    "price_field": "close",
                    "benchmark_price_field": "close",
                    "data_source_status": "real",
                    "validation_notes": [],
                },
                "warnings": [],
            },
            "model_risk": {
                "overfitting_risk_notes": ["KDJ 默认不进入总分"]
            },
            "universe": [
                {
                    "code": "300474",
                    "name": "景嘉微",
                    "universe_type": "core_universe",
                    "sector": "AI芯片",
                    "subsector": "GPU/军工芯片",
                    "role": "sub_leader",
                    "passed_hard_filters": True,
                    "suggestion": "保留核心",
                    "reasons": ["通过可交易性检查"],
                    "validation_flags": [],
                    "metrics": {"listing_days": 250},
                }
            ],
            "per_stock": [
                {
                    "code": "300474",
                    "name": "景嘉微",
                    "universe_type": "core_universe",
                    "sector": "AI芯片",
                    "subsector": "GPU/军工芯片",
                    "role": "sub_leader",
                    "benchmark": "399006",
                    "benchmark_name": "创业板指",
                    "oversold_score_total": 52.1,
                    "oversold_components": {
                        "rsi": {
                            "raw_value": 28.0,
                            "score": 20.0,
                            "normalized_score": 0.7,
                            "weight": 0.2,
                            "explanation": "test",
                        }
                    },
                    "confirmation_pass": True,
                    "confirmations": {
                        "macd": {
                            "passed": True,
                            "raw_value": {"dif": 1},
                            "threshold": {"histogram_rising_days": 2},
                            "explanation": "test",
                        }
                    },
                    "relative_strength": {
                        "benchmark": "399006",
                        "benchmark_name": "创业板指",
                        "return_diff_5d": 0.01,
                        "return_diff_20d": -0.02,
                        "ratio_vs_ma10": 0.03,
                        "signal": "中性",
                    },
                    "risk_flags": [],
                    "action": "观察",
                    "invalidation_conditions": [],
                    "confidence": "unknown",
                    "notes": [],
                    "data_quality": {},
                    "tradeability": {},
                    "pre_trade_checklist": {},
                    "trade_plan": {},
                }
            ],
            "summary": {"counts_by_action": {"观察": 1}},
        }

        validated = validate_analysis_payload(payload)
        self.assertEqual(validated.meta.agent.name, "test")


if __name__ == "__main__":
    unittest.main()
