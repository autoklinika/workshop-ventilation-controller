# CM5 Zigbee Stage 11 — walidacja nazw i ról systemowych

Data walidacji: 2026-08-18
Gałąź: `agent/zigbee-management-alerts-stage1`
Tryb stanowiska: sam CM5 + infrastruktura Zigbee; część wykonawcza celowo offline

## Wynik

Stage 11 zakończony wynikiem PASS.

Potwierdzono:

- pełny zestaw testów repozytorium: `263 tests`, `OK`,
- trwały rejestr ról w `/var/lib/workshop-ventilation/zigbee-roles.json`,
- poprawne mapowanie `supply -> temp_nawiew` oraz `extract -> temp_wywiew`,
- poprawną telemetrię i availability obu czujników,
- bezpieczną ścieżkę rename przez Web API -> core -> Zigbee2MQTT,
- bezpieczną ścieżkę przypisania roli,
- ponowne wymuszenie `retain=true` przy przypisaniu roli,
- odtworzenie rejestru ról oraz retained telemetry po restarcie core,
- obecność kontrolek rename/role w GUI,
- zachowanie architektury GUI -> Web API -> core bez bezpośredniego MQTT.

## Live role mapping

```text
supply:  temp_nawiew  0xa4c13810e66fffff  availability=True  temp=26.2
extract: temp_wywiew  0xa4c13810bdedffff  availability=True  temp=26.6
```

## Persistence

Po restarcie `ventilation-core`:

```text
role registry reload: PASS
retained telemetry after core restart: PASS
```

## Zakres bezpiecznej walidacji

Walidator nie:

- zmieniał realnych nazw urządzeń,
- zwalniał ról,
- otwierał parowania,
- usuwał urządzeń.

Wykonano tylko bezpieczny rename do tej samej nazwy oraz ponowne przypisanie tego samego urządzenia do tej samej roli.

## Następny krok

Praktyczny test operacyjny na jednym urządzeniu:

1. ustawienie `BEZ ROLI`,
2. ponowne przypisanie roli,
3. realna zmiana nazwy i przywrócenie,
4. restart core i potwierdzenie trwałości,
5. na końcu kontrolowane `usuń -> sparuj ponownie -> przypisz rolę`.

`main` pozostaje nietknięty.
