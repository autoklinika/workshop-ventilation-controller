import json
import unittest
from pathlib import Path

from ventilation_core.domain.tuning_validation import (
    TUNING_GROUP_REQUIREMENTS,
    TuningValidationEntry,
    TuningValidationProfile,
    ValidationLevel,
)


ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / "config" / "control-engine-tuning-validation-v1.json"


class TuningValidationTests(unittest.TestCase):
    def test_versioned_profile_is_strict_and_matches_required_groups(self) -> None:
        payload = json.loads(PROFILE.read_text(encoding="utf-8"))
        profile = TuningValidationProfile.from_dict(payload)

        self.assertEqual(
            {name for name, _ in profile.groups},
            set(TUNING_GROUP_REQUIREMENTS),
        )
        self.assertEqual(
            profile.entry("tacho_confirmation").level,
            ValidationLevel.PHYSICAL_VALIDATED,
        )
        self.assertIn(
            "physical-code-sha:f899f0589fb05bbb56c7df298ee6a268d85d7941",
            profile.entry("tacho_confirmation").evidence,
        )

    def test_current_profile_cannot_satisfy_future_actuation_preconditions(self) -> None:
        profile = TuningValidationProfile.from_dict(
            json.loads(PROFILE.read_text(encoding="utf-8"))
        )
        blockers = profile.readiness_blockers()

        self.assertNotIn(
            "VALIDATION_TACHO_CONFIRMATION_REQUIRES_PHYSICAL_VALIDATED",
            blockers,
        )
        for group in (
            "fan_outputs",
            "aero_outputs",
            "dynamics",
            "fan_sensor_fallback",
            "aero_sensor_fallback",
            "tacho_supply_fallback",
            "tacho_extract_fallback",
            "tacho_both_fallback",
        ):
            self.assertIn(
                f"VALIDATION_{group.upper()}_REQUIRES_WORKSHOP_VALIDATED",
                blockers,
            )
        self.assertFalse(profile.ready_for_actuation_preconditions)

    def test_synthetic_does_not_satisfy_workshop_requirement(self) -> None:
        entry = TuningValidationEntry(
            level=ValidationLevel.SYNTHETIC_VALIDATED,
            evidence=("test:scenario",),
        )
        self.assertLess(entry.level, ValidationLevel.WORKSHOP_VALIDATED)

    def test_validated_level_requires_evidence(self) -> None:
        with self.assertRaisesRegex(ValueError, "requires at least one evidence"):
            TuningValidationEntry(level=ValidationLevel.PHYSICAL_VALIDATED)

    def test_profile_rejects_missing_group(self) -> None:
        payload = json.loads(PROFILE.read_text(encoding="utf-8"))
        del payload["groups"]["fan_outputs"]
        with self.assertRaisesRegex(ValueError, "missing tuning validation groups"):
            TuningValidationProfile.from_dict(payload)

    def test_profile_rejects_unknown_group(self) -> None:
        payload = json.loads(PROFILE.read_text(encoding="utf-8"))
        payload["groups"]["invented"] = {
            "level": "UNVALIDATED",
            "evidence": [],
            "note": None,
        }
        with self.assertRaisesRegex(ValueError, "unsupported tuning validation groups"):
            TuningValidationProfile.from_dict(payload)


if __name__ == "__main__":
    unittest.main()
