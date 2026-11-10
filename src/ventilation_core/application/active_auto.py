"""Local *actuating* workshop AUTO. Core owns all output writes, never the AI or GUI.

This module is intentionally separate from the historical non-actuating SHADOW
evaluator. Its outputs use operator-reviewed preset voltages; they MUST NOT be
misrepresented as certified air volumes or occupational exposure limits.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from time import monotonic
from typing import Any, Callable, Mapping
import json
from math import isfinite
import logging
import os
import time

from ventilation_core.domain.aero_control import AeroControlCommand

LOGGER = logging.getLogger(__name__)

# Commissioning candidates from 2026-11-07 measured point velocities.
# Supply/extract are independent voltage setpoints, NOT equal-percent DAC commands.
# No direct m3/h feedback: these are field-test candidates, not guaranteed flow.
@dataclass(frozen=True)
class Preset:
    supply_v: float
    extract_v: float
    aero_speed: int
    airing: bool = False

PRESETS: dict[str, Preset] = {
    "ECO": Preset(2.0, 1.0, 1),
    "NORMAL": Preset(4.0, 3.0, 1),
    "BOOST": Preset(7.0, 5.0, 2),
    "HIGH": Preset(9.0, 6.0, 3),
    "MAX": Preset(10.0, 7.0, 3, True),
    # Loss of one SEN55 is NOT interpreted as clean air.
    "SENSOR_FAULT": Preset(4.0, 3.0, 2),
}

AQ_ORDER = {"ECO": 0, "NORMAL": 1, "BOOST": 2, "HIGH": 3, "MAX": 4}
AQ_LEVELS = ("NORMAL", "BOOST", "HIGH", "MAX")

DEFAULT_THRESHOLDS = {
    "pm2_5": [15.0, 25.0, 50.0],
    "voc_index": [150.0, 200.0, 300.0],
    "nox_index": [10.0, 50.0, 100.0],
}


def load_tuning(path: Path | None) -> tuple[dict[str, Preset], dict[str, tuple[float, float, float]], dict[str, float]]:
    """Validate a complete versioned JSON profile before enabling any actuator.

    Percentages and voltages are explicit operator-chosen commissioning candidates,
    never inferred from point velocity or interpreted as legal pollutant limits.
    """
    presets = dict(PRESETS)
    thresholds = {name: tuple(x) for name, x in DEFAULT_THRESHOLDS.items()}
    dynamics = {"up_boost_seconds": 15.0, "up_high_seconds": 5.0,
                "decay_seconds": 180.0, "thermal_eco_celsius": 18.0}
    if path is None:
        return presets, thresholds, dynamics
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        raise ValueError("AUTO profile schema_version must equal 1")
    if set(data) != {"schema_version", "presets", "thresholds", "dynamics"}:
        raise ValueError("AUTO profile requires exact keys")
    if not isinstance(data["presets"], dict) or set(data["presets"]) != set(PRESETS):
        raise ValueError("AUTO profile requires all six named presets")
    presets = {}
    for name, raw in data["presets"].items():
        if not isinstance(raw, dict) or set(raw) != {"supply_v", "extract_v", "aero_speed", "airing"}:
            raise ValueError(f"Malformed AUTO preset {name}")
        if any(isinstance(raw[f], bool) or not isinstance(raw[f], (int, float))
               or not isfinite(float(raw[f])) or not 1.0 <= raw[f] <= 10.0
               for f in ("supply_v", "extract_v")):
            raise ValueError(f"Invalid AUTO fan voltages for {name}")
        if type(raw["aero_speed"]) is not int or raw["aero_speed"] not in (1, 2, 3):
            raise ValueError(f"Invalid AERO speed for {name}")
        if type(raw["airing"]) is not bool or (name != "MAX" and raw["airing"]):
            raise ValueError(f"AERO airing only allowed for MAX: {name}")
        presets[name] = Preset(float(raw["supply_v"]), float(raw["extract_v"]),
                               raw["aero_speed"], raw["airing"])
    for field in ("supply_v", "extract_v", "aero_speed"):
        values = [getattr(presets[name],field) for name in ("ECO", "NORMAL", "BOOST", "HIGH", "MAX")]
        if values != sorted(values):
            raise ValueError(f"AUTO {field} must be monotonic ECO..MAX")
    if not isinstance(data["thresholds"], dict) or set(data["thresholds"]) != set(DEFAULT_THRESHOLDS):
        raise ValueError("AUTO requires 3 documented process threshold families")
    thresholds = {}
    for name, vals in data["thresholds"].items():
        if not isinstance(vals, list) or len(vals) != 3 or any(
            isinstance(v, bool) or not isinstance(v, (int, float))
            or not isfinite(float(v)) or v <= 0 for v in vals
        ) or vals != sorted(set(vals)):
            raise ValueError(f"Invalid AUTO process thresholds: {name}")
        thresholds[name] = tuple(float(x) for x in vals)
    if not isinstance(data["dynamics"], dict) or set(data["dynamics"]) != set(dynamics):
        raise ValueError("AUTO dynamics missing fields")
    for name, val in data["dynamics"].items():
        if (isinstance(val, bool) or not isinstance(val,(float,int))
            or not isfinite(float(val)) or not 0 < val <= 3600):
            raise ValueError(f"Invalid AUTO dynamic parameter: {name}")
        dynamics[name] = float(val)
    return presets, thresholds, dynamics


REQUIRED_APPROVAL_ITEMS = (
    "occupational_risk_assessment",
    "soldering_local_exhaust",
    "fan_airflow_commissioning",
    "aero_physical_confirmation",
    "tacho_fault_procedure",
    "sensor_loss_procedure",
    "independent_co_protection_if_applicable",
    "manual_override_and_stop",
)


def commissioning_approved(path: Path | None) -> tuple[bool, str]:
    """Do not turn the observational Control Engine into live actuation by flag alone."""
    if path is None or not path.is_file():
        return False, "WORKSHOP_COMMISSIONING_APPROVAL_MISSING"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if (data.get("schema_version") != 1
            or data.get("site") != "WVC_WORKSHOP"
            or data.get("approval") != "APPROVED"
            or not isinstance(data.get("responsible_person"), str)
            or not data["responsible_person"].strip()
            or not isinstance(data.get("evidence"), dict)
            or any(not isinstance(data["evidence"].get(key), str)
                   or not data["evidence"][key].strip() for key in REQUIRED_APPROVAL_ITEMS)):
            return False, "WORKSHOP_COMMISSIONING_EVIDENCE_INCOMPLETE"
    except (OSError, ValueError, KeyError, AttributeError, TypeError):
        return False, "WORKSHOP_COMMISSIONING_APPROVAL_INVALID"
    return True, ""


def _usable_node(state: Mapping[str, Any], address: int) -> Mapping[str, Any] | None:
    bus = state.get("sensor_bus")
    for node in (bus or {}).get("nodes", []):
        if node.get("slave_address") != address:
            continue
        if (node.get("online") is True and node.get("usable") is True
            and node.get("measurement_valid") is True
            and node.get("measurement_stale") is False):
            return node
    return None


def _air_quality(node: Mapping[str, Any] | None,
                 thresholds: Mapping[str, tuple[float, float, float]] | None = None) -> tuple[str, str]:
    if node is None:
        return "SENSOR_FAULT", "SEN55_UNAVAILABLE"
    data = node.get("reading") or {}
    pm, voc, nox = (data.get(key) for key in ("pm2_5_ug_m3", "voc_index", "nox_index"))
    if not all(isinstance(x, (int, float)) and not isinstance(x, bool)
               and isfinite(float(x)) and x >= 0 for x in (pm, voc, nox)):
        return "SENSOR_FAULT", "SEN55_INCOMPLETE_OR_NONFINITE"
    # PROCESS threshold candidates; NOT WHO/NDS instantaneous legal limits.
    limits = thresholds or DEFAULT_THRESHOLDS
    pm_boost, pm_high, pm_max = limits["pm2_5"]
    voc_boost, voc_high, voc_max = limits["voc_index"]
    nox_boost, nox_high, nox_max = limits["nox_index"]
    if pm > pm_max or voc > voc_max or nox > nox_max:
        return "MAX", "PM2.5/VOC/NOX_MAX"
    if pm > pm_high or voc >= voc_high or nox > nox_high:
        return "HIGH", "PM2.5/VOC/NOX_HIGH"
    if pm > pm_boost or voc >= voc_boost or nox > nox_boost:
        return "BOOST", "PM2.5/VOC/NOX_BOOST"
    return "NORMAL", "SEN55_NORMAL"


@dataclass
class _ZoneDynamics:
    effective: str | None = None
    upward_candidate: str | None = None
    upward_since: float = 0.0
    lower_since: float = 0.0


class ActiveWorkshopAuto:
    """Deterministic core-local actuator scheduler with persistent operator hold.

    Enablement is explicit at systemd startup and requires a commissioned JSON
    profile. A manual SET/STOP/ AERO command latches HOLD until AUTO RESUME, and
    HOLD survives reboot. No background agent can silently override the operator.
    """

    def __init__(
        self,
        *,
        enabled: bool,
        hold_path: Path,
        clock: Callable[[], float] = monotonic,
        fan_min_interval: float = 15.0,
        aero_min_interval: float = 40.0,
        aero_target_timeout_seconds: float = 25.0,
        aero_target_poll_seconds: float = 2.0,
        profile_path: Path | None = None,
        blocked_reason: str = "",
        startup_manual_hold: bool = True,
    ) -> None:
        self._presets, self._thresholds, self._dynamics = load_tuning(profile_path)
        self.enabled = bool(enabled)
        self.blocked_reason = blocked_reason
        self._clock = clock
        self._hold_path = hold_path
        self._lock = RLock()
        self.paused = hold_path.exists()
        self.pause_reason = "PERSISTED_OPERATOR_HOLD" if self.paused else ""
        self._fault_latched = False
        self._fault_mask: str | None = None
        if self.paused:
            try:
                persisted = json.loads(hold_path.read_text(encoding="utf-8"))
                self.pause_reason = str(persisted.get("reason") or "PERSISTED_OPERATOR_HOLD")
                self._fault_latched = persisted.get("fault_latched") is True
                mask = persisted.get("fault_mask")
                self._fault_mask = mask if isinstance(mask,str) else None
            except (OSError, ValueError, TypeError):
                # A corrupt hold file must still block all future auto writes.
                self.pause_reason = "PERSISTED_HOLD_FILE_INVALID"
                self._fault_latched = True
        self.last_error = ""
        self.last_action: dict[str, Any] | None = None
        self.last_evaluated_at_utc: str | None = None
        self.last_decisions: dict[str, dict[str, Any]] = {}
        self.fan_min_interval = fan_min_interval
        self.aero_min_interval = aero_min_interval
        if not 0 < aero_target_poll_seconds <= aero_target_timeout_seconds <= 60:
            raise ValueError("Invalid AERO target confirmation interval/timeout")
        self.aero_target_poll_seconds = aero_target_poll_seconds
        self.aero_target_timeout_seconds = aero_target_timeout_seconds
        self._fan_last_set_at: float | None = None
        self._aero_last_set_at: float | None = None
        self._last_aero_mode: str | None = None
        self._zones = {1: _ZoneDynamics(), 2: _ZoneDynamics()}
        self._tacho_missing_since: dict[str, float | None] = {"supply": None, "extract": None}
        if self.enabled:
            # A reboot must not silently erase an operator HOLD due to a
            # read-only/full filesystem. Disable AUTO if persistence is broken.
            try:
                self._hold_path.parent.mkdir(parents=True, exist_ok=True)
                probe = self._hold_path.parent / ".auto-hold-write-probe"
                with probe.open("x", encoding="utf-8") as output:
                    output.write("ok")
                probe.unlink()
            except OSError as exc:
                self.enabled = False
                self.blocked_reason = "AUTO_HOLD_STORAGE_UNAVAILABLE"
                LOGGER.error("ACTIVE_AUTO disabled: cannot persist operator HOLD: %s", exc)
        if self.enabled and startup_manual_hold and not self.paused:
            # Never energize fans solely because the CM5 has rebooted.
            self.hold("BOOT_MANUAL_REQUIRES_EXPLICIT_AUTO_RESUME")

    def hold(
        self,
        reason: str = "OPERATOR",
        *,
        fault: bool = False,
        fault_mask: str | None = None,
    ) -> None:
        """Latch MANUAL/HOLD before any future automated output write.

        Faults are persisted separately from ordinary manual handoff. AUTO
        resume after a fault requires an explicit local fault acknowledgement.
        """
        with self._lock:
            self.paused = True
            self.pause_reason = reason
            if fault:
                self._fault_latched = True
                self._fault_mask = fault_mask
            try:
                self._hold_path.parent.mkdir(parents=True, exist_ok=True)
                temp = self._hold_path.with_suffix(".tmp")
                temp.write_text(
                    json.dumps({
                        "reason": reason,
                        "at": datetime.now(timezone.utc).isoformat(),
                        "fault_latched": self._fault_latched,
                        "fault_mask": self._fault_mask,
                    }),
                    encoding="utf-8",
                )
                os.replace(temp, self._hold_path)
            except OSError as exc:
                self.last_error = f"HOLD_PERSISTENCE_FAILED:{type(exc).__name__}"
                LOGGER.critical("AUTO hold persistence failed: %s", exc)
            LOGGER.warning("ACTIVE_AUTO HOLD: %s", reason)

    def acknowledge_fault(self, state: Mapping[str, Any]) -> None:
        """Local service acknowledgement. Never resumes AUTO by itself."""
        with self._lock:
            if not self.paused or not self._fault_latched:
                raise RuntimeError("No latched AUTO fault awaiting acknowledgement")
            if state.get("mode") != "STOP" or state.get("setpoints") != {
                "supply_voltage": 0.0, "extract_voltage": 0.0
            }:
                raise RuntimeError("Cannot acknowledge fault unless EC outputs are STOP / 0 V")
            if not state.get("hardware_ready") or not state.get("output_state_known"):
                raise RuntimeError("Cannot acknowledge fault: DAC not ready")
            tacho = state.get("tacho") or {}
            if not (tacho.get("ready") and tacho.get("worker_alive")):
                raise RuntimeError("Cannot acknowledge fault: TACHO worker unavailable")
            if any(a.get("severity") == "critical" for a in state.get("active_alarms") or []):
                raise RuntimeError("Cannot acknowledge fault with active critical alarms")
            self._fault_latched = False
            self._fault_mask = None
            self.hold("OPERATOR_MANUAL_AFTER_FAULT_ACK")
            LOGGER.warning("AUTO fault acknowledged locally; MANUAL remains active")

    def _fault_stop_ec(self, service: Any, reason: str, *, mask: str | None = None) -> None:
        """Conservative hardware imbalance response: stop BOTH EC outputs.

        Stops uncontrolled supply/negative pressure excursions, but is NOT an
        assurance of occupational air safety. Work emitting fumes must halt
        and personnel must use the independently approved site procedure.
        """
        with self._lock:
            self.last_error = reason
            self.hold(reason, fault=True, fault_mask=mask)
            try:
                service.stop()
                LOGGER.error("ACTIVE_AUTO FAULT: both EC outputs forced 0 V; %s", reason)
            except Exception as exc:
                self.last_error = f"{reason}:EC_STOP_FAILED:{type(exc).__name__}"
                LOGGER.critical("Cannot verify 0 V on TACHO fault: %s", exc)

    def resume(self, state: Mapping[str, Any]) -> None:
        with self._lock:
            if not self.enabled:
                raise RuntimeError("Active AUTO is not enabled in core configuration")
            if self._fault_latched:
                raise RuntimeError("Latched AUTO fault requires local service acknowledgement")
            if any(a.get("severity") == "critical" for a in state.get("active_alarms") or []):
                raise RuntimeError("Cannot resume AUTO: active critical alarm")
            if not state.get("hardware_ready") or not state.get("output_state_known"):
                raise RuntimeError("Cannot resume AUTO: DAC hardware not ready")
            if not (state.get("tacho") or {}).get("ready"):
                raise RuntimeError("Cannot resume AUTO: TACHO unavailable")
            if not (state.get("aero_bus") or {}).get("usable"):
                raise RuntimeError("Cannot resume AUTO: AERO unavailable")
            if any(
                _air_quality(_usable_node(state, address), self._thresholds)[0]
                == "SENSOR_FAULT" for address in (1, 2)
            ):
                raise RuntimeError("Cannot resume AUTO: both SEN55 must have valid readings")
            self._hold_path.unlink(missing_ok=True)
            self.paused = False
            self.pause_reason = ""
            self.last_error = ""
            self._fan_last_set_at = None
            self._aero_last_set_at = None
            self._last_aero_mode = None
            self._zones = {1: _ZoneDynamics(), 2: _ZoneDynamics()}
            self._tacho_missing_since = {"supply": None, "extract": None}
            LOGGER.warning("ACTIVE_AUTO resumed by explicit operator command")

    def _handoff_if_inputs_unavailable(self, state: Mapping[str, Any]) -> bool:
        """Fail over to operator MANUAL without issuing replacement fan commands.

        Losing SEN55 readings or AERO feedback means AUTO can no longer make
        reliable decisions. Preserve the last *physical* settings rather than
        silently reducing an existing HIGH/MAX demand to a generic fallback.

        This persistent HOLD blocks only the automatic writer; it does not
        disable WebGUI manual EC/AERO controls or the physical STOP command.
        A new AUTO resume is explicit and uses the existing health preflight.
        """
        missing = [
            str(address) for address in (1, 2)
            if _air_quality(_usable_node(state, address), self._thresholds)[0]
            == "SENSOR_FAULT"
        ]
        if missing:
            reason = "SEN55_" + "_".join(missing) + "_UNAVAILABLE"
            self.last_error = reason
            self.hold(reason)
            LOGGER.error("ACTIVE_AUTO handoff to MANUAL: %s", reason)
            return True
        aero = state.get("aero_bus") or {}
        if not (aero.get("ready") and aero.get("online") and aero.get("usable")):
            reason = "AERO_UNAVAILABLE"
            self.last_error = reason
            self.hold(reason)
            LOGGER.error("ACTIVE_AUTO handoff to MANUAL: %s", reason)
            return True
        return False

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "enabled": self.enabled, "active": self.enabled and not self.paused,
                "blocked_reason": self.blocked_reason,
                "hold": self.paused, "hold_reason": self.pause_reason,
                "mode": ("MANUAL" if (self.paused or not self.enabled) else "AUTO"),
                "fault_latched": self._fault_latched,
                "fault_mask": self._fault_mask,
                "operator_action": (
                    "STOP_HAZARDOUS_WORK_AND_CHECK_VENTILATION"
                    if (self._fault_latched or self.pause_reason.startswith(
                        ("SEN55_", "AERO_UNAVAILABLE")
                    )) else None
                ),
                "last_error": self.last_error, "last_action": self.last_action,
                "evaluated_at_utc": self.last_evaluated_at_utc,
                "zones": dict(self.last_decisions),
                "control_owner": "ventilation-core",
            }

    def _stable_level(self, address: int, raw: str, now: float) -> str:
        st = self._zones[address]
        if raw == "SENSOR_FAULT":
            st.effective = "SENSOR_FAULT"
            st.upward_candidate = None
            st.lower_since = 0.0
            return raw
        if st.effective is None or st.effective == "SENSOR_FAULT":
            st.effective = raw
            return raw
        if AQ_ORDER[raw] == AQ_ORDER[st.effective]:
            st.upward_candidate = None
            st.lower_since = 0.0
            return st.effective
        if AQ_ORDER[raw] > AQ_ORDER[st.effective]:
            st.lower_since = 0.0
            if st.upward_candidate != raw:
                st.upward_candidate = raw
                st.upward_since = now
            # MAX/HIGH respond promptly; BOOST requires sustained increase.
            confirm_seconds = (self._dynamics["up_high_seconds"]
                               if raw in {"MAX", "HIGH"}
                               else self._dynamics["up_boost_seconds"])
            if now - st.upward_since >= confirm_seconds:
                st.effective = raw
                st.upward_candidate = None
            return st.effective
        st.upward_candidate = None
        if st.lower_since == 0.0:
            st.lower_since = now
        # Deliberately slow decrease to avoid rapid oscillation.
        if now - st.lower_since >= self._dynamics["decay_seconds"]:
            st.effective = raw
            st.lower_since = 0.0
        return st.effective

    def _evaluate(self, state: Mapping[str, Any], now: float) -> tuple[Preset, Preset]:
        calendar = state.get("calendar") or {}
        occupied = calendar.get("phase") in ("PREVENTILATION", "ACTIVE", "PURGE")
        result: dict[str, dict[str, Any]] = {}
        presets: list[Preset] = []
        for address, zone in ((1, "ec"), (2, "aero")):
            node = _usable_node(state, address)
            raw, reason = _air_quality(node, self._thresholds)
            level = self._stable_level(address, raw, now)
            if level == "NORMAL":
                level = "NORMAL" if occupied else "ECO"
                # Heat protection only when air quality requires no BOOST.
                if address == 1 and node is not None:
                    temperature = (node.get("reading") or {}).get("temperature_celsius")
                    if (isinstance(temperature, (float,int))
                        and temperature < self._dynamics["thermal_eco_celsius"]):
                        level = "ECO"
                        reason = "THERMAL_ECO_WHEN_AIR_NORMAL"
            preset = self._presets[level]
            result[zone] = {
                "zone": f"zone-{address}", "level": level,
                "raw_air_quality": raw, "reason": reason,
                "sensor_usable": node is not None, "occupied_scheduled": occupied,
                "supply_v": preset.supply_v if address == 1 else None,
                "extract_v": preset.extract_v if address == 1 else None,
                "aero_speed": preset.aero_speed if address == 2 else None,
                "aero_airing": preset.airing if address == 2 else None,
            }
            presets.append(preset)
        self.last_decisions = result
        self.last_evaluated_at_utc = datetime.now(timezone.utc).isoformat()
        return presets[0], presets[1]

    def _check_tacho(self, state: Mapping[str, Any], now: float) -> None:
        # The physical Stage7D test validated a 4s confirmation window.
        # Spin-up grace is 12s after each voltage change; then require 4s of
        # continuously missing feedback before declaring a channel fault.
        if self._fan_last_set_at is None or now - self._fan_last_set_at < 12:
            return
        if state.get("mode") != "AUTO":
            return
        tacho = state.get("tacho") or {}
        failed: list[str] = []
        for name in ("supply", "extract"):
            reading = tacho.get(name) or {}
            good = (reading.get("valid") is True
                    and isinstance(reading.get("rpm"), (int,float))
                    and isfinite(float(reading["rpm"]))
                    and float(reading["rpm"]) >= 80)
            if good:
                self._tacho_missing_since[name] = None
            else:
                if self._tacho_missing_since[name] is None:
                    self._tacho_missing_since[name] = now
                if now - self._tacho_missing_since[name] >= 4:
                    failed.append(name)
        if failed:
            mask = "BOTH" if len(failed) == 2 else failed[0].upper()
            raise RuntimeError(f"TACHO_{mask}_FEEDBACK_MISSING")

    @staticmethod
    def _aero_pair_matches(state: Mapping[str, Any], action: str) -> bool:
        aero = state.get("aero_bus") or {}
        if not (aero.get("ready") and aero.get("online") and aero.get("usable")):
            return False
        telem = aero.get("telemetry") or {}
        values = (telem.get("fan_1_percent"), telem.get("fan_2_percent"))
        if any(type(x) not in (int, float) or not isfinite(float(x)) for x in values):
            return False
        if action == "aero_airing_on":
            return all(x >= 95 for x in values)
        if action == "aero_airing_off":
            return all(x < 95 for x in values)
        if action.startswith("aero_speed_"):
            target = 30 * int(action.split("_")[-1])
            return all(abs(x-target) <= 5 for x in values)
        return False

    def _verify_aero_both(self, service: Any, action: str) -> bool:
        """Read actual fan 1+2 after AERO accepted a command.

        Existing low-level executor reports physical success on *any* power
        change: on a real 60->90% ramp one fan reaches the target earlier
        than the other. Never treat that intermediate response as complete.
        """
        until = time.monotonic() + self.aero_target_timeout_seconds
        while True:
            with self._lock:
                if self.paused:
                    return False
            state = service.state().to_dict()
            if self._aero_pair_matches(state, action):
                return True
            if time.monotonic() >= until:
                return False
            time.sleep(self.aero_target_poll_seconds)

    def supervise(self, service: Any) -> None:
        """Independent EC watchdog, including during slow AERO RS485 commands.

        Invoked from a separate asyncio task with its own thread. The AERO
        response (sometimes 60s) must not delay detecting lost EC feedback.
        Safety HOLD is latched and persisted; a separate *approved* physical
        fallback remains required before unattended GO.
        """
        if not self.enabled:
            return
        with self._lock:
            if self.paused:
                return
            s = service.state().to_dict()
            if not s.get("hardware_ready") or not s.get("output_state_known"):
                self._fault_stop_ec(service, "DAC_NOT_READY")
                return
            if any(a.get("severity") == "critical" for a in s.get("active_alarms") or []):
                self._fault_stop_ec(service, "CRITICAL_ALARM")
                return
            try:
                self._check_tacho(s, self._clock())
            except RuntimeError as exc:
                reason = str(exc)
                mask = reason.removeprefix("TACHO_").split("_")[0]
                self._fault_stop_ec(service, reason, mask=mask)
                return
            self._handoff_if_inputs_unavailable(s)

    def step(self, service: Any) -> None:
        if not self.enabled:
            return
        with self._lock:
            if self.paused:
                return
            state = service.state().to_dict()
            now = self._clock()
            if not state.get("hardware_ready") or not state.get("output_state_known"):
                self._fault_stop_ec(service, "DAC_NOT_READY")
                return
            if any(a.get("severity") == "critical" for a in state.get("active_alarms") or []):
                self._fault_stop_ec(service, "CRITICAL_ALARM")
                return
            try:
                self._check_tacho(state, now)
            except RuntimeError as exc:
                reason = str(exc)
                mask = reason.removeprefix("TACHO_").split("_")[0]
                self._fault_stop_ec(service, reason, mask=mask)
                return
            # Before ANY new EC/AERO command, require reliable input streams.
            # TACHO safety is checked above first and still forces both EC OFF.
            if self._handoff_if_inputs_unavailable(state):
                return
            ec, aero = self._evaluate(state, now)

            current = state.get("setpoints") or {}
            supply = float(current.get("supply_voltage") or 0)
            extract = float(current.get("extract_voltage") or 0)
            if (abs(supply-ec.supply_v) > .05 or abs(extract-ec.extract_v) > .05
                or state.get("mode") not in ("AUTO",)):
                if self._fan_last_set_at is None or now-self._fan_last_set_at >= self.fan_min_interval:
                    service.set_automatic(ec.supply_v, ec.extract_v)
                    self._fan_last_set_at = now
                    self._tacho_missing_since = {"supply": None, "extract": None}
                    self.last_action = {"target":"ec","supply_v":ec.supply_v,
                                        "extract_v":ec.extract_v,"at":self.last_evaluated_at_utc}
                    LOGGER.warning("ACTIVE_AUTO EC %s: %.1fV/%.1fV",
                                   self.last_decisions["ec"]["level"],ec.supply_v,ec.extract_v)

            bus = state.get("aero_bus") or {}
            if not (bus.get("ready") and bus.get("online") and bus.get("usable")):
                self.last_error = "AERO_UNAVAILABLE"
                return
            if bus.get("control_busy"):
                return
            if self._aero_last_set_at is not None and now-self._aero_last_set_at < self.aero_min_interval:
                return
            telem = bus.get("telemetry") or {}
            actual = [telem.get("fan_1_percent"), telem.get("fan_2_percent")]
            if any(x is None for x in actual):
                self.last_error = "AERO_TELEMETRY_MISSING"
                return
            if aero.airing and not all(x >= 95 for x in actual):
                if not all(x >= 85 for x in actual):
                    command = AeroControlCommand.set_speed(3)
                    action = "aero_speed_3"
                else:
                    command = AeroControlCommand.set_airing(True)
                    action = "aero_airing_on"
            elif not aero.airing and any(x >= 95 for x in actual):
                command = AeroControlCommand.set_airing(False)
                action = "aero_airing_off"
            elif not aero.airing and any(abs(float(x)-30*aero.aero_speed) > 9 for x in actual):
                command = AeroControlCommand.set_speed(aero.aero_speed)
                action = "aero_speed_" + str(aero.aero_speed)
            else:
                self.last_error = ""
                return
            self._aero_last_set_at = now
        # IMPORTANT: physical AERO confirmation may take ~60s. Never hold the
        # status/hold mutex across this call, or the WebGUI could freeze and an
        # operator would be unable to latch HOLD while AERO is responding.
        result = service.control_aero(command)
        # AERO driver can acknowledge the first changed fan before the other
        # reaches the target; use explicit target verification for BOTH fans.
        pair_ok = bool(result.succeeded and result.physical_confirmation)
        if pair_ok:
            pair_ok = self._verify_aero_both(service, action)
        with self._lock:
            if self.paused:
                return  # Manual HOLD may have been requested during AERO transition.
            if not pair_ok:
                self.last_error = f"AERO_TARGET_PAIR_NOT_CONFIRMED:{action}"
                self.hold(self.last_error)
                return
            self.last_error = ""
            self.last_action = {"target":action,"at":self.last_evaluated_at_utc}
            LOGGER.warning("ACTIVE_AUTO AERO %s (both fan powers confirmed)", action)
