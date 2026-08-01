# Stage 2 — poprawka synchronizacji testu pętli DFR0845

Data: 2026-08-01

Gałąź: `agent/rs485-bringup-stage2`

## Zaobserwowany wynik

Pierwszy sprzętowy test dwóch DFR0845 zakończył się błędem:

```text
RS-485 response timed out after 0 of 10 bytes
```

Test rozpoczynał transmisję z `RS485_BUS_1` do `RS485_BUS_2`. Kierunek odwrotny nie został jeszcze wykonany, ponieważ pierwszy kierunek zakończył się timeoutem.

## Znaleziony problem programowy

Pierwsza implementacja uruchamiała odczyt odbiornika w osobnym wątku, czekała arbitralnie 50 ms i rozpoczynała nadawanie. Właściwy proces będący właścicielem UART-u zerował bufor wejściowy dopiero po obsłużeniu polecenia odczytu.

Przy niekorzystnym planowaniu procesów możliwa była sekwencja:

1. nadawca wysyła dane,
2. dane trafiają do bufora UART odbiornika,
3. opóźniony worker rozpoczyna odczyt i zeruje bufor,
4. wszystkie odebrane dane zostają usunięte,
5. odczyt kończy się timeoutem po 0 bajtach.

Taki wynik nie pozwalał rozstrzygnąć, czy problem był programowy, czy elektryczny.

## Poprawka

Nowa sekwencja jest deterministyczna:

1. synchroniczne wyczyszczenie bufora wejściowego odbiornika,
2. opcjonalny krótki czas stabilizacji,
3. wysłanie wzorca przez nadawcę,
4. odczyt dokładnej liczby bajtów bez ponownego zerowania bufora.

Usunięto zależność od harmonogramu wątku i procesu. Błędy zawierają teraz kierunek transmisji:

```text
RS-485 loopback A->B failed: ...
RS-485 loopback B->A failed: ...
```

## Ocena

Pierwszego timeoutu nie klasyfikujemy jeszcze jako awarii okablowania ani DFR0845. Test sprzętowy należy powtórzyć po pobraniu poprawki, bez zmieniania przewodów A/B/GND.
