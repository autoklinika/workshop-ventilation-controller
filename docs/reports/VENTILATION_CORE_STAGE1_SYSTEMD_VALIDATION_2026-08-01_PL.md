# ventilation-core Stage 1 — walidacja usługi systemd na CM5

Data: 2026-08-01

Gałąź: `agent/cm5-hardware-bringup-stage1`

## Cel

Potwierdzić, że `ventilation-core` działa jako trwała usługa systemowa na docelowym Raspberry Pi Compute Module 5.

## Instalacja

Jednostka `ventilation-core.service` została zainstalowana w:

```text
/etc/systemd/system/ventilation-core.service
```

Następnie wykonano:

```text
systemctl daemon-reload
systemctl enable --now ventilation-core.service
```

Systemd utworzył powiązanie w `multi-user.target.wants`, co potwierdza włączenie automatycznego startu usługi.

## Wynik `systemctl status`

Potwierdzono:

- `Loaded: loaded`,
- `enabled`,
- `Active: active (running)`,
- proces główny uruchomiony przez `/usr/bin/python3 -m ventilation_core.main`,
- aktywny osobny proces sprzętowy `multiprocessing.spawn`,
- lokalny socket: `/run/workshop-ventilation/ventilation-core.sock`,
- brak błędów w logu startowym.

Log usługi potwierdził:

```text
ventilation-core listening on /run/workshop-ventilation/ventilation-core.sock
```

## Stan rdzenia

Komenda `status` zwróciła:

- `ok: true`,
- `mode: STOP`,
- `supply_voltage: 0.0`,
- `extract_voltage: 0.0`,
- `hardware_ready: true`.

## Wniosek

`ventilation-core` działa poprawnie jako warstwowa usługa systemowa:

- uruchamia się niezależnie od terminala i GUI,
- startuje automatycznie wraz z systemem,
- tworzy kontrolowany socket w `/run`,
- uruchamia odseparowany proces sprzętowy,
- przejmuje DFR0971,
- rozpoczyna pracę w bezpiecznym stanie `STOP / 0 V / 0 V`,
- raportuje gotowość sprzętu.

## Następny test

Wykonać kontrolowany `systemctl restart ventilation-core.service` i potwierdzić:

- brak niekontrolowanego uruchomienia wentylatora,
- ponowny stan `STOP`,
- `hardware_ready: true`,
- poprawny nowy PID procesu głównego i procesu sprzętowego.
