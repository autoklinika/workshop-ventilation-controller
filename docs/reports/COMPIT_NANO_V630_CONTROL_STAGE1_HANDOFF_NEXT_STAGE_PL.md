# COMPIT NANO COLOR 2 v6.30 — handoff do implementacji adaptera AERO

Data: 2026-08-03

## Cel kolejnego etapu

Zaimplementować produkcyjny adapter rekuperatora COMPIT NANO COLOR 2 v6.30 / AERO 4A2 w `ventilation-core`, bez przenoszenia logiki sterowania do GUI i bez bezpośredniego sterowania elementami wykonawczymi centrali.

Raport bazowy:

- `docs/reports/COMPIT_NANO_V630_CONTROL_VALIDATION_PL.md`
- `docs/COMPIT_AERO4A2_INTEGRATION_PL.md`
- `docs/DECISIONS_PL.md`

## Potwierdzony kontrakt urządzenia

```text
Modbus RTU
9600 bit/s
8N1
slave 44
FC03 — odczyt Holding Registers
FC06 — zapis pojedynczego Holding Register
```

Potwierdzona telemetria:

| Adres PDU | Pole domenowe | Kodowanie |
|---:|---|---|
| 2016 | humidity_percent | raw / 10 |
| 2021 | supply_temperature_c | signed raw / 10 |
| 2022 | extract_temperature_c | signed raw / 10 |
| 2023 | intake_temperature_c | signed raw / 10 |
| 2033 | fan_1_power_percent | raw |
| 2034 | fan_2_power_percent | raw |

Potwierdzone sterowanie:

| Adres PDU | Operacja | Dozwolony zakres etapu |
|---:|---|---|
| 1080 | ustawienie biegu | 0..3 |
| 1081 | wietrzenie | 0/1 |

Nie rozróżniać jeszcze `fan_1` i `fan_2` jako nawiew/wywiew bez osobnego testu.

## Krytyczne zachowanie AERO

AERO może wykonać polecenie fizycznie dopiero po około 30 sekundach.

Parametry implementacyjne:

```text
execution_timeout = 45 s
telemetry_poll_interval = 2 s
```

Natychmiastowe echo FC06 oraz readback FC03 potwierdzają przyjęcie polecenia przez NANO, ale nie potwierdzają fizycznego wykonania przez AERO.

## Wymagana architektura

Adapter ma znajdować się za interfejsem funkcjonalnym rekuperatora. Domena nie może znać numerów rejestrów Modbus.

Zalecane elementy:

- `IRecuperator` lub równoważny port domenowy,
- `CompitNanoV630Adapter`,
- osobny worker / executor RS-485,
- atrapowy `FakeRecuperator`,
- model telemetrii niezależny od producenta,
- model operacji asynchronicznej,
- log audytowy.

Jeden komponent musi być jedynym właścicielem portu RS-485. GUI i inne klienty nie mogą otwierać portu ani wykonywać zapisu bezpośrednio.

## Minimalna maszyna stanów komendy

```text
IDLE
→ REQUESTED
→ ACCEPTED_BY_NANO
→ WAITING_FOR_AERO
→ PHYSICALLY_CONFIRMED
→ IDLE
```

Ścieżki błędów:

```text
REQUESTED → TRANSPORT_ERROR
ACCEPTED_BY_NANO → READBACK_MISMATCH
WAITING_FOR_AERO → EXECUTION_TIMEOUT
ANY_STATE → COMMUNICATION_LOST
```

Przywrócenie poprzedniej wartości jest osobną komendą i przechodzi przez tę samą maszynę stanów.

## Semantyka potwierdzenia fizycznego

Pierwsza implementacja może wykorzystywać zmianę `fan_1_power_percent` lub `fan_2_power_percent` jako dowód reakcji AERO.

Nie zakładać jednak, że każda poprawna komenda musi zmienić oba procenty. Przykładowo polecenie może już odpowiadać aktualnemu stanowi, a zabezpieczenie AERO może ograniczyć wykonanie.

Adapter powinien wspierać strategię potwierdzenia zależną od operacji:

- zmiana biegu — oczekiwana stabilna zmiana mocy wentylatorów lub potwierdzony stan docelowy,
- wietrzenie ON — zmiana telemetrii zgodna z trybem wietrzenia,
- wietrzenie OFF — powrót do stanu wynikającego z bieżącego trybu,
- brak jednoznacznej zmiany — timeout lub wynik `ACCEPTED_NOT_PHYSICALLY_CONFIRMED`, zależnie od późniejszej decyzji domenowej.

## Kolejkowanie i konflikty

- tylko jedna aktywna operacja sterująca dla AERO,
- identyczna wartość docelowa jest idempotentna,
- podczas `WAITING_FOR_AERO` nie wysyłać przeciwnego polecenia,
- nowe żądanie może zostać odrzucone, zastąpione lub zakolejkowane zgodnie z polityką warstwy aplikacyjnej,
- priorytety alarm/automatyka/ręczne wymuszenie rozstrzyga domena, nie adapter Modbus.

## Zachowanie przy błędach

### Brak odpowiedzi Modbus

- oznaczyć urządzenie jako offline,
- nie zakładać, że ostatnie polecenie zostało wykonane,
- nie spamować magistrali zapisami,
- zastosować kontrolowany retry z backoff,
- po odzyskaniu najpierw odczytać stan, a dopiero potem rozstrzygnąć dalsze działanie.

### Timeout wykonawczy

- komunikacja z NANO może nadal działać,
- nie klasyfikować automatycznie jako awarii RS-485,
- zapisać osobno `execution_timeout`,
- nie wysyłać automatycznie serii powtórzeń bez polityki domenowej,
- pozostawić AERO odpowiedzialne za własne zabezpieczenia.

### Restart CM5

Po restarcie:

- otworzyć port w jednym workerze,
- odczytać sterowanie i telemetrię,
- nie przywracać ślepo wartości zapisanej przed restartem,
- odbudować stan domenowy z rzeczywistego stanu NANO/AERO,
- pozostawić lokalny panel i AERO w pełni funkcjonalne.

## Log audytowy

Każda operacja ma zapisać co najmniej:

- identyfikator operacji,
- czas żądania,
- źródło: automatyka / użytkownik / serwis,
- powód,
- adres logiczny operacji, bez eksponowania rejestru w zwykłym API,
- wartość przed,
- wartość docelową,
- wynik FC06,
- wynik readback,
- czas oczekiwania na AERO,
- telemetrię przed i po,
- stan końcowy,
- informację o przywróceniu poprzedniego stanu.

## Minimalne testy bez sprzętu

- kodowanie i dekodowanie signed temperature,
- skalowanie wilgotności,
- walidacja zakresu biegu 0..3,
- walidacja wietrzenia 0/1,
- odrzucenie zapisu do nieautoryzowanego adresu,
- idempotentne polecenie,
- poprawny przebieg maszyny stanów,
- timeout po 45 s,
- brak konfliktowej komendy podczas oczekiwania,
- odzyskanie po utracie komunikacji,
- restart procesu bez automatycznego zapisu,
- fake adapter z symulowaną zwłoką 30 s.

## Minimalne testy fizyczne na CM5

- odczyt wszystkich potwierdzonych pól,
- zmiana biegu 1 → 2 → powrót,
- wietrzenie ON → OFF,
- potwierdzenie reakcji po opóźnieniu,
- timeout bez fałszywego błędu transportu,
- odłączenie RS-485 podczas oczekiwania,
- odzyskanie po ponownym podłączeniu,
- restart `ventilation-core`,
- restart CM5,
- działanie lokalnego panelu przy wyłączonym CM5,
- dłuższy test stabilności,
- weryfikacja współpracy z iNext.

## Ograniczenia obowiązujące w implementacji

- nie reverse-engineerować C14,
- nie podłączać CM5 jako drugiego mastera do C14,
- nie używać EEPROM do automatyki,
- nie zapisywać adresów o niepotwierdzonym znaczeniu,
- nie blokować głównej pętli rdzenia przez 45 s,
- nie utożsamiać readbacku z wykonaniem fizycznym,
- nie uzależniać działania AERO od dostępności GUI, MQTT ani AI,
- nie wykonywać merge ani oznaczenia kolejnego PR jako Ready bez decyzji użytkownika.

## Kryterium zakończenia następnego etapu

Etap adaptera można uznać za zakończony dopiero po:

- pełnych testach jednostkowych,
- poprawnej walidacji CI,
- fizycznym teście na CM5,
- potwierdzeniu maszyny stanów z realną bezwładnością AERO,
- potwierdzeniu zachowania po utracie i odzyskaniu komunikacji,
- potwierdzeniu niezależności lokalnego panelu,
- sporządzeniu raportu końcowego i handoffu.
