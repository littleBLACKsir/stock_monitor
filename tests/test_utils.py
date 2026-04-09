from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ai_stock_analyzer.utils import build_analysis_stem, resolve_report_path


class UtilsTests(unittest.TestCase):
    def test_report_path_suffix_strategy(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            report_dir = Path(temp_dir)
            stem = build_analysis_stem("Trae", "ZhiPu", "GLM5")
            first = resolve_report_path(report_dir, stem, "suffix")
            first.write_text("x", encoding="utf-8")
            second = resolve_report_path(report_dir, stem, "suffix")
            self.assertTrue(second.name.endswith("-2.md"))


if __name__ == "__main__":
    unittest.main()
