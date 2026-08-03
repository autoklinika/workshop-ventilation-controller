# COMPIT NANO COLOR 2 — pierwsza walidacja Modbus RTU

## Cel

Pierwsze podłączenie panelu COMPIT NANO COLOR 2 do komputera z Windows przez izolowany konwerter KAmod USB RS485 ISO.

Walidacja jest wyłącznie odczytowa. Nie analizujemy protokołu C14 i nie wysyłamy żadnych funkcji zapisu.

## Znane parametry

- urządzenie: Modbus RTU Slave,
- domyślny adres: 44,
- prędkość: 9600 bit/s,
- format: 8N1,
- funkcja: 0x03 Read Holding Registers,
- maksymalny deklarowany czas odpowiedzi: 300 ms.

## Warunki przed podłączeniem

1. Odczytać wersję firmware panelu NANO COLOR 2.
2. Potwierdzić w menu dostępność trybu Modbus / BMS.
3. Potwierdzić w dokumentacji lub na oznaczeniach panelu, która para A1/B1 albo A2/B2 jest interfejsem Modbus/BMS.
4. Nie zgadywać pary zacisków i nie podłączać konwertera do nieustalonej magistrali C14.
5. Uwzględnić, że tryb Modbus/BMS może wykluczać jednoczesną pracę modułu iNext.

## Pierwsze rejestry

Skrypt odczytuje domyślnie tylko:

- 2016 — temperatura pomieszczenia,
- 2021 — temperatura nawiewu,
- 2036 — aktualny bieg wentylacji,
- 2039 — rozpoznany moduł wentylacji,
- 2040 — alarm AERO.

## Narzędzie

```text
tools/compit_nano_color2_read.py
```

Skrypt:

- używa wyłącznie funkcji 0x03,
- nie zawiera funkcji zapisu,
- sprawdza CRC Modbus,
- pokazuje wartości surowe i zdekodowane,
- opcjonalnie pokazuje pełne ramki TX/RX,
- zapisuje wynik do CSV.

## Uruchomienie Windows

```powershell
cd C:\PROJEKTY\workshop-ventilation-controller
py -m pip install pyserial
py tools\compit_nano_color2_read.py --port COM10 --show-frames
```

Pełny, nadal wyłącznie odczytowy zestaw znanych rejestrów stanu:

```powershell
py tools\compit_nano_color2_read.py --port COM10 --full --show-frames
```

## Kryterium zaliczenia

- odpowiedź z adresu 44,
- funkcja odpowiedzi 0x03,
- poprawne CRC,
- wartości temperatur zgodne z panelem z dokładnością wynikającą z rozdzielczości 0,1 °C,
- bieg 2036 zgodny ze stanem panelu,
- rejestr 2040 zgodny ze stanem alarmowym,
- brak zapisów i brak wpływu komputera na normalne sterowanie rekuperatora.

## Kolejny krok

Dopiero po pozytywnym odczycie i porównaniu wartości z panelem można przygotować osobny, kontrolowany test pojedynczego zapisu RAM 1081 = 1, a następnie 1081 = 0. Nie wykonuje się go w ramach pierwszego podłączenia.
