from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from ai_stock_analyzer.config import load_config
from ai_stock_analyzer.indicators.technical import prepare_indicator_frame


def make_frame(length: int = 40, drift: float = 0.0) -> pd.DataFrame:
    dates = pd.bdate_range("2026-01-01", periods=length)
    base = 100 + np.arange(length) * drift
    close = pd.Series(base, dtype=float)
    open_ = close * 0.995
    high = close * 1.01
    low = close * 0.99
    volume = pd.Series(np.linspace(1_000_000, 2_000_000, length))
    amount = volume * close
    return pd.DataFrame(
        {
            "date": dates,
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
            "amount": amount,
            "amplitude": 0.0,
            "pct_change": close.pct_change().fillna(0) * 100,
            "change": close.diff().fillna(0),
            "turnover": 1.5,
        }
    )


class IndicatorTests(unittest.TestCase):
    def test_prepare_indicator_frame_preserves_length_and_handles_short_history(self) -> None:
        thresholds = load_config("thresholds.yaml")
        raw = make_frame(length=12, drift=0.1)
        prepared = prepare_indicator_frame(raw, thresholds)
        self.assertEqual(len(prepared), len(raw))
        self.assertTrue(prepared["ma20"].isna().all())
        self.assertIn("rsi14", prepared.columns)


if __name__ == "__main__":
    unittest.main()

