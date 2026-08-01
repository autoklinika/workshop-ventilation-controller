# Stage 1.5 — plan walidacji alarmu DAC na CM5

Data: 2026-08-01

Gałąź: `agent/dac-alarm-supervision-stage1-5`

## Warunki początkowe

- fan zatrzymany,
- oba kanały DAC ustawione na 0 V,
- usługa `ventilation-core.service` aktywna,
- test wykonywany na stanowisku, z dostępem do przewodu I²C DFR0971.

## Test A — testy jednostkowe

```bash
cd ~/workshop-ventilation-controller
git fetch origin
git switch agent/dac-alarm-supervision-stage1-5
git pull --ff-only origin agent/dac-alarm-supervision-stage1-5
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

Oczekiwany wynik: `Ran 18 tests`, `OK`.

## Test B — start nowej wersji przy podłączonym DAC

```bash
sudo systemctl restart ventilation-core.service
sleep 2

PYTHONPATH=src python3 -m ventilation_core.ctl \
  --socket /run/workshop-ventilation/ventilation-core.sock \
  status
```

Oczekiwane:

- `mode: STOP`,
- `hardware_ready: true`,
- `output_state_known: true`,
- `consecutive_hardware_failures: 0`,
- `active_alarms: []`,
- fan nie rusza.

## Test C — odłączenie DAC przy zatrzymanym fanie

1. Nie zmieniać nastaw; fan ma pozostać zatrzymany.
2. Odłączyć przewód I²C / Gravity od DFR0971.
3. Odczekać co najmniej 4 sekundy.
4. Odczytać status:

```bash
PYTHONPATH=src python3 -m ventilation_core.ctl \
  --socket /run/workshop-ventilation/ventilation-core.sock \
  status
```

Oczekiwane:

- usługa nadal `active (running)`,
- `mode: FAULT`,
- `hardware_ready: false`,
- `output_state_known: false`,
- co najmniej 3 kolejne błędy,
- aktywny alarm `DAC_COMMUNICATION_LOST`,
- fan pozostaje zatrzymany.

Logi:

```bash
sudo journalctl -u ventilation-core.service -n 40 --no-pager
```

## Test D — odzyskanie komunikacji

1. Ponownie podłączyć przewód DAC.
2. Odczekać 2–3 sekundy.
3. Odczytać status.

Oczekiwane:

- `mode: STOP`,
- `hardware_ready: true`,
- `output_state_known: true`,
- `consecutive_hardware_failures: 0`,
- `active_alarms: []`,
- oba kanały wymuszone na 0 V,
- fan nie uruchamia się automatycznie.

## Test E — brak DAC podczas startu usługi

1. Zatrzymać fan i potwierdzić 0 V.
2. Odłączyć DAC.
3. Wykonać:

```bash
sudo systemctl restart ventilation-core.service
sleep 3
sudo systemctl status ventilation-core.service --no-pager
```

4. Odczytać status rdzenia.

Oczekiwane:

- usługa pozostaje `active (running)`,
- rdzeń raportuje `FAULT`,
- aktywny jest `DAC_COMMUNICATION_LOST`,
- po ponownym podłączeniu DAC następuje automatyczne odzyskanie do `STOP / 0 V / 0 V`.

## Test F — powrót do sterowania po odzyskaniu

Po całkowitym wyczyszczeniu alarmu:

```bash
PYTHONPATH=src python3 -m ventilation_core.ctl \
  --socket /run/workshop-ventilation/ventilation-core.sock \
  set --supply 2 --extract 0

sleep 3

PYTHONPATH=src python3 -m ventilation_core.ctl \
  --socket /run/workshop-ventilation/ventilation-core.sock \
  stop
```

Oczekiwane:

- fan startuje przy 2 V,
- fan zatrzymuje się po `stop`,
- alarm nie wraca.

## Zasada bezpieczeństwa

Pierwszy test odłączenia wykonujemy wyłącznie przy 0 V. Test utraty komunikacji przy pracującym fanie można wykonać później jako osobną walidację stanu nieznanego, ponieważ DAC z zachowanym zasilaniem może utrzymać ostatnie napięcie mimo braku I²C.
