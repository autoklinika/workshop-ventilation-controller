# Integracja rekuperatora Prodmax / COMPIT AERO 4A2

## 1. Zidentyfikowany sprzęt

- centrala: Prodmax PRO MINI 300 H/V CLASSIC + WiFi,
- oznaczenie: PRO MINI 300HV-C/WIFI,
- sterownik centrali: COMPIT AERO 4A2,
- panel pokojowy: COMPIT NANO COLOR 2,
- firmware panelu: 6.30,
- moduł sieciowy: COMPIT iNext / C14.

## 2. Architektura integracji

Nie odtwarzamy protokołu C14. CM5 komunikuje się z panelem NANO COLOR 2 przez jego interfejs Modbus RTU, a NANO nadal przekazuje żądania do AERO przez C14.

```text
CM5 / ventilation-core
        |
   Modbus RTU
        |
 NANO COLOR 2 v6.30
        |
       C14
        |
    AERO 4A2
        |
   rekuperator
```

AERO pozostaje sterownikiem nadrzędnym centrali i zachowuje odpowiedzialność za zabezpieczenia, rozmrażanie, bypass, nagrzewnice, alarmy oraz właściwe sterowanie wentylatorami.

## 3. Potwierdzony transport Modbus

Stanowisko testowe:

```text
COM10
9600 bit/s
8N1
slave 44
FC03 — odczyt
FC06 — zapis pojedynczego rejestru
CRC — poprawne
```

Interfejs: izolowany KAmod USB RS485 ISO.

## 4. Potwierdzone odczyty dla NANO COLOR 2 v6.30

Poniższe przypisania zostały ręcznie porównane z panelem:

| Adres PDU | Znaczenie | Format |
|---:|---|---|
| 2016 | wilgotność | 0,1 % |
| 2021 | temperatura nawiewu | 0,1 °C, signed 16-bit |
| 2022 | temperatura wywiewu | 0,1 °C, signed 16-bit |
| 2023 | temperatura czerpni | 0,1 °C, signed 16-bit |
| 2033 | moc wentylatora 1 | % |
| 2034 | moc wentylatora 2 | % |

Nie ustalono jeszcze, który z adresów 2033/2034 odpowiada nawiewowi, a który wywiewowi. W kodzie pozostają jako `fan_1` i `fan_2`.

Nie używamy starszej mapy parametrów jako źródła prawdy dla firmware 6.30.

## 5. Potwierdzone sterowanie

Walidacja fizyczna potwierdziła:

| Adres PDU | Funkcja | Dopuszczone wartości |
|---:|---|---|
| 1080 | wybór biegu / trybu | 0–3 w obecnym etapie |
| 1081 | wietrzenie | 0 = OFF, 1 = ON |

Obie funkcje działają przez FC06. Narzędzie testowe odczytuje poprzednią wartość, zapisuje nową, sprawdza echo FC06, wykonuje readback FC03 oraz domyślnie przywraca poprzedni stan.

## 6. Krytyczna bezwładność wykonawcza AERO

Test stanowiskowy wykazał, że AERO 4A2 może reagować fizycznie na zmianę nawet po około 30 sekundach.

Należy rozdzielać dwa różne potwierdzenia:

1. **potwierdzenie protokołu** — NANO odpowiada na FC06 i readback pokazuje nową wartość,
2. **potwierdzenie wykonania** — moce wentylatorów lub inna telemetria potwierdzają rzeczywistą reakcję AERO.

Echo FC06 ani natychmiastowy readback nie są dowodem wykonania polecenia przez centralę.

Obowiązujące założenia implementacyjne:

- domyślny timeout wykonawczy: 45 s,
- odpytywanie telemetrii podczas oczekiwania: co 2 s,
- brak ponownego lub przeciwnego polecenia, dopóki poprzednie jest w stanie `PENDING`,
- po zmianie sterowania stan domenowy przechodzi kolejno przez:
  - `REQUESTED`,
  - `ACCEPTED_BY_NANO`,
  - `WAITING_FOR_AERO`,
  - `PHYSICALLY_CONFIRMED` albo `EXECUTION_TIMEOUT`,
- po przywróceniu poprzedniego stanu również obowiązuje osobne oczekiwanie do 45 s,
- nie traktujemy opóźnienia 10–30 s jako awarii komunikacji.

## 7. Zasady bezpieczeństwa

- dynamiczne sterowanie korzysta wyłącznie z rejestrów RAM,
- nie wykonujemy cyklicznych zapisów do EEPROM,
- CM5 nie steruje bezpośrednio elementami wykonawczymi rekuperatora,
- awaria CM5 nie może blokować lokalnego panelu ani działania AERO,
- przed każdym zapisem odczytujemy stan bieżący,
- zapis musi być idempotentny: nie wysyłamy polecenia, gdy wartość docelowa jest już ustawiona,
- każde polecenie zapisujemy w historii wraz z czasem, stanem przed, wynikiem protokołu, czasem reakcji fizycznej i stanem końcowym.

## 8. Narzędzia testowe

- `tools/compit_nano_v630_labeled_read.py` — odczyt telemetrii,
- `tools/compit_nano_v630_discovery.py` — surowe snapshoty i porównania,
- `tools/compit_nano_v630_control_test.py` — kontrolowane testy FC06 z osobnym potwierdzeniem protokołu i wykonania.

## 9. Status

Potwierdzone fizycznie:

- odczyt Modbus RTU,
- zmiana biegu przez ADR 1080,
- włączenie/wyłączenie wietrzenia przez ADR 1081,
- automatyczne przywracanie poprzedniej wartości,
- długa bezwładność AERO, sięgająca około 30 s.

Następny etap to implementacja adaptera rekuperatora w `ventilation-core` z asynchroniczną maszyną stanów i timeoutem wykonawczym, bez blokowania całego rdzenia.
