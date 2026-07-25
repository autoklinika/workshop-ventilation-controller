# Integracja rekuperatora Prodmax / Compit AERO 4A2

## 1. Zidentyfikowany sprzęt

W pomieszczeniu lutowniczym pracuje rekuperator:

- producent centrali: Prodmax,
- model: PRO MINI 300 H/V CLASSIC + moduł WiFi,
- oznaczenie: PRO MINI 300HV-C/WIFI,
- sterownik centrali: COMPIT AERO 4A2,
- panel pokojowy: COMPIT NANO COLOR 2,
- moduł sieciowy: COMPIT iNext / C14.

Panel NANO COLOR 2 ma zaciski A1, B1, A2, B2, G oraz U. Sterownik AERO 4A2 ma interfejs RS-485 oznaczony jako C14.

## 2. Najważniejszy wniosek

Nie ma potrzeby odtwarzania własnościowego protokołu C14, jeżeli konkretna wersja panelu NANO COLOR 2 obsługuje opublikowany przez Compit tryb Modbus RTU dla AERO 4A ver.2.

Docelowo Raspberry Pi powinno komunikować się z panelem przez Modbus RTU, natomiast panel nadal realizuje komunikację C14 ze sterownikiem AERO 4A2.

```text
SEN55 + STM32
      │
 Modbus RTU
      │
Raspberry Pi
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

Według dokumentacji producenta:

- tryb urządzenia: Modbus RTU Slave,
- domyślny adres: 44,
- prędkość: 9600 bit/s,
- format: 8N1,
- maksymalny deklarowany czas odpowiedzi: 300 ms,
- funkcje Modbus:
  - 0x03 — odczyt Holding Registers,
  - 0x06 — zapis pojedynczego rejestru,
  - 0x10 — zapis wielu rejestrów.

Adres Modbus jest konfigurowalny. W mapie parametrów występuje jako rejestr 1017, z wartością domyślną 44.

## 4. Istotne rejestry stanu

| Rejestr | Znaczenie |
|---:|---|
| 2016 | temperatura pomieszczenia |
| 2021 | temperatura nawiewu |
| 2022 | temperatura czerpni / zewnętrzna |
| 2023 | temperatura wywiewu |
| 2024 | temperatura wyrzutni |
| 2026 | aktywne rozmrażanie |
| 2028 | aktywne wietrzenie |
| 2031 | zabrudzony filtr |
| 2034 | aktualna wydajność nawiewu w % |
| 2035 | aktualna wydajność wywiewu w % |
| 2036 | aktualny bieg wentylacji |
| 2037 | stan bypassu |
| 2039 | rozpoznany moduł wentylacji |
| 2040 | alarm AERO |

Temperatury są raportowane z rozdzielczością 0,1 °C.

## 5. Istotne rejestry sterujące

| Rejestr | Funkcja |
|---:|---|
| 1077 | wentylacja: 0 = OFF, 1 = ON |
| 1079 | bypass: 0 = OFF, 1 = AUTO, 2 = ON |
| 1080 | wybór biegu / trybu |
| 1081 | wietrzenie: 0 = OFF, 1 = ON |

Znaczenie wartości rejestru 1080:

- 0 — bieg 0,
- 1 — bieg 1,
- 2 — bieg 2,
- 3 — bieg 3,
- 4 — program świąteczny,
- 5 — harmonogram.

Do automatycznej reakcji na VOC i PM preferowany jest rejestr 1081. Raspberry Pi może tymczasowo uruchomić wietrzenie, obserwować rzeczywistą wydajność i po określonym czasie wyłączyć wietrzenie, pozostawiając pozostałą automatykę sterownikowi AERO.

## 6. Konfiguracja biegów

Dokumentacja udostępnia również parametry konfiguracyjne, między innymi:

- 1141–1144 — nawiew dla biegów 1, 2, 3 i wietrzenia,
- 1145–1148 — wywiew dla biegów 1, 2, 3 i wietrzenia,
- 1152 — czas wietrzenia,
- 1155 — korekta biegu od sensorów,
- 1166–1168 — parametry rozmrażania,
- 1175 — konfiguracja bypassu.

Nie należy używać tych parametrów do częstego sterowania dynamicznego.

## 7. Podział pamięci i trwałość EEPROM

Producent rozdziela obszary pamięci:

- 1–399 — EEPROM, konfiguracja trwała,
- 1001–1399 — RAM, ustawienia tymczasowe,
- 2000–2100 — bieżące odczyty stanu.

Częste zapisy do EEPROM mogą skrócić jego trwałość. Automatyka Raspberry Pi powinna używać przede wszystkim rejestrów RAM i rejestrów bieżącego stanu.

## 8. Rola protokołu C14

C14 jest własnościowym protokołem Compit pracującym fizycznie na RS-485. Dostępne materiały wskazują typowe parametry 9600 bit/s i 8N2 oraz architekturę master/slave.

Nie mamy pełnej, oficjalnej specyfikacji binarnej C14. Nie jest ona jednak potrzebna, jeżeli panel NANO COLOR 2 udostępnia wymagane funkcje AERO 4A2 przez Modbus RTU.

Nie należy dołączać drugiego urządzenia master bez potwierdzenia topologii i trybu pracy magistrali C14.

## 9. Ograniczenie dotyczące modułu iNext

Dokumentacja NANO COLOR 2 wskazuje, że praca panelu w trybie Modbus RTU / BMS może wykluczać jednoczesną pracę z modułem iNext.

Przed wdrożeniem trzeba sprawdzić na konkretnej wersji firmware, czy wybór Modbus wyłącza fabryczny dostęp WiFi. Lokalny panel i sterownik AERO powinny nadal działać niezależnie od Raspberry Pi.

## 10. Zasada bezpieczeństwa integracji

Raspberry Pi nie zastępuje sterownika AERO 4A2 i nie przejmuje jego zabezpieczeń.

Po stronie AERO pozostają:

- rozmrażanie,
- bypass,
- sterowanie nagrzewnicami,
- ochrona temperaturowa,
- alarmy,
- logika wentylatorów,
- pozostałe funkcje serwisowe producenta.

Raspberry Pi może jedynie odczytywać stan i żądać trybu pracy, np. czasowego wietrzenia.

Awaria Raspberry Pi nie może blokować normalnej pracy rekuperatora z panelu lokalnego.

## 11. Plan pierwszej walidacji

1. Odczytać wersję oprogramowania NANO COLOR 2.
2. Potwierdzić w menu panelu dostępność trybu Modbus / BMS.
3. Ustalić z dokumentacji przypisanie A1/B1 i A2/B2 — nie zgadywać połączeń.
4. Zastosować izolowany interfejs USB–RS-485.
5. Pierwszy test wykonać wyłącznie w trybie odczytu.
6. Odczytać rejestry: 2016, 2021, 2036, 2039 i 2040.
7. Porównać wartości z panelem i rzeczywistym stanem centrali.
8. Dopiero po pozytywnej walidacji wykonać pojedynczy zapis 1081 = 1.
9. Sprawdzić uruchomienie wietrzenia oraz odczyty 2028, 2034 i 2035.
10. Wyłączyć wietrzenie przez 1081 = 0 i potwierdzić powrót do normalnego sterowania.

## 12. Status

Integracja bez podsłuchiwania C14 jest technicznie prawdopodobna i preferowana. Ostateczne potwierdzenie wymaga sprawdzenia wersji firmware panelu, przypisania zacisków oraz testu odczytu Modbus na rzeczywistym urządzeniu.
