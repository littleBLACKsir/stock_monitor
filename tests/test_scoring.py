from __future__ import annotations

import unittest

from ai_stock_analyzer.config import load_config
from ai_stock_analyzer.indicators.scoring import score_oversold_components
from ai_stock_analyzer.indicators.technical import prepare_indicator_frame
from tests.test_indicators import make_frame


class ScoringTests(unittest.TestCase):
    def test_oversold_score_is_bounded_and_prefers_weaker_series(self) -> None:
        thresholds = load_config("thresholds.yaml")

        falling = make_frame(length=80, drift=-0.8)
        rising = make_frame(length=80, drift=0.8)

        falling_prepared = prepare_indicator_frame(falling, thresholds)
        rising_prepared = prepare_indicator_frame(rising, thresholds)

        _, falling_score = score_oversold_components(falling_prepared, thresholds, "neutral")
        rising_components, rising_score = score_oversold_components(rising_prepared, thresholds, "neutral")

        self.assertGreaterEqual(falling_score, 0)
        self.assertLessEqual(falling_score, 100)
        self.assertGreaterEqual(rising_score, 0)
        self.assertLessEqual(rising_score, 100)
        self.assertGreater(falling_score, rising_score)
        self.assertEqual(set(rising_components.keys()), {"rsi", "bollinger", "ma_deviation_atr", "drawdown_position"})


if __name__ == "__main__":
    unittest.main()

