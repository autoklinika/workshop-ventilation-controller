from __future__ import annotations

import copy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from tools.apply_validated_control_engine_tacho_confirmation import (
    DEFAULT_PROFILE,
    FIELD,
    _load_seconds,
    apply,
)


SOCKET = Path("/tmp/test-control-engine.sock")


def config(value):
    return {
        "schema_version": 1,
        "policy": {
            "version": "test-policy",
            "pm2_5_reference_ug_m3": 15.0,
            "pm2_5_high_ug_m3": 25.0,
            "pm2_5_max_ug_m3": 50.0,
            "pm10_reference_ug_m3": 45.0,
            "voc_boost_index": 150.0,
            "voc_high_index": 200.0,
            "voc_max_index": 300.0,
            "nox_boost_index": 10.0,
            "nox_high_index": 50.0,
            "nox_max_index": 100.0,
            "temperature_normal_above_celsius": 20.0,
            "temperature_limiting_from_celsius": 18.0,
            "temperature_minimum_from_celsius": 16.0,
            "tuning": {
                "sentinel_preserved_field": 123.0,
                FIELD: value,
            },
        },
    }


def response(revision: int, cfg: dict, *, dynamics_reset=None, actuation=False):
    control = {
        "revision": revision,
        "config": cfg,
        "actuation_supported": actuation,
    }
    if dynamics_reset is not None:
        control["dynamics_reset"] = dynamics_reset
    return {"ok": True, "control_engine": control}


class ValidatedTachoConfirmationPatcherTest(unittest.TestCase):
    def test_versioned_profile_contains_only_validated_tacho_timing(self) -> None:
        self.assertEqual(_load_seconds(DEFAULT_PROFILE), 4.0)
        payload = json.loads(DEFAULT_PROFILE.read_text(encoding="utf-8"))
        self.assertEqual(payload["validated_tuning"], {FIELD: 4.0})
        self.assertEqual(payload["evidence"]["stage7c_test_voltage"], 1.0)
        self.assertAlmostEqual(
            payload["evidence"]["stage7c_max_first_healthy_seconds"]["supply"],
            1.912283030000026,
        )
        self.assertEqual(len(payload["intentionally_unset"]), 6)

    def test_null_value_requires_explicit_confirmation_and_does_not_write(self) -> None:
        current = config(None)
        with patch(
            "tools.apply_validated_control_engine_tacho_confirmation.send_request",
            return_value=response(7, current),
        ) as sender:
            with self.assertRaisesRegex(RuntimeError, "--confirm-apply"):
                apply(socket_path=SOCKET, profile_path=DEFAULT_PROFILE, confirm=False)
        self.assertEqual(sender.call_count, 1)
        self.assertEqual(sender.call_args.args[1], {"command": "control-engine"})

    def test_patch_changes_only_tacho_timing_and_verifies_readback(self) -> None:
        current = config(None)
        patched = copy.deepcopy(current)
        patched["policy"]["tuning"][FIELD] = 4.0
        responses = [
            response(11, current),
            response(12, patched, dynamics_reset=True),
            response(12, patched),
        ]
        with patch(
            "tools.apply_validated_control_engine_tacho_confirmation.send_request",
            side_effect=responses,
        ) as sender:
            result = apply(socket_path=SOCKET, profile_path=DEFAULT_PROFILE, confirm=True)

        self.assertEqual(result["changed"], True)
        self.assertEqual(result["revision_before"], 11)
        self.assertEqual(result["revision_after"], 12)
        self.assertEqual(sender.call_count, 3)
        replace_request = sender.call_args_list[1].args[1]
        self.assertEqual(replace_request["command"], "control-engine-replace")
        self.assertEqual(replace_request["config"], patched)
        self.assertEqual(
            replace_request["config"]["policy"]["tuning"]["sentinel_preserved_field"],
            123.0,
        )

    def test_already_validated_value_is_idempotent_without_write(self) -> None:
        current = config(4.0)
        with patch(
            "tools.apply_validated_control_engine_tacho_confirmation.send_request",
            return_value=response(3, current),
        ) as sender:
            result = apply(socket_path=SOCKET, profile_path=DEFAULT_PROFILE, confirm=False)
        self.assertEqual(result, {"changed": False, "revision": 3, "seconds": 4.0})
        self.assertEqual(sender.call_count, 1)

    def test_existing_different_value_is_never_overwritten(self) -> None:
        current = config(3.0)
        with patch(
            "tools.apply_validated_control_engine_tacho_confirmation.send_request",
            return_value=response(5, current),
        ) as sender:
            with self.assertRaisesRegex(RuntimeError, "refusing to overwrite"):
                apply(socket_path=SOCKET, profile_path=DEFAULT_PROFILE, confirm=True)
        self.assertEqual(sender.call_count, 1)

    def test_actuation_authority_claim_blocks_patch(self) -> None:
        current = config(None)
        with patch(
            "tools.apply_validated_control_engine_tacho_confirmation.send_request",
            return_value=response(1, current, actuation=True),
        ) as sender:
            with self.assertRaisesRegex(RuntimeError, "actuation authority"):
                apply(socket_path=SOCKET, profile_path=DEFAULT_PROFILE, confirm=True)
        self.assertEqual(sender.call_count, 1)

    def test_invalid_profile_cannot_add_other_tuning_fields(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.json"
            path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "validated_tuning": {
                            FIELD: 4.0,
                            "tacho_supply_fault_fallback_supply_pct": 100.0,
                        },
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(RuntimeError, "must contain only"):
                _load_seconds(path)


if __name__ == "__main__":
    unittest.main()
