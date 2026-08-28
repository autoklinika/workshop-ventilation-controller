from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from ventilation_core.domain.shadow_policy import AirQualityLevel, ShadowPolicyV1, ThermalBand


@dataclass(frozen=True)
class AirQualityDynamicsSnapshot:
    raw_level: AirQualityLevel | None
    raw_driver: str | None
    effective_level: AirQualityLevel | None
    effective_driver: str | None
    effective_since_utc: str | None
    pending_level: AirQualityLevel | None
    pending_driver: str | None
    pending_since_utc: str | None
    transition_reason: str


@dataclass
class _AirQualityDynamicsState:
    pm2_5_level: AirQualityLevel | None = None
    voc_level: AirQualityLevel | None = None
    nox_level: AirQualityLevel | None = None
    effective_level: AirQualityLevel | None = None
    effective_driver: str | None = None
    effective_since: datetime | None = None
    pending_level: AirQualityLevel | None = None
    pending_driver: str | None = None
    pending_since: datetime | None = None


class AirQualityDynamicsTracker:
    """Per-zone SHADOW-only hysteresis and temporal stabilization.

    Production tuning remains explicit. When dynamics tuning is incomplete the
    tracker behaves transparently and follows the instantaneous classification,
    preserving the existing SHADOW contract without inventing timing values.
    """

    def __init__(self) -> None:
        self._state = _AirQualityDynamicsState()

    def update(
        self,
        policy: ShadowPolicyV1,
        *,
        pm2_5_ug_m3: float | None,
        voc_index: float | None,
        nox_index: float | None,
        now_utc: datetime,
    ) -> AirQualityDynamicsSnapshot:
        now = _aware_utc(now_utc)
        tuning = policy.tuning

        raw_pm = policy.classify_pm2_5(pm2_5_ug_m3)
        raw_voc = policy.classify_voc(voc_index)
        raw_nox = policy.classify_nox(nox_index)
        raw_level, raw_driver = _aggregate_levels(raw_pm, raw_voc, raw_nox)

        if not tuning.dynamics_configured:
            self._state.pm2_5_level = raw_pm
            self._state.voc_level = raw_voc
            self._state.nox_level = raw_nox
            self._set_effective(raw_level, raw_driver, now)
            self._clear_pending()
            return self._snapshot(raw_level, raw_driver, "DYNAMICS_TUNING_REQUIRED")

        stable_pm = _metric_with_hysteresis(
            raw_pm,
            previous=self._state.pm2_5_level,
            value=pm2_5_ug_m3,
            hysteresis=tuning.pm2_5_hysteresis_ug_m3,
            thresholds=(
                policy.pm2_5_reference_ug_m3,
                policy.pm2_5_high_ug_m3,
                policy.pm2_5_max_ug_m3,
            ),
        )
        stable_voc = _metric_with_hysteresis(
            raw_voc,
            previous=self._state.voc_level,
            value=voc_index,
            hysteresis=tuning.voc_hysteresis_index,
            thresholds=(
                policy.voc_boost_index,
                policy.voc_high_index,
                policy.voc_max_index,
            ),
        )
        stable_nox = _metric_with_hysteresis(
            raw_nox,
            previous=self._state.nox_level,
            value=nox_index,
            hysteresis=tuning.nox_hysteresis_index,
            thresholds=(
                policy.nox_boost_index,
                policy.nox_high_index,
                policy.nox_max_index,
            ),
        )
        self._state.pm2_5_level = stable_pm
        self._state.voc_level = stable_voc
        self._state.nox_level = stable_nox
        target_level, target_driver = _aggregate_levels(stable_pm, stable_voc, stable_nox)

        if self._state.effective_level is None:
            self._set_effective(target_level, target_driver, now)
            self._clear_pending()
            return self._snapshot(raw_level, raw_driver, "INITIALIZED")

        current = self._state.effective_level
        if target_level is None:
            self._clear_pending()
            return self._snapshot(raw_level, raw_driver, "INPUTS_UNAVAILABLE_HOLD")

        if target_level == current:
            self._state.effective_driver = target_driver
            self._clear_pending()
            return self._snapshot(raw_level, raw_driver, "STABLE")

        if target_level > current:
            confirmation = 0.0
            if target_level == AirQualityLevel.BOOST and target_driver == "PM2_5":
                confirmation = float(tuning.pm2_5_boost_confirmation_seconds or 0.0)
            if confirmation <= 0.0:
                self._set_effective(target_level, target_driver, now)
                self._clear_pending()
                return self._snapshot(raw_level, raw_driver, "ESCALATED_IMMEDIATELY")
            if not self._same_pending(target_level, target_driver):
                self._set_pending(target_level, target_driver, now)
                return self._snapshot(raw_level, raw_driver, "ESCALATION_CONFIRMING")
            assert self._state.pending_since is not None
            if (now - self._state.pending_since).total_seconds() >= confirmation:
                self._set_effective(target_level, target_driver, now)
                self._clear_pending()
                return self._snapshot(raw_level, raw_driver, "ESCALATION_CONFIRMED")
            return self._snapshot(raw_level, raw_driver, "ESCALATION_CONFIRMING")

        # De-escalation is intentionally slower than escalation. First honour the
        # minimum state hold, then require a sustained lower target for decay.
        assert target_level < current
        effective_since = self._state.effective_since or now
        minimum_hold = float(tuning.state_minimum_hold_seconds or 0.0)
        if (now - effective_since).total_seconds() < minimum_hold:
            self._clear_pending()
            return self._snapshot(raw_level, raw_driver, "MINIMUM_HOLD")

        decay = float(tuning.boost_decay_seconds or 0.0)
        if decay <= 0.0:
            self._set_effective(target_level, target_driver, now)
            self._clear_pending()
            return self._snapshot(raw_level, raw_driver, "DEESCALATED_IMMEDIATELY")
        if not self._same_pending(target_level, target_driver):
            self._set_pending(target_level, target_driver, now)
            return self._snapshot(raw_level, raw_driver, "DEESCALATION_DECAY")
        assert self._state.pending_since is not None
        if (now - self._state.pending_since).total_seconds() >= decay:
            self._set_effective(target_level, target_driver, now)
            self._clear_pending()
            return self._snapshot(raw_level, raw_driver, "DEESCALATION_CONFIRMED")
        return self._snapshot(raw_level, raw_driver, "DEESCALATION_DECAY")

    def _set_effective(
        self,
        level: AirQualityLevel | None,
        driver: str | None,
        now: datetime,
    ) -> None:
        if level != self._state.effective_level:
            self._state.effective_since = now
        elif self._state.effective_since is None:
            self._state.effective_since = now
        self._state.effective_level = level
        self._state.effective_driver = driver

    def _set_pending(
        self,
        level: AirQualityLevel,
        driver: str | None,
        now: datetime,
    ) -> None:
        self._state.pending_level = level
        self._state.pending_driver = driver
        self._state.pending_since = now

    def _clear_pending(self) -> None:
        self._state.pending_level = None
        self._state.pending_driver = None
        self._state.pending_since = None

    def _same_pending(self, level: AirQualityLevel, driver: str | None) -> bool:
        return (
            self._state.pending_level == level
            and self._state.pending_driver == driver
            and self._state.pending_since is not None
        )

    def _snapshot(
        self,
        raw_level: AirQualityLevel | None,
        raw_driver: str | None,
        reason: str,
    ) -> AirQualityDynamicsSnapshot:
        return AirQualityDynamicsSnapshot(
            raw_level=raw_level,
            raw_driver=raw_driver,
            effective_level=self._state.effective_level,
            effective_driver=self._state.effective_driver,
            effective_since_utc=_iso(self._state.effective_since),
            pending_level=self._state.pending_level,
            pending_driver=self._state.pending_driver,
            pending_since_utc=_iso(self._state.pending_since),
            transition_reason=reason,
        )


class ThermalDynamicsTracker:
    """Temperature-band hysteresis for the fan-zone SHADOW proposal."""

    def __init__(self) -> None:
        self._band: ThermalBand | None = None

    def update(
        self,
        policy: ShadowPolicyV1,
        *,
        temperature_celsius: float | None,
    ) -> tuple[ThermalBand, ThermalBand]:
        raw = policy.classify_temperature(temperature_celsius)
        tuning = policy.tuning
        previous = self._band
        if (
            raw in {ThermalBand.UNKNOWN, ThermalBand.NOT_APPLICABLE}
            or previous is None
            or previous in {ThermalBand.UNKNOWN, ThermalBand.NOT_APPLICABLE}
            or not tuning.dynamics_configured
            or tuning.temperature_hysteresis_celsius is None
            or temperature_celsius is None
        ):
            self._band = raw
            return raw, raw

        # Moving toward colder/more restrictive bands is immediate. Recovery to
        # a less restrictive band requires crossing the boundary plus hysteresis.
        order = {
            ThermalBand.NORMAL: 0,
            ThermalBand.LIMITING: 1,
            ThermalBand.MINIMUM: 2,
            ThermalBand.PROTECTION: 3,
        }
        if order[raw] >= order[previous]:
            self._band = raw
            return raw, raw

        hysteresis = float(tuning.temperature_hysteresis_celsius)
        recovery_threshold = {
            ThermalBand.PROTECTION: policy.temperature_minimum_from_celsius,
            ThermalBand.MINIMUM: policy.temperature_limiting_from_celsius,
            ThermalBand.LIMITING: policy.temperature_normal_above_celsius,
        }.get(previous)
        if recovery_threshold is None:
            self._band = raw
            return raw, raw
        if temperature_celsius < recovery_threshold + hysteresis:
            return raw, previous
        self._band = raw
        return raw, raw


def _metric_with_hysteresis(
    raw: AirQualityLevel | None,
    *,
    previous: AirQualityLevel | None,
    value: float | None,
    hysteresis: float | None,
    thresholds: tuple[float, float, float],
) -> AirQualityLevel | None:
    if raw is None or previous is None or value is None or hysteresis is None:
        return raw
    if raw >= previous:
        return raw
    threshold_by_level = {
        AirQualityLevel.BOOST: thresholds[0],
        AirQualityLevel.HIGH: thresholds[1],
        AirQualityLevel.MAX: thresholds[2],
    }
    previous_threshold = threshold_by_level.get(previous)
    if previous_threshold is None:
        return raw
    if float(value) > float(previous_threshold) - float(hysteresis):
        return previous
    return raw


def _aggregate_levels(
    pm2_5: AirQualityLevel | None,
    voc: AirQualityLevel | None,
    nox: AirQualityLevel | None,
) -> tuple[AirQualityLevel | None, str | None]:
    values = (("PM2_5", pm2_5), ("VOC", voc), ("NOX", nox))
    available = [(name, level) for name, level in values if level is not None]
    if not available:
        return None, None
    maximum = max(level for _, level in available)
    for name, level in available:
        if level == maximum:
            return maximum, name
    raise AssertionError("unreachable")


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("dynamics clock must be timezone-aware")
    return value.astimezone(timezone.utc)


def _iso(value: datetime | None) -> str | None:
    return None if value is None else value.astimezone(timezone.utc).isoformat()
