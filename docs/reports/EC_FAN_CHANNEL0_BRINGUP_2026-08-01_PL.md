# Pierwsze uruchomienie wentylatora EC — kanał 0

Data: 2026-08-01

Gałąź: `agent/cm5-hardware-bringup-stage1`

## Tor sterowania

`CM5 -> I2C -> DFRobot DFR0971 / GP8403 -> VOUT0 0–10 V -> wejście sterujące wentylatora EC`

## Stan połączeń

- jeden wentylator EC podłączony do kanału 0,
- kanał 1 pozostaje nieużywany,
- wyjście Tacho nie jest jeszcze podłączone,
- przed każdym testem oba kanały są zerowane,
- po zakończeniu testu oba kanały wracają do 0 V.

## Wyniki pierwszego uruchomienia

| Napięcie zadane | Zachowanie wentylatora | Wynik |
|---:|---|---|
| 0,0 V | zatrzymany | PASS |
| 0,5 V | nie uruchamia się | PASS |
| 1,0 V | uruchamia się samodzielnie od zatrzymania | PASS |

## Wniosek wstępny

Potwierdzony próg startu znajduje się w przedziale większym niż 0,5 V i nie większym niż 1,0 V. Wartość 1,0 V jest pierwszym dotychczas potwierdzonym napięciem zimnego startu, ale nie jest jeszcze ostatecznym minimalnym progiem.

## Następne pomiary

1. wykonać osobne zimne starty przy 0,6 V, 0,7 V, 0,8 V i 0,9 V,
2. każdy test rozpoczynać po pełnym zatrzymaniu wirnika,
3. po ustaleniu minimalnego napięcia startu sprawdzić histerezę — minimalne napięcie podtrzymania po wcześniejszym uruchomieniu,
4. następnie wykonać punkty charakterystyki 2 V, 5 V, 8 V i 10 V,
5. w kolejnym etapie podłączyć Tacho i mierzyć rzeczywistą prędkość obrotową.
