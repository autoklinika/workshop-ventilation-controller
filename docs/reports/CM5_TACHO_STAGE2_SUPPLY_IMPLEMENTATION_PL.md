# CM5 TACHO Stage 2 — SUPPLY / VOUT0

Data: 2026-08-13

## Cel

Rozszerzyć zwalidowany wcześniej read-only pomiar TACHO kanału EXTRACT o drugi kanał dla wentylatora nawiewnego SUPPLY.

## Docelowe mapowanie

```text
SUPPLY control: DAC CH0 / VOUT0
SUPPLY TACHO:   GPIO17 / physical pin 11

EXTRACT control: DAC CH1 / VOUT1
EXTRACT TACHO:   GPIO27 / physical pin 13
```

Przewód CM5 <-> BOX wykonawczy:

```text
DB9 pin 8 -> GPIO17 -> TACHO dla VOUT0 / SUPPLY
DB9 pin 9 -> GPIO27 -> TACHO dla VOUT1 / EXTRACT
```

DB9 sterowania wentylatorami:

```text
pin 1 -> VOUT0
pin 2 -> TACHO dla VOUT0
pin 3 -> GND
pin 4 -> TACHO dla VOUT1
pin 5 -> VOUT1
```

## Tor wejściowy

Dla obu kanałów obowiązuje ten sam zwalidowany tor wejściowy:

```text
                      +3.3 V
                         |
                       10 kΩ
                         |
TACHO FAN --------------+
                         |
                        1 kΩ
                         |
                         +---------- GPIO CM5
                         |
                        1 nF
                         |
                        GND
```

Założenia pomiaru:

- wyjście TACHO open-collector,
- pull-up 10 kΩ do 3,3 V,
- rezystor szeregowy 1 kΩ,
- kondensator 1 nF do GND,
- zbocze narastające,
- 3 impulsy/obrót,
- `RPM = frequency_hz * 20`.

## Implementacja

Dotychczasowy jednokanałowy `ExtractTachoMonitor` został rozszerzony do monitora dwóch niezależnych kanałów GPIO.

Każdy kanał ma osobny worker libgpiod:

```text
SUPPLY  -> consumer ventilation-core-supply-tacho  -> GPIO17
EXTRACT -> consumer ventilation-core-extract-tacho -> GPIO27
```

Dzięki temu oba wejścia są obsługiwane niezależnie na poziomie zbierania impulsów.

Nowe argumenty runtime:

```text
--enable-supply-tacho
--supply-tacho-line GPIO17
```

Zachowane argumenty EXTRACT:

```text
--enable-extract-tacho
--extract-tacho-line GPIO27
```

Produkcjny plik `deploy/systemd/ventilation-core.service` w tej gałęzi włącza oba kanały.

## Kontrakt CoreState

Nie zmienia się struktura API. Istniejące pole:

```text
state.tacho.supply
```

przestaje być `null` po włączeniu SUPPLY i publikuje:

```text
line_name
line_offset
frequency_hz
rpm
sample_count
age_seconds
valid
```

`state.tacho.extract` pozostaje bez zmian.

Web GUI z PR #20 już obsługuje oba pola i nie wymaga dodatkowego endpointu ani obliczania RPM po stronie przeglądarki.

## Bezpieczeństwo

TACHO pozostaje wyłącznie read-only.

Brak sygnału lub awaria monitora TACHO:

- nie zmienia nastawy DAC,
- nie zatrzymuje wentylatora,
- nie ustawia trybu FAULT,
- nie tworzy alarmu DAC,
- nie jest interpretowana jako potwierdzone `0 RPM`.

`valid=false` oznacza wyłącznie brak aktualnego, poprawnego feedbacku TACHO.

## Walidacja programowa

Testy zostały rozszerzone o:

- publikację jednocześnie `supply` i `extract`,
- domyślne mapowanie GPIO17/GPIO27,
- osobne flagi enable dla obu kanałów,
- blokadę przypisania obu kanałów do tej samej linii GPIO,
- wymóg co najmniej jednego skonfigurowanego kanału,
- produkcyjną konfigurację obu kanałów w systemd.

## Walidacja sprzętowa — PENDING

Przed merge wymagane jest potwierdzenie na docelowym CM5 i drugim fizycznym wentylatorze:

1. GPIO17 jest wolne i poprawnie przejęte przez `ventilation-core-supply-tacho`.
2. STOP: brak fałszywych impulsów.
3. SUPPLY przy zadanym napięciu publikuje stabilne Hz/RPM.
4. EXTRACT na GPIO27 nadal działa równolegle.
5. Fizyczne odłączenie wyłącznie SUPPLY TACHO nie zmienia setpointu SUPPLY ani trybu core.
6. Ponowne podłączenie SUPPLY TACHO odzyskuje `valid=true` bez restartu core.
7. SENSOR BUS i AERO BUS pozostają niezależne.
8. Końcowy stan DAC po walidacji: STOP / 0.0 V / 0.0 V.

PR pozostaje Draft do zakończenia walidacji sprzętowej i jawnej decyzji użytkownika o Ready/Merge.
