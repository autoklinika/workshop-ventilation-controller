# Checkpoint pełnego zakresu sterowania wentylatorem EC — kanał 0

Data: 2026-08-01

Gałąź: `agent/cm5-hardware-bringup-stage1`

## Konfiguracja

- sterownik: Raspberry Pi Compute Module 5,
- DAC: DFRobot DFR0971 / GP8403,
- kanał sterujący: `VOUT0`,
- jeden wentylator EC podłączony do wejścia 0–10 V,
- drugi kanał DAC pozostawiony na 0 V,
- praktyczny próg startu przyjęty na `1,0 V`.

## Wyniki

| Napięcie sterujące | Zachowanie wentylatora | Wynik |
|---:|---|---|
| 0 V | wentylator zatrzymany | PASS |
| 1 V | uruchamia się | PASS |
| 2 V | pewny start, stabilna praca, zatrzymanie po powrocie do 0 V | PASS |
| 5 V | pewny start, wyraźnie większa prędkość niż przy 2 V, stabilna praca, zatrzymanie po powrocie do 0 V | PASS |
| 8 V | zachowanie zgodne z założeniami, stabilna praca i dalszy wzrost wydajności | PASS |
| 10 V | zachowanie zgodne z założeniami, pełne sterowanie i stabilna praca | PASS |

## Wnioski

- tor `CM5 → I²C → DFR0971 → 0–10 V → wentylator EC` działa poprawnie,
- wentylator reaguje prawidłowo w pełnym praktycznym zakresie `1–10 V`,
- `0 V` skutecznie zatrzymuje wentylator,
- `1,0 V` pozostaje obowiązującym minimalnym napięciem uruchomienia,
- kanał 0 DFR0971 jest gotowy do integracji z `ventilation-core`,
- dalsza kalibracja progu startu nie jest wymagana dla tego lokalnego wdrożenia.

## Następny etap

Przygotować integrację sterowania DAC z `ventilation-core`, z zachowaniem polityki:

- `0 V` = stop,
- komenda pracy zawsze co najmniej `1,0 V`,
- jawne przejęcie sterowania po starcie procesu,
- brak użycia funkcji nieulotnego zapisu `store`,
- kontrolowany powrót do bezpiecznego stanu przy zatrzymaniu usługi.
