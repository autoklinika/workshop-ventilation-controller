from __future__ import annotations

import unittest

from ventilation_core.application.control_engine_runtime import PersistentControlEngineEvaluator
from ventilation_core.domain.control_engine_config import ControlEngineConfig
from ventilation_core.domain.models import CoreState, FanSetpoints, VentilationMode
from ventilation_core.domain.sensors import AirQualityReading, SensorBusState, SensorNodeState


class MemoryStore:
    def __init__(self) -> None:
        self.config = ControlEngineConfig()
        self.revision = 1

    def load(self):
        return self.config, self.revision

    def replace(self, config):
        self.config = config
        self.revision += 1
        return self.revision

    def close(self) -> None:
        pass


def state_with_node(node: SensorNodeState) -> CoreState:
    return CoreState(
        mode=VentilationMode.STOP,
        setpoints=FanSetpoints.stopped(),
        hardware_ready=True,
        output_state_known=True,
        sensor_bus=SensorBusState(
            port="/dev/ttyAMA0",
            baudrate=19200,
            addresses=(1, 2),
            ready=True,
            worker_alive=True,
            nodes=(node,),
        ),
    )


class ControlEngineSensorProvenanceTest(unittest.TestCase):
    def test_fresh_sen55_values_are_copied_exactly_into_shadow_provenance(self) -> None:
        node = SensorNodeState(
            slave_address=1,
            online=True,
            usable=True,
            measurement_valid=True,
            measurement_stale=False,
            sensor_present=True,
            reading=AirQualityReading(
                pm2_5_ug_m3=12.5,
                pm10_0_ug_m3=18.75,
                temperature_celsius=21.25,
                voc_index=123.0,
                nox_index=7.0,
            ),
            age_seconds=2,
            last_success_at="2026-08-28T06:30:00+00:00",
        )
        runtime = PersistentControlEngineEvaluator(MemoryStore())

        result = runtime.evaluate(state_with_node(node))
        zone = next(item for item in result.zones if item.sensor_address == 1)

        self.assertTrue(zone.sensor_usable)
        self.assertTrue(zone.sensor_online)
        self.assertTrue(zone.sensor_measurement_valid)
        self.assertFalse(zone.sensor_measurement_stale)
        self.assertEqual(zone.sensor_age_seconds, 2)
        self.assertEqual(zone.sensor_last_success_at, "2026-08-28T06:30:00+00:00")
        self.assertEqual(zone.sensor_pm2_5_ug_m3, 12.5)
        self.assertEqual(zone.sensor_pm10_0_ug_m3, 18.75)
        self.assertEqual(zone.sensor_voc_index, 123.0)
        self.assertEqual(zone.sensor_nox_index, 7.0)
        self.assertEqual(zone.sensor_temperature_celsius, 21.25)
        self.assertEqual(zone.inside_temperature_celsius, 21.25)
        self.assertFalse(result.actuation_supported)

    def test_stale_sen55_values_remain_visible_as_provenance_but_are_not_consumed(self) -> None:
        node = SensorNodeState(
            slave_address=1,
            online=True,
            usable=True,
            measurement_valid=True,
            measurement_stale=True,
            sensor_present=True,
            reading=AirQualityReading(
                pm2_5_ug_m3=44.0,
                pm10_0_ug_m3=55.0,
                temperature_celsius=19.0,
                voc_index=200.0,
                nox_index=20.0,
            ),
            age_seconds=999,
            last_success_at="2026-08-28T06:00:00+00:00",
        )
        runtime = PersistentControlEngineEvaluator(MemoryStore())

        result = runtime.evaluate(state_with_node(node))
        zone = next(item for item in result.zones if item.sensor_address == 1)

        self.assertFalse(zone.sensor_usable)
        self.assertTrue(zone.sensor_online)
        self.assertTrue(zone.sensor_measurement_valid)
        self.assertTrue(zone.sensor_measurement_stale)
        self.assertEqual(zone.sensor_pm2_5_ug_m3, 44.0)
        self.assertEqual(zone.sensor_temperature_celsius, 19.0)
        self.assertIsNone(zone.inside_temperature_celsius)
        self.assertIsNone(zone.air_quality_level)
        self.assertEqual(zone.automation_state, "FAULT")
        self.assertFalse(result.actuation_supported)

    def test_serialized_contract_contains_provenance_fields_without_actuation_enable(self) -> None:
        node = SensorNodeState(
            slave_address=1,
            online=True,
            usable=True,
            measurement_valid=True,
            measurement_stale=False,
            reading=AirQualityReading(pm2_5_ug_m3=5.0, temperature_celsius=22.0),
        )
        runtime = PersistentControlEngineEvaluator(MemoryStore())
        payload = runtime.evaluate(state_with_node(node)).to_dict()
        zone = next(item for item in payload["zones"] if item["sensor_address"] == 1)

        self.assertEqual(zone["sensor_pm2_5_ug_m3"], 5.0)
        self.assertEqual(zone["sensor_temperature_celsius"], 22.0)
        self.assertIn("sensor_measurement_stale", zone)
        self.assertNotIn("actuation_enabled", payload)
        self.assertNotIn("actuation_enabled", zone)


if __name__ == "__main__":
    unittest.main()
