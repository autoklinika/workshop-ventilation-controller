# Wstępne założenia logiki sterowania

Szczegółowe progi, czasy i zależności zostaną ustalone podczas implementacji oraz prób w rzeczywistym pomieszczeniu. Obecnie definiujemy tylko ramy funkcjonalne.

## Zasada podstawowa

System ma przede wszystkim regularnie przewietrzać pomieszczenie. SEN55 pełni funkcję pomocniczą: wykrywa wyraźne pogorszenie jakości powietrza i pozwala zwiększyć wentylację.

## Kanały sterowania

- kanał 1 DAC 0–10 V: nawiew,
- kanał 2 DAC 0–10 V: wyciąg.

Wyciąg może otrzymywać nieco wyższą wartość zadaną niż nawiew, aby utrzymać lekkie podciśnienie.

## Planowane stany

### STOP

Wentylatory zatrzymane, o ile warunki bezpieczeństwa i konfiguracja na to pozwalają.

### ECO

Niska, stała wymiana powietrza.

### AUTO

Podstawowa praca okresowa plus automatyczne zwiększenie wydajności po wzroście VOC Index, PM lub temperatury.

### PRZEWIETRZANIE

Wymuszona praca przez określony czas, uruchamiana:

- z harmonogramu,
- ręcznie,
- po zakończeniu mycia lub wygrzewania,
- po wykryciu pogorszenia jakości powietrza.

### BOOST

Ręczne lub automatyczne przejście na wysoką wydajność.

### AWARIA / TRYB ZASTĘPCZY

Stan po utracie komunikacji z modułem czujnika albo po wykryciu niesprawności wentylatora. Dokładna reakcja zostanie ustalona w sofcie; preferowane zachowanie to bezpieczna, stała wentylacja zamiast całkowitego wyłączenia.

## Wejścia opcjonalne

W przyszłości można dodać:

- sygnał „myjka pracuje”,
- sygnał „piec pracuje”,
- przycisk BOOST,
- kontaktron drzwi,
- potwierdzenie pracy wentylatorów z Tacho.

System ma jednak działać również bez tych wejść.

## Diagnostyka

Oprogramowanie powinno rejestrować co najmniej:

- aktualny stan pracy,
- zadanie 0–10 V dla obu wentylatorów,
- bieżące pomiary SEN55,
- utratę komunikacji Modbus,
- nieaktualne pomiary,
- brak impulsów Tacho przy aktywnym zadaniu,
- ręczne uruchomienia BOOST,
- przejścia do trybu awaryjnego.

## Strojenie

Do konfiguracji programowej powinny należeć:

- harmonogram przewietrzania,
- czas przewietrzania,
- minimalna i maksymalna wydajność,
- różnica między nawiewem i wyciągiem,
- progi oraz histereza VOC i PM,
- opóźnienia załączania i wyłączania,
- zachowanie po awarii czujnika.
