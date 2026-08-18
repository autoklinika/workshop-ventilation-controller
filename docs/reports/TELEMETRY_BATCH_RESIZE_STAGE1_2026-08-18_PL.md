# Telemetry batch resize Stage 1 — walidacja produkcyjna

**Data:** 18.08.2026

## Problem produkcyjny

Po wdrożeniu zintegrowanego `CoreState` rozmiar pojedynczej próbki telemetrycznej wzrósł. Na rzeczywistym CM5 zmierzono:

- 1 próbka: ~10,7 KiB,
- 25 próbek: ~213 KiB,
- 50 próbek: ~481 KiB,
- 100 próbek: 1 150 808 B (~1,124 MiB), czyli 109,7% limitu AI Bridge 1 MiB.

Stary batch 100 próbek powodował `HTTP 413 Content Too Large` po stronie AI Bridge.

## Pierwsza próba walidacji PR #36

Testy przedprodukcyjne przeszły:

- testy celowane: 5/5 PASS,
- pełny suite: 359/359 PASS.

Podczas pierwszej próby na produkcyjnym CM5 klient nie otrzymał jednak klasycznego `HTTPError(413)`. Serwer odrzucał duże body wystarczająco wcześnie, że `urllib` podczas wysyłania obserwował `BrokenPipeError` / `ConnectionResetError`, następnie `URLError`. W efekcie ścieżka klasyfikacji `HTTPError.code == 413` nie była wykonywana i istniejący 100-próbkowy batch pozostawał zarezerwowany.

Nie doszło do utraty danych. Telemetryka została zatrzymana, a `ventilation-core` został doprowadzony do `STOP / 0 V`.

## Korekta projektu

Klient CM5 otrzymuje lokalny preflight rozmiaru gotowego JSON przed otwarciem połączenia HTTP. Domyślny limit klienta jest zgodny z limitem AI Bridge:

```text
1 048 576 B
```

Jeżeli body przekracza limit lokalnie, klient zgłasza `AIBridgeRequestTooLarge` bez próby wysłania danych. Dzięki temu agent może deterministycznie:

1. zapisać próbę i diagnostykę,
2. zwolnić wyłącznie rezerwację batcha (`batch_id`, `batch_created_at`),
3. zachować wszystkie próbki i ich historię,
4. zmniejszyć efektywny rozmiar batcha o połowę,
5. ponowić wysyłkę mniejszymi paczkami.

Produkcja ma docelowy cap `--batch-size 50`.

## Granica bezpieczeństwa

Zmiana dotyczy wyłącznie transportu telemetrycznego. Nie zmienia `ventilation-core`, sterowania DAC/AERO, harmonogramów, SHADOW, Zigbee, GUI ani odczytu sensorów. Pojedyncza próbka przekraczająca limit pozostaje `pending` i nie jest automatycznie usuwana.
