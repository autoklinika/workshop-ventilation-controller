# ventilation-core Stage 1 — fizyczna walidacja obu kanałów DFR0971 na CM5

Data: 2026-08-01

Gałąź: `agent/cm5-hardware-bringup-stage1`

## Cel

Potwierdzić niezależne działanie obu wyjść analogowych DFR0971 używanych przez `ventilation-core`:

- kanał 0 / `VOUT0` jako nawiew (`supply`),
- kanał 1 / `VOUT1` jako wyciąg (`extract`).

Do testu użyto jednego fana EC. Przewód sterujący był fizycznie przełączany pomiędzy wyjściami.

## Wynik

### VOUT0 / supply

Wysłano nastawę:

```text
supply = 10.0 V
extract = 0.0 V
```

Fan pracował prawidłowo z pełną prędkością. Po komendzie `stop` zatrzymał się.

### VOUT1 / extract

Po zatrzymaniu fana przewód sterujący przełożono z `VOUT0` na `VOUT1`.

Wysłano nastawę:

```text
supply = 0.0 V
extract = 5.0 V
```

Fan pracował prawidłowo z niższą prędkością odpowiadającą nastawie 5 V. Po komendzie `stop` zatrzymał się.

## Wniosek

Fizycznie potwierdzono:

- poprawne mapowanie `supply -> VOUT0`,
- poprawne mapowanie `extract -> VOUT1`,
- niezależne sterowanie obu kanałów,
- poprawne napięcia 10 V i 5 V,
- skuteczne zatrzymanie przez ustawienie obu kanałów na 0 V.

Dwukanałowa warstwa wykonawcza Stage 1 jest zwalidowana na docelowym CM5 i rzeczywistym fanie EC.
