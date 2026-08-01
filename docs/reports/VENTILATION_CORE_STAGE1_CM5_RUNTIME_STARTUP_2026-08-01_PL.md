# ventilation-core Stage 1 — uruchomienie runtime na CM5

Data: 2026-08-01

Gałąź: `agent/cm5-hardware-bringup-stage1`

## Zakres

Zweryfikowano ręczne uruchomienie warstwowego `ventilation-core` na docelowym Raspberry Pi Compute Module 5 z rzeczywistym DFRobot DFR0971 podłączonym przez I²C.

## Wykonane kroki

1. Pobrano aktualny HEAD gałęzi.
2. Wymuszono `0 V` na obu kanałach przy użyciu narzędzia serwisowego.
3. Uruchomiono `ventilation-core` ręcznie z Unix socketem `/tmp/ventilation-core.sock`.
4. Z osobnego terminala wykonano komendę `status` przez klienta `ventilationctl`.

## Potwierdzone zachowanie

- rdzeń uruchomił się bez błędów,
- proces sprzętowy poprawnie wystartował,
- DFR0971 został przejęty przez warstwę infrastruktury,
- oba kanały pozostały w stanie `0 V`,
- Unix socket został utworzony i przyjmował komendy,
- warstwa aplikacyjna zwróciła stan `STOP`,
- zadane napięcia wynosiły `0.0 V / 0.0 V`,
- `hardware_ready` miało wartość `true`.

Potwierdzona odpowiedź:

```json
{
  "ok": true,
  "state": {
    "mode": "STOP",
    "setpoints": {
      "supply_voltage": 0.0,
      "extract_voltage": 0.0
    },
    "hardware_ready": true
  }
}
```

## Wniosek

Pełny tor warstwowy działa na docelowym CM5:

```text
ventilationctl
    ↓
Unix socket
    ↓
runtime/server
    ↓
application/service
    ↓
domain/policy
    ↓
process-isolated actuator
    ↓
hardware worker
    ↓
DFR0971 / I²C
```

Rdzeń jest gotowy do pierwszej rzeczywistej komendy wykonawczej przez API aplikacyjne, przy zachowaniu drugiego kanału na `0 V`.
