from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src" / "ventilation_core" / "web" / "static"


class HistoryAlertPaginationPollingStage43Test(unittest.TestCase):
    def test_stage43_stops_legacy_fixed_200_history_poll(self) -> None:
        h41 = (STATIC / "history-h41-alerts.js").read_text(encoding="utf-8")
        h43 = (STATIC / "history-h43-alert-pagination.js").read_text(encoding="utf-8")
        self.assertIn(
            "const historyH41PollTimer = window.setInterval",
            h41,
        )
        self.assertIn("window.clearInterval(historyH41PollTimer)", h43)
        self.assertIn("HISTORY_H43_INDEX_POLL_MS = 60000", h43)
        self.assertIn('historyH43Post("/api/v1/history/alerts/days"', h43)
        self.assertIn('historyH43Post("/api/v1/history/alerts/day"', h43)


if __name__ == "__main__":
    unittest.main()
