# COMPIT NANO COLOR 2 v6.30 — walidacja sterowania Modbus

Data walidacji: 2026-08-03

## Stanowisko

- COMPIT NANO COLOR 2, firmware 6.30,
- COMPIT AERO 4A2,
- izolowany KAmod USB RS485 ISO,
- COM10,
- 9600 bit/s,
- 8N1,
- slave 44.

## Wynik

Potwierdzono:

- FC03 działa poprawnie,
- FC06 działa poprawnie,
- ADR 1080 zmienia bieg centrali,
- ADR 1081 steruje wietrzeniem,
- echo FC06 i readback FC03 są poprawne,
- centrala wykonuje polecenia fizycznie,
- automatyczne przywrócenie poprzedniej wartości działa.

## Obserwacja krytyczna

Fizyczna reakcja AERO 4A2 może nastąpić dopiero po około 30 sekundach od poprawnego przyjęcia zapisu przez NANO.

Nie wolno utożsamiać:

- odpowiedzi Modbus,
- zmiany rejestru sterującego,
- fizycznego wykonania polecenia.

Dla implementacji przyjęto domyślny timeout wykonawczy 45 s i osobne monitorowanie mocy wentylatorów pod ADR 2033 i 2034.

## Konsekwencje architektoniczne

Adapter AERO musi być asynchroniczny. Polecenie pozostaje `PENDING`, dopóki telemetria nie potwierdzi reakcji albo nie upłynie timeout. W tym czasie rdzeń nie wysyła konfliktowego polecenia do tego samego urządzenia.

Opóźnienie wykonawcze nie jest błędem RS-485 ani brakiem odpowiedzi Modbus.
