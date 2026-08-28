from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ventilation_core.domain.control_engine_config import ControlEngineConfig
from ventilation_core.domain.operator_control import OperatorControlIntent

from .alert_history_app import AlertHistoryWebApplication
from .app import ApiResponse
from .client import CoreClientError


_TUNING_LEVEL_RANK = {
    "UNVALIDATED": 0,
    "SYNTHETIC_VALIDATED": 1,
    "PHYSICAL_VALIDATED": 2,
    "WORKSHOP_VALIDATED": 3,
}


class ControlEngineWebApplication(AlertHistoryWebApplication):
    """WebUI extension for Control Engine SHADOW configuration and observability.

    The browser receives no generic core proxy and no actuation-enable endpoint.
    Configuration updates and operator intent are strictly validated and forwarded
    through fixed, narrow ventilation-core commands only.
    """

    _tuning_validation_path = (
        Path(__file__).resolve().parents[3]
        / "config"
        / "control-engine-tuning-validation-v1.json"
    )

    def handle(self, method: str, path: str, body: Any = None) -> ApiResponse:
        if method == "GET" and path == "/api/v1/control-engine":
            try:
                return self._control_engine()
            except CoreClientError as exc:
                return ApiResponse(503, {"ok": False, "error": str(exc)})

        if method == "POST" and path == "/api/v1/control-engine":
            try:
                return self._control_engine_replace(body)
            except ValueError as exc:
                return ApiResponse(400, {"ok": False, "error": str(exc)})
            except CoreClientError as exc:
                return ApiResponse(503, {"ok": False, "error": str(exc)})

        if method == "GET" and path == "/api/v1/automation/operator":
            try:
                return self._automation_operator()
            except CoreClientError as exc:
                return ApiResponse(503, {"ok": False, "error": str(exc)})

        if method == "POST" and path == "/api/v1/automation/operator":
            try:
                return self._automation_operator_replace(body)
            except ValueError as exc:
                return ApiResponse(400, {"ok": False, "error": str(exc)})
            except CoreClientError as exc:
                return ApiResponse(503, {"ok": False, "error": str(exc)})

        if method == "GET" and path == "/api/v1/automation/tuning-validation":
            try:
                return self._automation_tuning_validation()
            except (OSError, json.JSONDecodeError, ValueError) as exc:
                return ApiResponse(503, {"ok": False, "error": str(exc)})

        if path == "/api/v1/automation/tuning-validation" and method != "GET":
            return ApiResponse(
                405,
                {
                    "ok": False,
                    "error": "Tuning validation ledger is read-only from WebGUI",
                },
            )

        return super().handle(method, path, body)

    def _control_engine(self) -> ApiResponse:
        response = self._core.request({"command": "control-engine"})
        configuration = response.get("control_engine")
        if response.get("ok") is not True or not isinstance(configuration, dict):
            return self._core_rejection(response)
        if configuration.get("actuation_supported") is not False:
            return ApiResponse(
                502,
                {
                    "ok": False,
                    "error": "Invalid Control Engine safety contract from ventilation-core",
                },
            )
        return ApiResponse(200, response)

    def _control_engine_replace(self, body: Any) -> ApiResponse:
        data = self._require_object(body)
        if set(data) != {"config"}:
            raise ValueError("Control Engine update accepts only the config field")
        raw_config = data.get("config")
        if not isinstance(raw_config, dict):
            raise ValueError("config must be a JSON object")

        # Defense in depth at the browser boundary. Core validates the same contract
        # authoritatively before persistence.
        sanitized = ControlEngineConfig.from_dict(raw_config).to_dict()
        response = self._core.request(
            {"command": "control-engine-replace", "config": sanitized}
        )
        configuration = response.get("control_engine")
        if response.get("ok") is not True or not isinstance(configuration, dict):
            return self._core_rejection(response)
        if configuration.get("actuation_supported") is not False:
            return ApiResponse(
                502,
                {
                    "ok": False,
                    "error": "Invalid Control Engine safety contract from ventilation-core",
                },
            )
        return ApiResponse(200, response)

    def _automation_operator(self) -> ApiResponse:
        response = self._core.request({"command": "control-engine-operator"})
        if response.get("ok") is not True:
            return self._core_rejection(response)
        return ApiResponse(200, response)

    def _automation_operator_replace(self, body: Any) -> ApiResponse:
        data = self._require_object(body)
        # The endpoint body is the operator intent itself. There is deliberately no
        # command selector or generic core payload accepted from the browser.
        sanitized = OperatorControlIntent.from_dict(data).to_dict()
        response = self._core.request(
            {
                "command": "control-engine-operator-replace",
                "operator": sanitized,
            }
        )
        if response.get("ok") is not True:
            return self._core_rejection(response)
        return ApiResponse(200, response)

    def _automation_tuning_validation(self) -> ApiResponse:
        raw = json.loads(self._tuning_validation_path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("Tuning validation profile must be a JSON object")
        groups = raw.get("groups")
        if not isinstance(groups, dict) or not groups:
            raise ValueError("Tuning validation profile has no groups")

        result_groups: list[dict[str, Any]] = []
        completed = 0
        for group_id, group in groups.items():
            if not isinstance(group_id, str) or not isinstance(group, dict):
                raise ValueError("Invalid tuning validation group")
            current = group.get("current_level")
            required = group.get("required_level")
            if current not in _TUNING_LEVEL_RANK or required not in _TUNING_LEVEL_RANK:
                raise ValueError(f"Unsupported tuning validation level for {group_id}")
            satisfied = _TUNING_LEVEL_RANK[current] >= _TUNING_LEVEL_RANK[required]
            if satisfied:
                completed += 1
            result_groups.append(
                {
                    "id": group_id,
                    "current_level": current,
                    "required_level": required,
                    "satisfied": satisfied,
                    "evidence": group.get("evidence"),
                    "next_evidence": group.get("next_evidence"),
                    "notes": group.get("notes"),
                }
            )

        return ApiResponse(
            200,
            {
                "ok": True,
                "tuning_validation": {
                    "schema": raw.get("schema"),
                    "profile_id": raw.get("profile_id"),
                    "default_runtime_binding": raw.get("default_runtime_binding") is True,
                    "completed": completed,
                    "total": len(result_groups),
                    "groups": result_groups,
                },
            },
        )
