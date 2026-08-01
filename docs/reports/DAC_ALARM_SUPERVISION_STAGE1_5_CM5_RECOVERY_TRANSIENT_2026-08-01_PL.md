# Stage 1.5 — odzyskanie komunikacji z DAC i zaobserwowany impuls fana

Data: 2026-08-01

Gałąź: `agent/dac-alarm-supervision-stage1-5`

## Przebieg

Po wcześniejszym odłączeniu DFR0971 rdzeń poprawnie przeszedł do trybu `FAULT` i zgłosił alarm `DAC_COMMUNICATION_LOST`. Następnie przewód Gravity / I2C został ponownie podłączony.

## Obserwacja fizyczna

Podczas odzyskiwania komunikacji fan wykonał delikatny, krótkotrwały ruch.

Nie należy klasyfikować tego wyniku jako całkowicie bezimpulsowego odzyskania. Funkcjonalne odzyskanie komunikacji może być poprawne, ale tor 0–10 V wykazuje krótki stan przejściowy podczas ponownego zasilenia lub inicjalizacji DFR0971.

## Możliwe źródła stanu przejściowego

- ponowne zasilenie DFR0971 przez przewód Gravity,
- stan wyjścia GP8403 przed pierwszym skutecznym zapisem 0 V,
- sekwencja ponownej konfiguracji zakresu 10 V i zerowania kanałów,
- przejściowy poziom analogowy podczas stabilizacji zasilania DAC.

Na podstawie samej obserwacji mechanicznej nie można jeszcze określić amplitudy ani czasu impulsu.

## Ocena

Dla fana wentylacyjnego pojedynczy delikatny ruch prawdopodobnie nie stanowi zagrożenia mechanicznego, ale jest istotny dla rzetelności funkcji fail-safe. Kryterium „fan nie wykonuje żadnego ruchu” nie zostało spełnione.

Stage 1.5 może zostać zamknięty dopiero po:

1. potwierdzeniu końcowego statusu `STOP`, `hardware_ready: true`, `output_state_known: true`, `active_alarms: []`,
2. powtórzeniu odzyskania i sprawdzeniu, czy ruch jest powtarzalny,
3. zapisaniu zjawiska jako świadomego ograniczenia albo usunięciu go programowo lub sprzętowo.

## Ważne rozróżnienie

Odłączenie całego przewodu Gravity powoduje prawdopodobnie zarówno utratę I2C, jak i zasilania DAC. Nie jest to identyczne z samą utratą komunikacji przy zachowanym zasilaniu. W docelowej instalacji oba scenariusze należy traktować osobno.
