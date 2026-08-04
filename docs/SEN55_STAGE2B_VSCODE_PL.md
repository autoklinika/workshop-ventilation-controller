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

## 2. Aktywuj środowisko ESP-IDF

Preferowana metoda w VS Code:

```text
View -> Command Palette -> ESP-IDF: Open ESP-IDF Terminal
```

Jeżeli rozszerzenie nie otwiera terminala, aktywuj środowisko ręcznie:

```powershell
. "C:\Espressif\esp-idf-v6.0.2\export.ps1"
```

Sprawdź:

```powershell
idf.py --version
```

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
python ..\..\tools\provision_sensor_node_address.py --port COM9 --address 1
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
python ..\..\tools\provision_sensor_node_address.py --port COM9 --address 2
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
python ..\..\tools\read_modbus_sensor.py --port COM10 --address 1 --once
```

Drugi węzeł:

```powershell
python ..\..\tools\read_modbus_sensor.py --port COM10 --address 2 --once
```

Nieistniejący adres powinien zwrócić brak odpowiedzi:

```powershell
python ..\..\tools\read_modbus_sensor.py --port COM10 --address 3 --once
```

## 7. Test obu urządzeń na jednej magistrali

Połącz magistralę liniowo:

```text
USB-RS485 -> KAmod #1 -> KAmod #2
```

Połącz odpowiednio A z A, B z B oraz referencję GND, jeżeli wymaga jej zastosowany interfejs. Terminacja ma być tylko na dwóch fizycznych końcach magistrali.

Jednorazowy test 10 cykli:

```powershell
python ..\..\tools\read_modbus_sensor_nodes.py --port COM10 --addresses 1,2 --cycles 10
```

Test ciągły:

```powershell
python ..\..\tools\read_modbus_sensor_nodes.py --port COM10 --addresses 1,2
```

Narzędzie odpytuje każdy adres niezależnie. Timeout jednego slave nie zatrzymuje odczytu drugiego. Domyślna przerwa pomiędzy zapytaniami do kolejnych węzłów wynosi `10 ms` i zapobiega zbyt szybkiemu przełączeniu kierunku transmisji przez niektóre konwertery USB-RS485.

Wartość można podać jawnie:

```powershell
python ..\..\tools\read_modbus_sensor_nodes.py --port COM10 --addresses 1,2 --inter-node-delay 0.01
```

Po zakończeniu `Ctrl+C` drukowane jest podsumowanie liczby odczytów i błędów per urządzenie.

## 8. Test końcowy Stage 2B

Kolejność 1,2:

```powershell
python ..\..\tools\read_modbus_sensor_nodes.py --port COM10 --addresses 1,2 --cycles 300 --interval 1 --timeout 0.5
```

Kolejność 2,1:

```powershell
python ..\..\tools\read_modbus_sensor_nodes.py --port COM10 --addresses 2,1 --cycles 100 --interval 1 --timeout 0.5
```

Wymagany wynik dla każdego węzła:

```text
errors=0 invalid=0 stale=0 map_errors=0
```

## 9. Próba zapisu musi pozostać odrzucona

```powershell
python ..\..\tools\read_modbus_sensor.py --port COM10 --address 1 --test-write
python ..\..\tools\read_modbus_sensor.py --port COM10 --address 2 --test-write
```

Oba testy muszą zakończyć się odpowiedzią wyjątkową Modbus, a nie zaakceptowaniem FC06.

## 10. Ponowna zmiana adresu

Aby zmienić lokalny adres urządzenia, podłącz tylko wybrany KAmod przez USB i wykonaj:

```powershell
python ..\..\tools\provision_sensor_node_address.py --port COM9 --address 2
```

Dozwolony zakres to `1..247`. W tej instalacji używamy wyłącznie `1` i `2`. Po zmianie urządzenie wykonuje reset i korzysta z nowego adresu przy następnym uruchomieniu.
