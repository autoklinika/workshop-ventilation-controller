from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum, StrEnum


class AirQualityLevel(IntEnum):
    NORMAL = 0
    BOOST = 1
    HIGH = 2
    MAX = 3


class ThermalBand(StrEnum):
    NORMAL = "NORMAL"
    LIMITING = "LIMITING"
    MINIMUM = "MINIMUM"
    PROTECTION = "PROTECTION"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class ShadowOutputTuning:
    """Explicit tuning knobs intentionally left unset until real-object tuning.

    None means that the threshold policy can classify conditions, but must not invent
    an output request. Values are percentages of the command range, not measured air
    flow. A later persistent configuration layer can populate the same contract.
    """

    normal_air_request_pct: float | None = None
    boost_air_request_pct: float | None = None
    high_air_request_pct: float | None = None
    max_air_request_pct: float | None = None

    thermal_normal_limit_pct: float | None = None
    thermal_limiting_limit_pct: float | None = None
    thermal_minimum_limit_pct: float | None = None
    thermal_protection_limit_pct: float | None = None

    extract_bias_pct: float | None = None

    aero_normal_speed: int | None = None
    aero_boost_speed: int | None = None
    aero_high_speed: int | None = None
    aero_max_speed: int | None = None

    pm2_5_hysteresis_ug_m3: float | None = None
    voc_hysteresis_index: float | None = None
    nox_hysteresis_index: float | None = None
    temperature_hysteresis_celsius: float | None = None

    pm2_5_boost_confirmation_seconds: float | None = None
    state_minimum_hold_seconds: float | None = None
    boost_decay_seconds: float | None = None

    # Explicit sensor-loss fallback. These values intentionally do not take part
    # in `complete` yet: Stage 1/2 tuning can be validated independently, while
    # sensor-loss fallback remains a separately auditable safety parameter.
    sensor_fallback_supply_pct: float | None = None
    sensor_fallback_extract_pct: float | None = None
    aero_sensor_fallback_speed: int | None = None

    def __post_init__(self) -> None:
        percentage_fields = (
            "normal_air_request_pct",
            "boost_air_request_pct",
            "high_air_request_pct",
            "max_air_request_pct",
            "thermal_normal_limit_pct",
            "thermal_limiting_limit_pct",
            "thermal_minimum_limit_pct",
            "thermal_protection_limit_pct",
            "extract_bias_pct",
            "sensor_fallback_supply_pct",
            "sensor_fallback_extract_pct",
        )
        for name in percentage_fields:
            value = getattr(self, name)
            if value is not None and not 0.0 <= float(value) <= 100.0:
                raise ValueError(f"{name} must be within 0..100")

        for name in (
            "aero_normal_speed",
            "aero_boost_speed",
            "aero_high_speed",
            "aero_max_speed",
            "aero_sensor_fallback_speed",
        ):
            value = getattr(self, name)
            if value is not None and (
                isinstance(value, bool) or not isinstance(value, int) or value not in {0, 1, 2, 3}
            ):
                raise ValueError(f"{name} must be one of 0, 1, 2, 3")

        for name in (
            "pm2_5_hysteresis_ug_m3",
            "voc_hysteresis_index",
            "nox_hysteresis_index",
            "temperature_hysteresis_celsius",
            "pm2_5_boost_confirmation_seconds",
            "state_minimum_hold_seconds",
            "boost_decay_seconds",
        ):
            value = getattr(self, name)
            if value is not None and float(value) < 0.0:
                raise ValueError(f"{name} must be non-negative")

        air_values = (
            self.normal_air_request_pct,
            self.boost_air_request_pct,
            self.high_air_request_pct,
            self.max_air_request_pct,
        )
        if all(value is not None for value in air_values):
            normal, boost, high, maximum = (float(value) for value in air_values)
            if not normal <= boost <= high <= maximum:
                raise ValueError("Air request percentages must be monotonic NORMAL <= BOOST <= HIGH <= MAX")

        thermal_values = (
            self.thermal_normal_limit_pct,
            self.thermal_limiting_limit_pct,
            self.thermal_minimum_limit_pct,
            self.thermal_protection_limit_pct,
        )
        if all(value is not None for value in thermal_values):
            normal, limiting, minimum, protection = (float(value) for value in thermal_values)
            if not normal >= limiting >= minimum >= protection:
                raise ValueError(
                    "Thermal limits must be monotonic NORMAL >= LIMITING >= MINIMUM >= PROTECTION"
                )

        aero_values = (
            self.aero_normal_speed,
            self.aero_boost_speed,
            self.aero_high_speed,
            self.aero_max_speed,
        )
        if all(value is not None for value in aero_values):
            normal, boost, high, maximum = (int(value) for value in aero_values)
            if not normal <= boost <= high <= maximum:
                raise ValueError("AERO speeds must be monotonic NORMAL <= BOOST <= HIGH <= MAX")

        fan_fallback = (
            self.sensor_fallback_supply_pct,
            self.sensor_fallback_extract_pct,
        )
        if any(value is not None for value in fan_fallback) and not all(
            value is not None for value in fan_fallback
        ):
            raise ValueError(
                "Fan sensor fallback requires both supply and extract percentages"
            )

    @property
    def fan_outputs_configured(self) -> bool:
        values = (
            self.normal_air_request_pct,
            self.boost_air_request_pct,
            self.high_air_request_pct,
            self.max_air_request_pct,
            self.thermal_normal_limit_pct,
            self.thermal_limiting_limit_pct,
            self.thermal_minimum_limit_pct,
            self.thermal_protection_limit_pct,
            self.extract_bias_pct,
        )
        return all(value is not None for value in values)

    @property
    def aero_outputs_configured(self) -> bool:
        values = (
            self.aero_normal_speed,
            self.aero_boost_speed,
            self.aero_high_speed,
            self.aero_max_speed,
        )
        return all(value is not None for value in values)

    @property
    def outputs_configured(self) -> bool:
        # SHADOW can be tuned and observed per actuator family independently.
        return self.fan_outputs_configured or self.aero_outputs_configured

    @property
    def dynamics_configured(self) -> bool:
        values = (
            self.pm2_5_hysteresis_ug_m3,
            self.voc_hysteresis_index,
            self.nox_hysteresis_index,
            self.temperature_hysteresis_celsius,
            self.pm2_5_boost_confirmation_seconds,
            self.state_minimum_hold_seconds,
            self.boost_decay_seconds,
        )
        return all(value is not None for value in values)

    @property
    def fan_sensor_fallback_configured(self) -> bool:
        return (
            self.sensor_fallback_supply_pct is not None
            and self.sensor_fallback_extract_pct is not None
        )

    @property
    def aero_sensor_fallback_configured(self) -> bool:
        return self.aero_sensor_fallback_speed is not None

    @property
    def complete(self) -> bool:
        return (
            self.fan_outputs_configured
            and self.aero_outputs_configured
            and self.dynamics_configured
        )


@dataclass(frozen=True)
class ShadowPolicyV1:
    """Versioned deterministic thresholds from docs/ZALOZENIA_AUTOMATYKI_PL.md.

    The policy classifies process conditions only. It is not a BHP declaration and
    it does not grant actuation authority. Percentages, hysteresis and timing remain
    explicit tuning parameters and default to None until validated on the real site.
    """

    version: str = "shadow-policy-v1-2026-08-12"

    pm2_5_reference_ug_m3: float = 15.0
    pm2_5_high_ug_m3: float = 25.0
    pm2_5_max_ug_m3: float = 50.0
    pm10_reference_ug_m3: float = 45.0

    voc_boost_index: float = 150.0
    voc_high_index: float = 200.0
    voc_max_index: float = 300.0

    nox_boost_index: float = 10.0
    nox_high_index: float = 50.0
    nox_max_index: float = 100.0

    temperature_normal_above_celsius: float = 20.0
    temperature_limiting_from_celsius: float = 18.0
    temperature_minimum_from_celsius: float = 16.0

    tuning: ShadowOutputTuning = ShadowOutputTuning()

    def classify_pm2_5(self, value: float | None) -> AirQualityLevel | None:
        if value is None:
            return None
        if value > self.pm2_5_max_ug_m3:
            return AirQualityLevel.MAX
        if value > self.pm2_5_high_ug_m3:
            return AirQualityLevel.HIGH
        if value > self.pm2_5_reference_ug_m3:
            return AirQualityLevel.BOOST
        return AirQualityLevel.NORMAL

    def classify_voc(self, value: float | None) -> AirQualityLevel | None:
        if value is None:
            return None
        if value > self.voc_max_index:
            return AirQualityLevel.MAX
        if value >= self.voc_high_index:
            return AirQualityLevel.HIGH
        if value >= self.voc_boost_index:
            return AirQualityLevel.BOOST
        return AirQualityLevel.NORMAL

    def classify_nox(self, value: float | None) -> AirQualityLevel | None:
        if value is None:
            return None
        if value > self.nox_max_index:
            return AirQualityLevel.MAX
        if value > self.nox_high_index:
            return AirQualityLevel.HIGH
        if value > self.nox_boost_index:
            return AirQualityLevel.BOOST
        return AirQualityLevel.NORMAL

    def classify_air_quality(
        self,
        *,
        pm2_5_ug_m3: float | None,
        voc_index: float | None,
        nox_index: float | None,
    ) -> tuple[AirQualityLevel | None, str | None]:
        levels = {
            "PM2_5": self.classify_pm2_5(pm2_5_ug_m3),
            "VOC": self.classify_voc(voc_index),
            "NOX": self.classify_nox(nox_index),
        }
        available = {name: level for name, level in levels.items() if level is not None}
        if not available:
            return None, None
        maximum = max(available.values())
        for name in ("PM2_5", "VOC", "NOX"):
            if available.get(name) == maximum:
                return maximum, name
        raise AssertionError("unreachable")

    def classify_temperature(self, value: float | None) -> ThermalBand:
        if value is None:
            return ThermalBand.UNKNOWN
        if value > self.temperature_normal_above_celsius:
            return ThermalBand.NORMAL
        if value >= self.temperature_limiting_from_celsius:
            return ThermalBand.LIMITING
        if value >= self.temperature_minimum_from_celsius:
            return ThermalBand.MINIMUM
        return ThermalBand.PROTECTION

    def pm10_reference_exceeded(self, value: float | None) -> bool | None:
        if value is None:
            return None
        return value > self.pm10_reference_ug_m3

    def air_request_pct(self, level: AirQualityLevel | None) -> float | None:
        if level is None:
            return None
        mapping = {
            AirQualityLevel.NORMAL: self.tuning.normal_air_request_pct,
            AirQualityLevel.BOOST: self.tuning.boost_air_request_pct,
            AirQualityLevel.HIGH: self.tuning.high_air_request_pct,
            AirQualityLevel.MAX: self.tuning.max_air_request_pct,
        }
        return mapping[level]

    def temperature_limit_pct(self, band: ThermalBand) -> float | None:
        mapping = {
            ThermalBand.NORMAL: self.tuning.thermal_normal_limit_pct,
            ThermalBand.LIMITING: self.tuning.thermal_limiting_limit_pct,
            ThermalBand.MINIMUM: self.tuning.thermal_minimum_limit_pct,
            ThermalBand.PROTECTION: self.tuning.thermal_protection_limit_pct,
        }
        return mapping.get(band)

    def aero_speed(self, level: AirQualityLevel | None) -> int | None:
        if level is None:
            return None
        mapping = {
            AirQualityLevel.NORMAL: self.tuning.aero_normal_speed,
            AirQualityLevel.BOOST: self.tuning.aero_boost_speed,
            AirQualityLevel.HIGH: self.tuning.aero_high_speed,
            AirQualityLevel.MAX: self.tuning.aero_max_speed,
        }
        return mapping[level]
