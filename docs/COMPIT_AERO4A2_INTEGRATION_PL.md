# Integracja rekuperatora Prodmax / Compit AERO 4A2

## 1. Zidentyfikowany sprzęt

W pomieszczeniu lutowniczym pracuje rekuperator:

- producent centrali: Prodmax,
- model: PRO MINI 300 H/V CLASSIC + moduł WiFi,
- oznaczenie: PRO MINI 300HV-C/WIFI,
- sterownik centrali: COMPIT AERO 4A2,
- panel pokojowy: COMPIT NANO COLOR 2,
- moduł sieciowy: COMPIT iNext / C14.

Panel NANO COLOR 2 ma zaciski A1, B1, A2, B2, G oraz U. Sterownik AERO 4A2 komunikuje się z panelem przez własnościowy protokół C14.

## 2. Najważniejszy wniosek

Nie odtwarzamy protokołu C14, jeżeli posiadany NANO COLOR 2 udostępnia opublikowany przez producenta tryb Modbus RTU dla AERO 4A ver.2.

Docelowo CM5 komunikuje się z panelem przez Modbus RTU, natomiast panel nadal realizuje komunikację C14 ze sterownikiem AERO 4A2.

```text
CM5 / ventilation-core
        │
   Modbus RTU
        │
 NANO COLOR 2
        │
       C14
        │
    AERO 4A2
        │
   rekuperator
```

## 3. Parametry Modbus NANO COLOR 2

Parametry pierwszej walidacji:

- rola panelu: Modbus RTU Slave,
- domyślny adres slave: `44`,
- prędkość: `9600 bit/s`,
- format: `8N1`,
- maksymalny deklarowany czas odpowiedzi: `300 ms`,
- funkcje:
  - `0x03` — Read Holding Registers,
  - `0x06` — Write Single Register,
  - `0x10` — Write Multiple Registers.

Pierwsza walidacja używa wyłącznie `0x03`.

## 4. Krytyczne rozróżnienie: REJESTR i ADRES

Dokumentacja COMPIT/AWENTA podaje dwie oddzielne wartości:

- **REJESTR** — numer prezentowany w tabeli producenta,
- **ADRES** — zero-based adres PDU wysyłany w ramce Modbus.

Przykład:

```text
REJESTR 2017 — temperatura pomieszczenia
ADRES PDU 2016 — wartość wysyłana w zapytaniu FC03
```

W kodzie sterownika i w surowej ramce Modbus należy używać kolumny **ADRES**. W dokumentacji użytkowej należy zawsze pokazywać oba pola, aby uniknąć błędów off-by-one.

## 5. Rejestry bieżącego stanu

| Rejestr | Adres PDU | Znaczenie | Jednostka |
|---:|---:|---|---|
| 2017 | 2016 | temperatura pomieszczenia | 0,1 °C |
| 2022 | 2021 | temperatura nawiewu | 0,1 °C |
| 2023 | 2022 | temperatura czerpni / zewnętrzna | 0,1 °C |
| 2024 | 2023 | temperatura wywiewu | 0,1 °C |
| 2025 | 2024 | temperatura wyrzutni | 0,1 °C |
| 2026 | 2025 | stan presostatu | — |
| 2027 | 2026 | aktywne rozmrażanie | 0/1 |
| 2028 | 2027 | praca nagrzewnicy wtórnej | 0/1 |
| 2029 | 2028 | aktywne wietrzenie | 0/1 |
| 2030 | 2029 | praca nagrzewnicy wstępnej | 0/1 |
| 2031 | 2030 | praca chłodnicy | 0/1 |
| 2032 | 2031 | zabrudzony filtr | 0/1 |
| 2033 | 2032 | aktualna moc nagrzewnicy wstępnej | % |
| 2034 | 2033 | aktualna moc nagrzewnicy wtórnej | % |
| 2035 | 2034 | aktualna wydajność nawiewu | % |
| 2036 | 2035 | aktualna wydajność wywiewu | % |
| 2037 | 2036 | aktualny bieg wentylacji | kod |
| 2038 | 2037 | stan bypassu | kod |
| 2039 | 2038 | stan GWC | kod |
| 2040 | 2039 | aktualnie podłączony moduł wentylacji | kod |
| 2041 | 2040 | alarm AERO | kod |
| 2042 | 2041 | aktualne obroty AO3 | % |

Temperatury są wartościami signed 16-bit ze skalą `0,1 °C`.

## 6. Rejestry sterujące — numer i adres PDU

| Rejestr | Adres PDU | Funkcja |
|---:|---:|---|
| 1078 | 1077 | wentylacja: 0 = OFF, 1 = ON |
| 1079 | 1078 | GWC: 0 = OFF, 1 = AUTO |
| 1080 | 1079 | bypass: 0 = OFF, 1 = AUTO, 2 = ON |
| 1081 | 1080 | wybór biegu / trybu pracy |
| 1082 | 1081 | wietrzenie: 0 = OFF, 1 = ON |

Znaczenie rejestru 1081 / adresu 1080:

- 0 — bieg 0,
- 1 — bieg 1,
- 2 — bieg 2,
- 3 — bieg 3,
- 4 — program świąteczny,
- 5 — harmonogram.

Do dynamicznej reakcji na VOC i PM preferowany jest **rejestr 1082 / adres PDU 1081**. CM5 może czasowo uruchomić wietrzenie, obserwować stan 2029 / 2028 oraz wydajności 2035 / 2034 i 2036 / 2035, a następnie wyłączyć wietrzenie.

## 7. Konfiguracja biegów

Najważniejsze parametry konfiguracyjne:

| Rejestr | Adres PDU | Znaczenie |
|---:|---:|---|
| 1142–1145 | 1141–1144 | nawiew dla biegów 1, 2, 3 i wietrzenia |
| 1146–1149 | 1145–1148 | wywiew dla biegów 1, 2, 3 i wietrzenia |
| 1153 | 1152 | czas wietrzenia |
| 1156 | 1155 | korekta biegu od sensorów |
| 1167–1169 | 1166–1168 | parametry rozmrażania |
| 1176 | 1175 | konfiguracja bypassu |

Nie używamy tych parametrów do częstego sterowania dynamicznego.

## 8. Podział pamięci i trwałość EEPROM

Producent rozdziela obszary pamięci:

- `1–399` — EEPROM, konfiguracja trwała,
- `1001–1399` — RAM, ustawienia tymczasowe,
- `2000–2100` — bieżące odczyty stanu.

Częste zapisy do EEPROM mogą skrócić jego trwałość. Automatyka CM5 powinna korzystać przede wszystkim z obszaru RAM i rejestrów bieżącego stanu.

## 9. Rola protokołu C14

C14 jest własnościowym protokołem COMPIT pracującym fizycznie na RS-485. Nie mamy pełnej, oficjalnej specyfikacji binarnej i nie jest ona potrzebna, jeżeli NANO COLOR 2 udostępnia wymagane funkcje AERO 4A2 przez Modbus RTU.

Nie dołączamy drugiego mastera do magistrali C14.

## 10. Ograniczenie dotyczące iNext

Tryb Modbus RTU / BMS może wykluczać jednoczesną pracę z modułem iNext. Przed wdrożeniem należy potwierdzić zachowanie konkretnej wersji firmware panelu.

Lokalny panel i AERO muszą działać niezależnie od CM5.

## 11. Zasada bezpieczeństwa integracji

CM5 nie zastępuje AERO 4A2 i nie przejmuje jego zabezpieczeń.

Po stronie AERO pozostają:

- rozmrażanie,
- bypass,
- sterowanie nagrzewnicami,
- ochrona temperaturowa,
- alarmy,
- logika wentylatorów,
- funkcje serwisowe producenta.

CM5 odczytuje stan i może żądać trybu pracy, np. czasowego wietrzenia. Awaria CM5 nie może blokować normalnej pracy rekuperatora z panelu lokalnego.

## 12. Plan pierwszej walidacji

1. Potwierdzić wersję oprogramowania NANO COLOR 2.
2. Potwierdzić w menu panelu tryb Modbus / BMS.
3. Potwierdzić właściwą parę zacisków Modbus — bez zgadywania i bez wejścia na C14.
4. Użyć izolowanego interfejsu USB–RS-485.
5. Pierwszy test wykonać wyłącznie funkcją `0x03`.
6. Odczytać:
   - rejestr 2017 / adres 2016,
   - rejestr 2022 / adres 2021,
   - rejestr 2037 / adres 2036,
   - rejestr 2040 / adres 2039,
   - rejestr 2041 / adres 2040.
7. Porównać wartości z panelem i rzeczywistym stanem centrali.
8. Wyjaśnić wszystkie wartości nielogiczne oraz aktywny kod alarmu przed jakimkolwiek zapisem.
9. Dopiero po pozytywnej walidacji wykonać pojedynczy zapis rejestru 1082 / adresu 1081 wartością 1.
10. Sprawdzić wietrzenie przez rejestr 2029 / adres 2028 oraz wydajności.
11. Wyłączyć wietrzenie przez rejestr 1082 / adres 1081 wartością 0 i potwierdzić powrót do normalnej pracy.

## 13. Status bieżącej walidacji

Potwierdzono komunikację:

```text
COM10
9600 bit/s
8N1
slave 44
FC03
CRC poprawne
```

Pierwszy odczyt ujawnił błąd opisu w projekcie: adresy PDU były przedstawiane jako numery rejestrów. Błąd został poprawiony w dokumentacji i narzędziu Windows.

Do wyjaśnienia pozostają:

- nielogiczna wartość temperatury pomieszczenia `67,4 °C`,
- kod alarmu AERO `30`,
- zgodność pozostałych wartości z ekranem NANO i rzeczywistym stanem centrali.
