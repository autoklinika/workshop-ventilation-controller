# HMI sleep/wake – notatka POC

## Cel

Docelowo CM5 ma zarządzać stanem panelu HMI iiyama ProLite TW1025LASC-B3PNR podczas wyłączania i uruchamiania systemu wentylacji.

## Potwierdzone testy na fizycznym HMI

### Android SLEEP / WAKEUP

Użyte komendy Androida:

```bash
adb shell input keyevent 223   # KEYCODE_SLEEP
adb shell input keyevent 224   # KEYCODE_WAKEUP
```

Wyniki:

- przy połączeniu HMI przez Wi-Fi `KEYCODE_SLEEP` wygasza ekran i HMI przestaje być osiągalne po Wi-Fi;
- po podłączeniu przewodowego Ethernetu `eth0` pozostaje aktywny po `KEYCODE_SLEEP`;
- po sleep HMI nadal odpowiada na ping po Ethernet;
- port TCP 5555 pozostaje dostępny;
- po celowym zerwaniu starej sesji ADB można zestawić nową sesję ADB z uśpionym HMI;
- `adb get-state` po ponownym połączeniu zwraca `device`;
- `KEYCODE_WAKEUP` wysłany przez nową sesję ADB poprawnie wybudza ekran.

Test Ethernet wykonano przy osobnym zasilaniu HMI, bez PoE. Po docelowym podłączeniu Ethernet/PoE należy wykonać krótki test końcowy potwierdzający identyczne zachowanie.

### Sterowanie samym podświetleniem – fallback

Potwierdzono także bezpośrednie sterowanie podświetleniem LCD:

```text
/sys/class/backlight/backlight/brightness
```

Zakres urządzenia:

- `max_brightness = 255`
- typowa jasność podczas testu: `220`
- `brightness = 0` całkowicie wygasza podświetlenie.

Przy `brightness = 0` Android, kiosk, Wi-Fi i ADB pozostają aktywne. Przywrócenie wartości `220` natychmiast zapala ekran. Mechanizm ten należy zachować jako możliwy fallback, ale preferowanym rozwiązaniem docelowym jest prawdziwy Android SLEEP/WAKEUP przez przewodowy Ethernet.

## Docelowa sekwencja

### Wyłączanie CM5

1. Żądanie shutdown.
2. CM5 doprowadza urządzenia wykonawcze do stanu SAFE.
3. CM5 potwierdza zakończenie krytycznej procedury SAFE.
4. Jako jeden z ostatnich kroków wysyła do HMI `KEYCODE_SLEEP`.
5. Niepowodzenie komunikacji z HMI jest logowane, ale **nie może blokować shutdown CM5**.
6. CM5 wykonuje `poweroff`.

### Uruchamianie CM5

1. Start Linuxa i sieci.
2. Start `ventilation-core` i WebGUI.
3. CM5 czeka, aż system sterowania i interfejs użytkownika będą gotowe.
4. CM5 zestawia nowe połączenie ADB z HMI po Ethernet.
5. Wysyła `KEYCODE_WAKEUP`.
6. Sprawdza, czy aplikacja kiosk `pl.autoklinika.workshopventilation.hmi` jest aktywna; w razie potrzeby przywraca ją na pierwszy plan.

Założenie UX: HMI ma wybudzić ekran dopiero wtedy, gdy system CM5 i WebGUI są gotowe do pracy, aby użytkownik nie oglądał niedziałającego lub niegotowego GUI podczas bootowania.

## Warunki przed wdrożeniem produkcyjnym

- HMI stale podłączone przewodowym Ethernet/PoE;
- stabilny adres HMI (np. rezerwacja DHCP lub inna kontrolowana konfiguracja adresacji);
- potwierdzenie ADB po Ethernet po restartach;
- końcowy test SLEEP → nowe połączenie ADB → WAKEUP już na docelowym PoE;
- HMI pozostaje elementem interfejsu, a nie interlockiem bezpieczeństwa: jego brak lub awaria nie mogą blokować bezpiecznego wyłączenia CM5.
