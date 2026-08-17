from __future__ import annotations

import importlib.util
import json
import os
import stat
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/provision_sensor_node_service.py"
SPEC = importlib.util.spec_from_file_location("provision_sensor_node_service", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
PROVISION = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PROVISION)


class ProvisionSensorNodeServiceTests(unittest.TestCase):
    def test_preserve_owner_group_uses_existing_registry_metadata(self) -> None:
        source = SimpleNamespace(st_uid=1000, st_gid=1000)
        current = SimpleNamespace(st_uid=0, st_gid=0)

        with mock.patch.object(PROVISION.os, "fstat", return_value=current), mock.patch.object(
            PROVISION.os, "fchown"
        ) as fchown:
            PROVISION._preserve_owner_group(7, source)

        fchown.assert_called_once_with(7, 1000, 1000)

    def test_preserve_owner_group_does_not_chown_when_already_matching(self) -> None:
        source = SimpleNamespace(st_uid=1000, st_gid=1000)
        current = SimpleNamespace(st_uid=1000, st_gid=1000)

        with mock.patch.object(PROVISION.os, "fstat", return_value=current), mock.patch.object(
            PROVISION.os, "fchown"
        ) as fchown:
            PROVISION._preserve_owner_group(7, source)

        fchown.assert_not_called()

    def test_write_registry_keeps_owner_group_and_forces_mode_0600(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "keys.json"
            path.write_text('{"nodes": {}}\n', encoding="utf-8")
            os.chmod(path, 0o640)
            before = path.stat()

            registry = {
                "nodes": {
                    "sensor-node-1": {
                        "key_id": "sensor-node-1-v1",
                        "hmac_key_hex": "11" * 32,
                        "mac": "88:13:BF:00:52:D0",
                    }
                }
            }
            PROVISION.write_registry(path, registry)

            after = path.stat()
            self.assertEqual((after.st_uid, after.st_gid), (before.st_uid, before.st_gid))
            self.assertEqual(stat.S_IMODE(after.st_mode), 0o600)
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), registry)


if __name__ == "__main__":
    unittest.main()
