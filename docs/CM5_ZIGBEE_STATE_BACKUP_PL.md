# CM5 — backup stanu Zigbee2MQTT

## Cel

Pełny backup NVMe nie jest potrzebny do Disaster Recovery WVC, ponieważ telemetria i historia są archiwizowane poza CM5. Na NVMe znajduje się jednak mały, krytyczny stan sieci Zigbee2MQTT. Jego utrata może wymusić ponowne tworzenie sieci i parowanie urządzeń.

Mechanizm kopiuje wyłącznie stan `/srv/wvc-data/zigbee2mqtt` z NVMe na eMMC do `/var/backups/workshop-ventilation/zigbee2mqtt`.

## Zasady

- źródło musi znajdować się na NVMe,
- cel musi znajdować się na eMMC i nie może być tym samym urządzeniem co źródło,
- wymagane są `configuration.yaml`, `database.db` i `coordinator_backup.json`,
- logi Zigbee2MQTT są wykluczone,
- archiwum otrzymuje SHA-256 i metadane,
- snapshot jest tworzony tylko wtedy, gdy stan zmienił się od ostatniej kopii,
- podczas tworzenia snapshotu stan jest haszowany przed i po odczycie; przy zmianie wykonywana jest ponowna próba,
- przechowywanych jest maksymalnie 30 różnych snapshotów,
- nie ma cyklicznego timera,
- `systemd.path` obserwuje wyłącznie trwałe pliki stanu `configuration.yaml`, `database.db` i `coordinator_backup.json`,
- zmiana któregoś z tych plików uruchamia backup; krótki 2-sekundowy delay scala serię zapisów Zigbee2MQTT,
- dodatkowa kontrola fingerprintu nadal gwarantuje, że identyczny stan nie tworzy kolejnego archiwum.

## Instalacja na CM5

```bash
cd /home/wentylacja/workshop-ventilation-controller
git pull --ff-only origin main
sudo bash tools/install_cm5_zigbee_state_backup.sh
```

Installer usuwa wcześniejszy timer, uruchamia event-driven `wvc-zigbee-state-backup.path`, a następnie wykonuje pierwszy snapshot i sprawdza SHA-256 oraz strukturę archiwum.

## Kontrola

```bash
systemctl status wvc-zigbee-state-backup.path --no-pager
systemctl status wvc-zigbee-state-backup.service --no-pager
sudo ls -lah /var/backups/workshop-ventilation/zigbee2mqtt
```

Weryfikacja najnowszego snapshotu:

```bash
latest="$(find /var/backups/workshop-ventilation/zigbee2mqtt -maxdepth 1 -name 'zigbee2mqtt-state-*.tar.gz' | sort | tail -n 1)"
sudo sh -c 'cd "$(dirname "$1")" && sha256sum -c "$(basename "$1.sha256")"' sh "${latest}"
sudo tar -tzf "${latest}"
```

## Odtwarzanie

Restore jest operacją serwisową i nie jest wykonywany automatycznie. Przy uszkodzeniu NVMe należy zatrzymać Zigbee2MQTT, odtworzyć zawartość wybranego poprawnego archiwum do `/srv/wvc-data/zigbee2mqtt`, przywrócić właściciela `wentylacja:wentylacja`, uruchomić usługę i zweryfikować `bridge/state`, inwentarz oraz oba przypisania ról.

Kopie zawierają dane sieci Zigbee, dlatego katalog backupu i pliki mają restrykcyjne uprawnienia i nie mogą być publikowane w repozytorium.
