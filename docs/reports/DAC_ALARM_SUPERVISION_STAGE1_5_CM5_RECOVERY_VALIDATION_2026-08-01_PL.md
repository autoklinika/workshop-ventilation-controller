# Stage 1.5 — walidacja odzyskania komunikacji z DAC na CM5

Data: 2026-08-01

Gałąź: `agent/dac-alarm-supervision-stage1-5`

## Warunki testu

- przed testem rdzeń znajdował się w stanie `FAULT`,
- DFR0971 był odłączony od przewodu Gravity/I²C,
- aktywny był alarm `DAC_COMMUNICATION_LOST`,
- fan pozostawał zatrzymany,
- następnie ponownie podłączono DFR0971.

## Wynik logiczny po odzyskaniu

Odczyt `status` zwrócił:

```json
{
  "ok": true,
  "state": {
    "mode": "STOP",
    "setpoints": {
      "supply_voltage": 0.0,
      "extract_voltage": 0.0
    },
    "hardware_ready": true,
    "output_state_known": true,
    "consecutive_hardware_failures": 0,
    "active_alarms": []
  }
}
```

Potwierdzono więc:

- automatyczne wykrycie powrotu DAC,
- ponowną konfigurację i wyzerowanie obu kanałów,
- przejście do `STOP`,
- wyczyszczenie alarmu,
- wyzerowanie licznika kolejnych błędów,
- brak automatycznego przywrócenia wcześniejszej nastawy.

## Obserwacja fizyczna

Przy ponownym podłączeniu całego przewodu Gravity fan wykonał bardzo delikatny, krótkotrwały ruch. Nie nastąpiło trwałe uruchomienie ani wejście na obroty.

Najbardziej prawdopodobną przyczyną jest krótki stan przejściowy przy ponownym zasileniu DFR0971, zanim oprogramowanie ponownie skonfiguruje zakres wyjściowy i zapisze 0 V na obu kanałach.

Obserwację należy traktować jako znany transient przy ponownym zasileniu DAC, a nie jako przywrócenie poprzedniej komendy przez logikę `ventilation-core`.

## Ocena

Walidacja odzyskania komunikacji zakończona wynikiem funkcjonalnym PASS z odnotowanym drobnym transientem mechanicznym fana przy ponownym zasileniu DFR0971.

Przed ostatecznym zamknięciem Stage 1.5 wskazane jest jeszcze jedno powtórzenie sekwencji odłączenie–podłączenie w stanie 0 V, aby potwierdzić powtarzalność i skalę transientu.
