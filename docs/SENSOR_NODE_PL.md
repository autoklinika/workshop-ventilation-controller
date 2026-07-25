# Moduł pomiarowy SEN55 + STM32 + RS-485

## Cel

Moduł pomiarowy ma znajdować się w pomieszczeniu, możliwie blisko reprezentatywnego punktu pomiaru. SEN55 nie będzie połączony bezpośrednio z Raspberry Pi długim przewodem I²C.

## Bloki modułu

```text
Zasilanie
  ├── stabilizacja dla STM32
  ├── zasilanie SEN55
  └── zasilanie transceivera RS-485

STM32
  ├── I²C ↔ SEN55
  ├── UART ↔ RS-485
  ├── watchdog
  └── diody/status diagnostyczny (opcjonalnie)
```

## Funkcje firmware STM32

- inicjalizacja i okresowy odczyt SEN55,
- walidacja ramek i statusu czujnika,
- przechowywanie ostatniego poprawnego pomiaru,
- oznaczanie pomiarów nieaktualnych,
- Modbus RTU slave,
- licznik czasu pracy,
- licznik błędów komunikacji z SEN55,
- watchdog sprzętowy,
- bezpieczny restart po zawieszeniu,
- opcjonalna aktualizacja konfiguracji przez rejestry Modbus.

## Mierzone wielkości

- PM1.0,
- PM2.5,
- PM4.0,
- PM10,
- VOC Index,
- NOx Index, jeżeli będzie używany,
- temperatura,
- wilgotność względna,
- status czujnika.

## Założenia komunikacyjne

- protokół: Modbus RTU,
- medium: RS-485 półdupleks,
- domyślny adres urządzenia: 1,
- domyślna prędkość: 19200 bit/s,
- format: 8N1,
- adres i prędkość powinny być możliwe do zmiany później,
- rejestry pomiarowe tylko do odczytu,
- rejestry konfiguracji zapisywane świadomie i walidowane.

## Montaż czujnika

- nie montować bezpośrednio przy nawiewie ani wyciągu,
- nie montować tuż nad piecem,
- zapewnić swobodny przepływ powietrza przez SEN55,
- ograniczyć osadzanie się mgły i rozprysków z myjek,
- obudowa nie może tłumić przepływu przez kanał czujnika,
- moduł powinien być dostępny serwisowo.

## Ograniczenia

VOC Index jest wskaźnikiem jakościowym, a nie bezpośrednim pomiarem stężenia konkretnego rozpuszczalnika. W projekcie służy do wykrywania trendu i wyraźnego pogorszenia jakości powietrza, a nie do certyfikowanego pomiaru bezpieczeństwa chemicznego.
