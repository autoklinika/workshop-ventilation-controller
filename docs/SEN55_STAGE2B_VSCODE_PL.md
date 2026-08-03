# SEN55 Modbus Stage 2B — przygotowanie dwóch KAmod w VS Code

## Założenie

Oba urządzenia otrzymują dokładnie ten sam firmware `0.3.0-stage2b`. Różnią się wyłącznie trwałym adresem zapisanym w partycji NVS:

```text
KAmod + SEN55 #1 -> slave 1
KAmod + SEN55 #2 -> slave 2
```

Magistrala SENSOR BUS pozostaje:

```text
19200 bit/s, 8N1, Modbus RTU, FC04, mapa v1, 19 Input Registers
```

Provisioning odbywa się wyłącznie lokalnie przez USB KAmod. Skrypt zastępuje zawartość partycji NVS, ale nie kasuje firmware ani partycji OTA.

## 1. Otwórz repozytorium i gałąź Stage 2B

W terminalu PowerShell VS Code:

```powershell
git fetch origin
git switch agent/kamod-modbus-stage2b-multinode
git pull
```

## 2. Otwórz terminal ESP-IDF

W VS Code użyj:

```text
View -> Command Palette -> ESP-IDF: Open ESP-IDF Terminal
```

Dalsze polecenia build, flash i provisioning wykonuj w tym terminalu.

## 3. Zbuduj wspólny firmware

```powershell
cd firmware/sensor-node
idf.py set-target esp32
idf.py fullclean
idf.py build
```

## 4. Przygotuj pierwszy KAmod jako slave 1

Podłącz tylko pierwszy KAmod przez USB. Przykład dla `COM9`:

```powershell
idf.py -p COM9 flash
cd ../..
python tools/provision_sensor_node_address.py --port COM9 --address 1
cd firmware/sensor-node
idf.py -p COM9 monitor
```

W logu startowym musi pojawić się:

```text
resolved Modbus slave address=1
started: mode=RTU address=1 baud=19200
```

Monitor zamknij skrótem:

```text
Ctrl+]
```

## 5. Przygotuj drugi KAmod jako slave 2

Odłącz pierwszy KAmod od USB i podłącz drugi. Dla przykładu nadal `COM9`:

```powershell
idf.py -p COM9 flash
cd ../..
python tools/provision_sensor_node_address.py --port COM9 --address 2
cd firmware/sensor-node
idf.py -p COM9 monitor
```

W logu startowym musi pojawić się:

```text
resolved Modbus slave address=2
started: mode=RTU address=2 baud=19200
```

## 6. Test każdego urządzenia osobno przez USB-RS485

Zainstaluj pyserial, jeżeli nie jest jeszcze dostępny:

```powershell
python -m pip install pyserial
```

Przykład dla konwertera RS-485 na `COM10`.

Pierwszy węzeł:

```powershell
python tools/read_modbus_sensor.py --port COM10 --address 1 --once
```

Drugi węzeł:

```powershell
python tools/read_modbus_sensor.py --port COM10 --address 2 --once
```

Nieistniejący adres powinien zwrócić brak odpowiedzi:

```powershell
python tools/read_modbus_sensor.py --port COM10 --address 3 --once
```

## 7. Test obu urządzeń na jednej magistrali

Połącz magistralę liniowo:

```text
USB-RS485 -> KAmod #1 -> KAmod #2
```

Połącz odpowiednio A z A, B z B oraz referencję GND, jeżeli wymaga jej zastosowany interfejs. Terminacja ma być tylko na dwóch fizycznych końcach magistrali.

Jednorazowy test 10 cykli:

```powershell
python tools/read_modbus_sensor_nodes.py --port COM10 --addresses 1,2 --cycles 10
```

Test ciągły:

```powershell
python tools/read_modbus_sensor_nodes.py --port COM10 --addresses 1,2
```

Narzędzie odpytuje każdy adres niezależnie. Timeout jednego slave nie zatrzymuje odczytu drugiego. Po zakończeniu `Ctrl+C` drukowane jest podsumowanie liczby odczytów i błędów per urządzenie.

## 8. Próba zapisu musi pozostać odrzucona

```powershell
python tools/read_modbus_sensor.py --port COM10 --address 1 --test-write
python tools/read_modbus_sensor.py --port COM10 --address 2 --test-write
```

Oba testy muszą zakończyć się odpowiedzią wyjątkową Modbus, a nie zaakceptowaniem FC06.

## 9. Ponowna zmiana adresu

Aby zmienić lokalny adres urządzenia, podłącz tylko wybrany KAmod przez USB i wykonaj:

```powershell
python tools/provision_sensor_node_address.py --port COM9 --address 2
```

Dozwolony zakres to `1..247`. W tej instalacji używamy wyłącznie `1` i `2`. Po zmianie urządzenie wykonuje reset i korzysta z nowego adresu przy następnym uruchomieniu.

## 10. Minimalna walidacja fizyczna Stage 2B

1. Odczyt slave 1 osobno.
2. Odczyt slave 2 osobno.
3. Odczyt obu urządzeń na jednej magistrali.
4. Brak odpowiedzi dla adresu 3.
5. Odłączenie slave 1 bez utraty slave 2.
6. Ponowne podłączenie slave 1 i automatyczny powrót.
7. Odłączenie slave 2 bez utraty slave 1.
8. Zimny start obu urządzeń.
9. Dłuższy test bez timeoutów i błędów CRC.
10. `modbus_errors=0` dla obu urządzeń.
11. FC06 odrzucone na obu urządzeniach.
12. Potwierdzenie topologii liniowej i terminacji tylko na końcach.
