# COMPIT NANO COLOR 2 v6.30 — końcowy raport walidacji Modbus

Data walidacji: 2026-08-03

## 1. Status etapu

**Testy stanowiskowe komunikacji, podstawowego odczytu i sterowania rekuperatorem zostały zakończone powodzeniem.**

Interfejs COMPIT NANO COLOR 2 v6.30 został rozpoznany w zakresie potrzebnym do implementacji adaptera rekuperatora w `ventilation-core`.

Nie ma potrzeby odtwarzania własnościowego protokołu C14 ani wykonywania dalszych ręcznych eksperymentów przed rozpoczęciem implementacji adaptera.

Etap nie oznacza jeszcze końcowego odbioru całego systemu wentylacji. Testy integracyjne na CM5, testy utraty komunikacji, restartów i dłuższej pracy zostaną wykonane podczas implementacji warstwy produkcyjnej.

## 2. Zidentyfikowany sprzęt

- rekuperator: Prodmax PRO MINI 300 H/V CLASSIC + WiFi,
- oznaczenie centrali: PRO MINI 300HV-C/WIFI,
- sterownik centrali: COMPIT AERO 4A2,
- panel: COMPIT NANO COLOR 2,
- potwierdzona wersja firmware panelu: `6.30`,
- opcjonalny moduł sieciowy: COMPIT iNext / C14,
- interfejs testowy: izolowany KAmod USB RS485 ISO,
- port stanowiska Windows: `COM10`.

Docelowa architektura komunikacji:

```text
CM5 / ventilation-core
        │
   Modbus RTU
        │
 NANO COLOR 2 v6.30
        │
       C14
        │
    AERO 4A2
        │
   rekuperator
```

CM5 nie dołącza jako drugi master do magistrali C14 i nie steruje bezpośrednio elementami wykonawczymi centrali.

## 3. Potwierdzone parametry transmisji

```text
tryb: Modbus RTU
rola NANO: slave
port testowy: COM10
baudrate: 9600 bit/s
format: 8N1
adres slave: 44
odczyt: FC03 Read Holding Registers
zapis: FC06 Write Single Register
CRC: poprawne
```

Odpowiedzi Modbus są stabilne, ramki przechodzą kontrolę CRC, a adres slave i format transmisji zostały potwierdzone fizycznie.

## 4. Krytyczna uwaga o mapie firmware 6.30

Starsza publiczna mapa rejestrów nie odpowiada w pełni NANO COLOR 2 z firmware `6.30`.

Nie wolno używać dawnych opisów jako źródła prawdy tylko dlatego, że dany adres zwraca poprawną odpowiedź. Poprawna odpowiedź Modbus potwierdza istnienie adresu, ale nie potwierdza znaczenia parametru.

W dokumentacji producenta występuje również rozróżnienie:

- **REJESTR** — numer opisowy z tabeli,
- **ADRES PDU** — wartość faktycznie wysyłana w ramce Modbus.

W kodzie używamy adresów PDU. W dokumentacji serwisowej należy zawsze określać, czy numer oznacza rejestr dokumentacyjny, czy adres PDU.

## 5. Potwierdzona telemetria firmware 6.30

Poniższe przypisania zostały porównane ręcznie z panelem i są traktowane jako potwierdzone:

| Adres PDU | Znaczenie | Kodowanie |
|---:|---|---|
| `2016` | wilgotność | wartość / 10 = % RH |
| `2021` | temperatura nawiewu | signed 16-bit, wartość / 10 = °C |
| `2022` | temperatura wywiewu | signed 16-bit, wartość / 10 = °C |
| `2023` | temperatura czerpni | signed 16-bit, wartość / 10 = °C |
| `2033` | moc jednego z wentylatorów | wartość bezpośrednia w % |
| `2034` | moc drugiego wentylatora | wartość bezpośrednia w % |

Nie ustalono jeszcze, który z adresów `2033` i `2034` odpowiada nawiewowi, a który wywiewowi. Do czasu osobnej identyfikacji adapter i diagnostyka używają nazw neutralnych `fan_1_power` i `fan_2_power`.

Przykład zaobserwowany podczas zmiany biegu 2 → 3:

```text
ADR 2033: 60 -> 90
ADR 2034: 60 -> 90
```

Potwierdza to, że oba adresy reprezentują rzeczywiste moce wentylatorów w procentach.

Pozostałe adresy z zakresu stanu nie są potrzebne do pierwszej implementacji i nie otrzymują niepotwierdzonych nazw produkcyjnych.

## 6. Potwierdzone adresy sterujące

| Adres PDU | Funkcja | Wartości zwalidowane |
|---:|---|---|
| `1080` | wybór biegu / trybu | `0`, `1`, `2`, `3` |
| `1081` | wietrzenie | `0` = OFF, `1` = ON |

Oba adresy należą do obszaru RAM i zostały zwalidowane przez pojedynczy zapis `FC06`.

### ADR 1080 — zmiana biegu

Potwierdzono fizyczną zmianę pracy centrali po zapisaniu wartości biegu.

W pierwszym etapie produkcyjnym dopuszczamy wyłącznie wartości `0..3`. Tryby specjalne, harmonogram i inne wartości nie są potrzebne do podstawowej automatyki i pozostają poza zakresem.

### ADR 1081 — wietrzenie

Potwierdzono:

- zapis `1` uruchamia wietrzenie,
- zapis `0` wyłącza wietrzenie,
- lokalny panel pokazuje zmianę,
- AERO wykonuje zmianę fizycznie,
- wcześniejszy stan można przywrócić.

## 7. Wyniki testów sterowania

Zaliczone zostały następujące testy:

- odczyt `FC03`,
- zapis `FC06`,
- poprawne echo odpowiedzi `FC06`,
- readback `FC03` po zapisie,
- zmiana biegu przez `ADR 1080`,
- włączenie i wyłączenie wietrzenia przez `ADR 1081`,
- obserwacja reakcji panelu,
- obserwacja fizycznej reakcji wentylatorów,
- automatyczne przywrócenie poprzedniej wartości,
- kontrola mocy wentylatorów przez `ADR 2033` i `ADR 2034`.

Komunikację i podstawowe sterowanie rekuperatorem uznaje się za zwalidowane stanowiskowo.

## 8. Krytyczna bezwładność wykonawcza AERO

Test stanowiskowy wykazał, że AERO 4A2 może reagować fizycznie na prawidłowo przyjęte polecenie dopiero po około `30 s`.

NANO może odpowiedzieć na zapis natychmiast, podczas gdy AERO nadal wykonuje poprzedni stan.

Należy bezwzględnie rozdzielać:

1. **potwierdzenie transportu** — poprawna ramka i CRC,
2. **potwierdzenie przyjęcia przez NANO** — echo `FC06`,
3. **potwierdzenie wartości zadanej** — readback `FC03`,
4. **potwierdzenie wykonania przez AERO** — zmiana mocy wentylatorów lub innej właściwej telemetrii.

Echo `FC06` ani natychmiastowy readback nie są dowodem fizycznego wykonania polecenia przez centralę.

Obowiązujące wartości projektowe:

```text
timeout wykonawczy: 45 s
interwał odpytywania telemetrii: 2 s
zaobserwowane opóźnienie fizyczne: do około 30 s
```

Opóźnienie 10–30 s nie jest klasyfikowane jako błąd RS-485 ani brak odpowiedzi Modbus.

## 9. Wymagana maszyna stanów adaptera

Docelowy adapter nie może blokować całego `ventilation-core` podczas oczekiwania na AERO.

Minimalne stany operacji:

```text
REQUESTED
→ ACCEPTED_BY_NANO
→ WAITING_FOR_AERO
→ PHYSICALLY_CONFIRMED
```

Ścieżka błędu wykonawczego:

```text
WAITING_FOR_AERO
→ EXECUTION_TIMEOUT
```

Wymagania:

- podczas `WAITING_FOR_AERO` nie wysyłamy konfliktowej komendy do tego samego urządzenia,
- identyczne polecenie ma być idempotentne,
- szybki readback nie kończy operacji jako sukces fizyczny,
- przywrócenie poprzedniego stanu jest osobną operacją i również wymaga do 45 s,
- rdzeń musi pozostawać responsywny dla innych urządzeń i klientów,
- wynik operacji zapisujemy w historii.

## 10. Zasady bezpieczeństwa

- AERO 4A2 pozostaje nadrzędnym sterownikiem centrali,
- zabezpieczenia, rozmrażanie, bypass, nagrzewnice, alarmy i logika wentylatorów pozostają po stronie AERO,
- CM5 wysyła wyłącznie żądanie trybu lub wietrzenia,
- dynamiczne sterowanie korzysta z rejestrów RAM,
- nie wykonujemy cyklicznych zapisów do EEPROM,
- nie zapisujemy do adresów o niepotwierdzonym znaczeniu,
- przed zapisem odczytujemy aktualną wartość,
- nie wysyłamy zapisu, gdy wartość docelowa jest już ustawiona,
- ręczne wymuszenia muszą mieć określony czas zakończenia,
- awaria lub wyłączenie CM5 nie może blokować panelu lokalnego ani normalnej pracy AERO,
- nie ingerujemy w C14 i nie dołączamy do niego drugiego mastera.

## 11. Narzędzia stanowiskowe w repo

### `tools/compit_nano_v630_discovery.py`

- surowe odczyty `FC03`,
- snapshoty zakresu rejestrów,
- porównywanie dwóch stanów,
- brak funkcji zapisu.

### `tools/compit_nano_v630_labeled_read.py`

- czytelny log wartości,
- potwierdzone opisy telemetrii,
- robocze opisy pozostałych adresów,
- brak funkcji zapisu.

### `tools/compit_nano_v630_control_test.py`

- kontrolowane zapisy wyłącznie do `ADR 1080` i `ADR 1081`,
- wymagane jawne `--execute --confirm NANO630`,
- odczyt wartości przed zmianą,
- sprawdzenie echa `FC06`,
- readback `FC03`,
- osobna obserwacja fizycznej reakcji AERO,
- timeout wykonawczy 45 s,
- polling mocy wentylatorów co 2 s,
- automatyczne przywrócenie poprzedniej wartości, o ile nie użyto `--keep`.

Narzędzia są przeznaczone do diagnostyki i walidacji, nie stanowią docelowego adaptera produkcyjnego.

## 12. Elementy świadomie pozostawione na później

Nie blokują one rozpoczęcia implementacji adaptera:

- rozróżnienie `ADR 2033` jako nawiew/wywiew względem `ADR 2034`,
- identyfikacja pozostałych rejestrów stanu firmware 6.30,
- jednoczesna zgodność trybu Modbus z modułem iNext,
- test długotrwały na docelowej magistrali RS-485,
- zachowanie po utracie i odzyskaniu komunikacji,
- restart CM5 podczas aktywnej operacji,
- priorytety pomiędzy lokalnym panelem, automatyką i ręcznym wymuszeniem,
- końcowa integracja z historią zdarzeń i API domenowym.

## 13. Następny etap

Następny etap to implementacja produkcyjnego adaptera COMPIT/AERO w `ventilation-core`:

- osobny worker lub adapter będący jedynym właścicielem portu RS-485,
- asynchroniczna maszyna stanów,
- odczyt telemetrii i kontrolowane zapisy,
- timeout wykonawczy 45 s,
- brak blokowania rdzenia,
- blokada konfliktowych poleceń,
- obsługa utraty komunikacji i odzyskania,
- log audytowy każdej operacji,
- atrapowy adapter do testów bez sprzętu,
- testy jednostkowe i integracyjne,
- końcowa walidacja na CM5.

## 14. Konkluzja

NANO COLOR 2 v6.30 zapewnia wystarczający i fizycznie zwalidowany interfejs Modbus RTU do sterowania rekuperatorem w zakresie wymaganym przez projekt.

Nie jest potrzebne reverse engineering C14.

Stan etapu:

```text
ODCZYT: ZWALIDOWANY W WYMAGANYM ZAKRESIE
ZMIANA BIEGU: ZWALIDOWANA
WIETRZENIE: ZWALIDOWANE
PRZYWRACANIE STANU: ZWALIDOWANE
BEZWŁADNOŚĆ AERO: ZIDENTYFIKOWANA I UWZGLĘDNIONA
GOTOWOŚĆ DO IMPLEMENTACJI ADAPTERA: TAK
```
