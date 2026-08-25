import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ZONE_DETAIL_JS = ROOT / "src" / "ventilation_core" / "web" / "static" / "zone-detail.js"
ZONE_DETAIL_CSS = ROOT / "src" / "ventilation_core" / "web" / "static" / "zone-detail.css"


class ZoneDetailAutoFitTest(unittest.TestCase):
    def test_zone_detail_values_use_dedicated_fill_area_and_autofit(self) -> None:
        js = ZONE_DETAIL_JS.read_text(encoding="utf-8")
        css = ZONE_DETAIL_CSS.read_text(encoding="utf-8")

        self.assertIn('valueWrap.className = "v2-zone-detail-value-wrap"', js)
        self.assertIn('value.dataset.autofit = "true"', js)
        self.assertIn("function zoneDetailFitValue(value)", js)
        self.assertIn("function zoneDetailFitValues", js)
        self.assertIn("value.scrollWidth <= availableWidth", js)
        self.assertIn("value.scrollHeight <= availableHeight", js)
        self.assertIn("zoneDetailFitValues(body);", js)
        self.assertIn("window.addEventListener(\"resize\", () => zoneDetailFitValues())", js)
        self.assertIn(".v2-zone-detail-value-wrap", css)
        self.assertIn('strong[data-autofit="true"]', css)

    def test_zone_detail_units_scale_with_the_value(self) -> None:
        js = ZONE_DETAIL_JS.read_text(encoding="utf-8")
        css = ZONE_DETAIL_CSS.read_text(encoding="utf-8")

        self.assertIn("value.appendChild(unit)", js)
        self.assertIn(".v2-zone-detail-item small", css)
        self.assertIn("font-size:.34em", css)


if __name__ == "__main__":
    unittest.main()
