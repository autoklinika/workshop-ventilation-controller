from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from math import isfinite
from typing import Any, Mapping, Sequence

from ventilation_core.application.operator_control import apply_operator_intent
from ventilation_core.application.shadow_controller import PolicyShadowAutomationEvaluator
from ventilation_core.application.tacho_control import TachoShadowSupervisor
from ventilation_core.calendar.model import CalendarMode, CalendarPhase, CalendarResolution
from ventilation_core.domain.control_engine_config import ControlEngineConfig
from ventilation_core.domain.models import (
    AlarmCode,
    AlarmSeverity,
    AlarmState,
    CoreState,
    FanSetpoints,
    VentilationMode,
)
from ventilation_core.domain.operator_control import OperatorControlIntent
from ventilation_core.domain.sensors import AirQualityReading, SensorBusState, SensorNodeState
from ventilation_core.domain.tacho import FanTachoState, TachoMonitorState
from ventilation_core.domain.zigbee import ZigbeeMqttState, ZigbeeTemperatureSensorState


_SCENARIO_KEYS = {"schema_version", "name", "start_utc", "control_engine", "steps"}
_STEP_KEYS = {
    "at_seconds",
    "calendar",
    "operator",
    "actual_setpoints",
    "tacho",
    "sensor_1",
    "sensor_2",
    "zigbee_supply",
    "zigbee_extract",
    "hardware_ready",
    "output_state_known",
    "critical_alarm",
}
_CALENDAR_KEYS = {
    "phase",
    "mode",
    "profile",
    "schedule_supply_pct",
    "schedule_extract_pct",
    "schedule_request_source",
}
_SENSOR_KEYS = {
    "usable",
    "pm2_5_ug_m3",
    "pm10_0_ug_m3",
    "voc_index",
    "nox_index",
    "temperature_celsius",
}
_ZIGBEE_KEYS = {"temperature_celsius", "age_seconds", "available", "timestamp_available"}
_ACTUAL_SETPOINT_KEYS = {"supply_voltage", "extract_voltage"}
_TACHO_KEYS = {
    "ready",
    "worker_alive",
    "supply_present",
    "supply_valid",
    "supply_rpm",
    "extract_present",
    "extract_valid",
    "extract_rpm",
}


def _mapping(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} must be a JSON object")
    return value


def _sequence(value: Any, field: str) -> Sequence[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise ValueError(f"{field} must be a JSON array")
    return value


def _strict_keys(payload: Mapping[str, Any], allowed: set[str], field: str) -> None:
    unknown = set(payload) - allowed
    if unknown:
        raise ValueError(f"{field} contains unsupported fields: {', '.join(sorted(unknown))}")


def _number(value: Any, field: str, *, minimum: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be numeric without type coercion")
    result = float(value)
    if not isfinite(result):
        raise ValueError(f"{field} must be finite")
    if minimum is not None and result < minimum:
        raise ValueError(f"{field} must be >= {minimum}")
    return result


def _optional_number(value: Any, field: str) -> float | None:
    if value is None:
        return None
    return _number(value, field)


def _boolean(value: Any, field: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{field} must be boolean")
    return value


def _aware_datetime(value: Any, field: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be ISO-8601 text")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} must be valid ISO-8601 text") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field} must include timezone information")
    return parsed.astimezone(timezone.utc)


def _percentage(value: Any, field: str) -> float:
    result = _number(value, field)
    if not 0.0 <= result <= 100.0:
        raise ValueError(f"{field} must be within 0..100")
    return result


def _fan_voltage(value: Any, field: str) -> float:
    result = _number(value, field)
    if result == 0.0:
        return result
    if not 1.0 <= result <= 10.0:
        raise ValueError(f"{field} must be 0 or within the validated 1..10 V command range")
    return result


@dataclass(frozen=True)
class ScenarioRunResult:
    name: str
    start_utc: str
    policy_version: str
    steps: tuple[dict[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "name": self.name,
            "start_utc": self.start_utc,
            "policy_version": self.policy_version,
            "actuation_supported": False,
            "steps": list(self.steps),
        }


class _ScenarioClock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


class ControlEngineScenarioRunner:
    """Pure deterministic replay of the real Control Engine SHADOW evaluator.

    The runner creates synthetic CoreState snapshots only. It has no actuator,
    service, socket, GPIO, DAC, AERO executor, host-power or systemd boundary.
    Operator intent is process-local scenario state: AUTO initially and changed only
    by explicit step payloads, mirroring the volatile runtime contract. Optional
    actual_setpoints and TACHO inputs model already-commanded physical EC state for
    feedback supervision without executing any command.
    """

    def run(self, payload: Mapping[str, Any]) -> ScenarioRunResult:
        payload = _mapping(payload, "scenario")
        _strict_keys(payload, _SCENARIO_KEYS, "scenario")

        schema_version = payload.get("schema_version", 1)
        if isinstance(schema_version, bool) or schema_version != 1:
            raise ValueError("unsupported scenario schema_version")

        name = payload.get("name")
        if not isinstance(name, str) or not name.strip() or len(name) > 120:
            raise ValueError("scenario.name must be non-empty text up to 120 characters")

        start = _aware_datetime(payload.get("start_utc"), "scenario.start_utc")
        control_engine = ControlEngineConfig.from_dict(
            _mapping(payload.get("control_engine"), "scenario.control_engine")
        )
        raw_steps = _sequence(payload.get("steps"), "scenario.steps")
        if not raw_steps:
            raise ValueError("scenario.steps must contain at least one step")

        clock = _ScenarioClock(start)
        evaluator = PolicyShadowAutomationEvaluator(control_engine.policy, clock=clock)
        tacho_supervisor = TachoShadowSupervisor(clock=clock)
        operator_intent = OperatorControlIntent()
        operator_revision = 0
        results: list[dict[str, Any]] = []
        previous_offset = -1.0

        for index, raw in enumerate(raw_steps):
            step = _mapping(raw, f"scenario.steps[{index}]")
            _strict_keys(step, _STEP_KEYS, f"scenario.steps[{index}]")
            offset = _number(
                step.get("at_seconds"),
                f"scenario.steps[{index}].at_seconds",
                minimum=0.0,
            )
            if offset < previous_offset:
                raise ValueError("scenario step at_seconds values must be non-decreasing")
            previous_offset = offset
            clock.now = start + timedelta(seconds=offset)

            if "operator" in step:
                operator_intent = OperatorControlIntent.from_dict(
                    _mapping(step["operator"], f"scenario.steps[{index}].operator")
                )
                operator_revision += 1

            state = self._build_state(step, now=clock.now, index=index)
            shadow = evaluator.evaluate(state)
            shadow = apply_operator_intent(
                shadow,
                control_engine.policy,
                operator_intent,
                revision=operator_revision,
            )
            shadow = tacho_supervisor.apply(shadow, state, control_engine.policy)
            shadow_payload = shadow.to_dict()
            if shadow_payload.get("actuation_supported") is not False:
                raise RuntimeError("scenario evaluator unexpectedly supports actuation")
            for zone in shadow_payload.get("zones") or []:
                if zone.get("proposed_supply_voltage") is not None:
                    raise RuntimeError("scenario exposed physical supply voltage proposal")
                if zone.get("proposed_extract_voltage") is not None:
                    raise RuntimeError("scenario exposed physical extract voltage proposal")

            results.append(
                {
                    "index": index,
                    "at_seconds": offset,
                    "evaluated_at_utc": clock.now.isoformat(),
                    "operator_intent_revision": operator_revision,
                    "actual_setpoints": {
                        "supply_voltage": state.setpoints.supply_voltage,
                        "extract_voltage": state.setpoints.extract_voltage,
                    },
                    "shadow": shadow_payload,
                }
            )

        return ScenarioRunResult(
            name=name,
            start_utc=start.isoformat(),
            policy_version=control_engine.policy.version,
            steps=tuple(results),
        )

    def _build_state(
        self,
        step: Mapping[str, Any],
        *,
        now: datetime,
        index: int,
    ) -> CoreState:
        calendar = self._calendar(step.get("calendar"), now=now, index=index)
        sensor_1 = self._sensor(step.get("sensor_1"), address=1, now=now, index=index)
        sensor_2 = self._sensor(step.get("sensor_2"), address=2, now=now, index=index)
        sensor_bus = SensorBusState(
            port="scenario://sen55",
            baudrate=19200,
            addresses=(1, 2),
            ready=True,
            worker_alive=True,
            last_cycle_at=now.isoformat(),
            nodes=(sensor_1, sensor_2),
        )
        zigbee = self._zigbee(step, now=now, index=index)
        setpoints = self._actual_setpoints(step.get("actual_setpoints"), index=index)
        tacho = self._tacho(step.get("tacho"), index=index)

        hardware_ready = step.get("hardware_ready", True)
        output_state_known = step.get("output_state_known", True)
        critical_alarm = step.get("critical_alarm", False)
        hardware_ready = _boolean(hardware_ready, f"scenario.steps[{index}].hardware_ready")
        output_state_known = _boolean(
            output_state_known,
            f"scenario.steps[{index}].output_state_known",
        )
        critical_alarm = _boolean(critical_alarm, f"scenario.steps[{index}].critical_alarm")

        alarms: tuple[AlarmState, ...] = ()
        if critical_alarm:
            alarms = (
                AlarmState(
                    code=AlarmCode.DAC_COMMUNICATION_LOST,
                    severity=AlarmSeverity.CRITICAL,
                    message="Synthetic scenario critical safety fault",
                    active_since=now.isoformat(),
                    last_error="scenario",
                    occurrences=1,
                ),
            )

        return CoreState(
            mode=(
                VentilationMode.MANUAL
                if setpoints.supply_voltage > 0.0 or setpoints.extract_voltage > 0.0
                else VentilationMode.STOP
            ),
            setpoints=setpoints,
            hardware_ready=hardware_ready,
            output_state_known=output_state_known,
            active_alarms=alarms,
            sensor_bus=sensor_bus,
            tacho=tacho,
            zigbee=zigbee,
            calendar=calendar,
        )

    def _actual_setpoints(self, raw: Any, *, index: int) -> FanSetpoints:
        if raw is None:
            return FanSetpoints.stopped()
        field = f"scenario.steps[{index}].actual_setpoints"
        payload = _mapping(raw, field)
        _strict_keys(payload, _ACTUAL_SETPOINT_KEYS, field)
        return FanSetpoints(
            supply_voltage=_fan_voltage(
                payload.get("supply_voltage", 0.0), f"{field}.supply_voltage"
            ),
            extract_voltage=_fan_voltage(
                payload.get("extract_voltage", 0.0), f"{field}.extract_voltage"
            ),
        )

    def _tacho(self, raw: Any, *, index: int) -> TachoMonitorState | None:
        if raw is None:
            return None
        field = f"scenario.steps[{index}].tacho"
        payload = _mapping(raw, field)
        _strict_keys(payload, _TACHO_KEYS, field)
        ready = _boolean(payload.get("ready", True), f"{field}.ready")
        worker_alive = _boolean(payload.get("worker_alive", True), f"{field}.worker_alive")
        supply = self._tacho_channel(payload, field=field, channel="supply")
        extract = self._tacho_channel(payload, field=field, channel="extract")
        return TachoMonitorState(
            chip_path="scenario://gpiochip",
            ready=ready,
            worker_alive=worker_alive,
            last_error=None if ready and worker_alive else "scenario tacho monitor unavailable",
            supply=supply,
            extract=extract,
        )

    def _tacho_channel(
        self,
        payload: Mapping[str, Any],
        *,
        field: str,
        channel: str,
    ) -> FanTachoState | None:
        present = _boolean(payload.get(f"{channel}_present", True), f"{field}.{channel}_present")
        if not present:
            return None
        valid = _boolean(payload.get(f"{channel}_valid", False), f"{field}.{channel}_valid")
        rpm = _number(payload.get(f"{channel}_rpm", 0.0), f"{field}.{channel}_rpm", minimum=0.0)
        return FanTachoState(
            line_name="GPIO17" if channel == "supply" else "GPIO27",
            line_offset=17 if channel == "supply" else 27,
            frequency_hz=rpm / 20.0,
            rpm=rpm,
            sample_count=6 if valid else 0,
            age_seconds=0.01 if valid else 1.0,
            valid=valid,
        )

    def _calendar(self, raw: Any, *, now: datetime, index: int) -> CalendarResolution:
        payload = _mapping(raw, f"scenario.steps[{index}].calendar")
        _strict_keys(payload, _CALENDAR_KEYS, f"scenario.steps[{index}].calendar")

        phase_raw = payload.get("phase")
        mode_raw = payload.get("mode")
        if not isinstance(phase_raw, str):
            raise ValueError(f"scenario.steps[{index}].calendar.phase must be text")
        if not isinstance(mode_raw, str):
            raise ValueError(f"scenario.steps[{index}].calendar.mode must be text")
        try:
            phase = CalendarPhase(phase_raw)
            mode = CalendarMode(mode_raw)
        except ValueError as exc:
            raise ValueError(f"scenario.steps[{index}].calendar contains unsupported enum") from exc

        profile = payload.get("profile", "SCENARIO")
        if not isinstance(profile, str) or not profile.strip():
            raise ValueError(f"scenario.steps[{index}].calendar.profile must be non-empty text")
        supply = _percentage(
            payload.get("schedule_supply_pct", 0.0),
            f"scenario.steps[{index}].calendar.schedule_supply_pct",
        )
        extract = _percentage(
            payload.get("schedule_extract_pct", 0.0),
            f"scenario.steps[{index}].calendar.schedule_extract_pct",
        )
        source = payload.get("schedule_request_source", "SCENARIO")
        if not isinstance(source, str) or not source.strip():
            raise ValueError(
                f"scenario.steps[{index}].calendar.schedule_request_source must be non-empty text"
            )

        return CalendarResolution(
            available=True,
            timezone="Europe/Warsaw",
            evaluated_at_utc=now.isoformat(),
            local_time=now.isoformat(),
            phase=phase,
            effective_profile=profile,
            effective_mode=mode,
            rule_id="SCENARIO",
            schedule_supply_pct=supply,
            schedule_extract_pct=extract,
            schedule_request_source=source,
        )

    def _sensor(
        self,
        raw: Any,
        *,
        address: int,
        now: datetime,
        index: int,
    ) -> SensorNodeState:
        field = f"scenario.steps[{index}].sensor_{address}"
        payload = _mapping(raw, field)
        _strict_keys(payload, _SENSOR_KEYS, field)
        usable = _boolean(payload.get("usable", True), f"{field}.usable")

        reading = AirQualityReading(
            pm2_5_ug_m3=_optional_number(payload.get("pm2_5_ug_m3"), f"{field}.pm2_5_ug_m3"),
            pm10_0_ug_m3=_optional_number(payload.get("pm10_0_ug_m3"), f"{field}.pm10_0_ug_m3"),
            temperature_celsius=_optional_number(
                payload.get("temperature_celsius"), f"{field}.temperature_celsius"
            ),
            voc_index=_optional_number(payload.get("voc_index"), f"{field}.voc_index"),
            nox_index=_optional_number(payload.get("nox_index"), f"{field}.nox_index"),
        )
        return SensorNodeState(
            slave_address=address,
            online=usable,
            usable=usable,
            measurement_valid=usable,
            measurement_stale=not usable,
            sensor_present=True,
            reading=reading,
            age_seconds=0 if usable else None,
            last_success_at=now.isoformat() if usable else None,
            polls=index + 1,
            successful_polls=index + 1 if usable else 0,
        )

    def _zigbee(self, step: Mapping[str, Any], *, now: datetime, index: int) -> ZigbeeMqttState:
        devices = (
            self._zigbee_device(
                step.get("zigbee_supply"), role="supply", now=now, index=index
            ),
            self._zigbee_device(
                step.get("zigbee_extract"), role="extract", now=now, index=index
            ),
        )
        return ZigbeeMqttState(
            broker_host="scenario",
            broker_port=1883,
            base_topic="scenario",
            running=True,
            connected=True,
            connected_at=now.isoformat(),
            last_message_at=now.isoformat(),
            bridge_online=True,
            devices=devices,
        )

    def _zigbee_device(
        self,
        raw: Any,
        *,
        role: str,
        now: datetime,
        index: int,
    ) -> ZigbeeTemperatureSensorState:
        field = f"scenario.steps[{index}].zigbee_{role}"
        if raw is None:
            raw = {"temperature_celsius": None, "timestamp_available": False}
        payload = _mapping(raw, field)
        _strict_keys(payload, _ZIGBEE_KEYS, field)
        temperature = _optional_number(
            payload.get("temperature_celsius"), f"{field}.temperature_celsius"
        )
        age = _number(payload.get("age_seconds", 0.0), f"{field}.age_seconds", minimum=0.0)
        available = _boolean(payload.get("available", True), f"{field}.available")
        timestamp_available = _boolean(
            payload.get("timestamp_available", True), f"{field}.timestamp_available"
        )
        timestamp = None
        if timestamp_available:
            timestamp = (now - timedelta(seconds=age)).isoformat()

        return ZigbeeTemperatureSensorState(
            role=role,
            friendly_name=f"scenario_{role}",
            ieee_address=f"scenario-{role}",
            topic=f"scenario/{role}",
            available=available,
            temperature_celsius=temperature,
            last_seen=timestamp,
            last_message_at=timestamp,
            messages=1,
        )
