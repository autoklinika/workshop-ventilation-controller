# Lista elementów sprzętowych

## Elementy przyjęte w koncepcji

| Obszar | Element | Status / uwagi |
|---|---|---|
| Sterownik główny | Raspberry Pi | Montaż w rozdzielni DIN |
| Zasilanie | Zasilacz 5 V na szynę DIN | Dobór mocy po ustaleniu modelu Raspberry Pi i osprzętu |
| Sterowanie analogowe | DFRobot Gravity 2-Channel I²C DAC 0–10 V | Dwa niezależne kanały dla nawiewu i wyciągu |
| Komunikacja | Interfejs RS-485 dla Raspberry Pi | Preferowany wariant izolowany galwanicznie |
| Czujnik | Sensirion SEN55 | VOC Index, PM, temperatura, wilgotność |
| Węzeł czujnika | STM32 | Lokalna obsługa SEN55 i Modbus RTU slave |
| Transceiver czujnika | RS-485 | Zalecany transceiver przemysłowy; izolacja do rozważenia |
| Nawiew | Wentylator EC 0–10 V | Model do potwierdzenia |
| Wyciąg | Harmann ML EC.A 125/300 lub docelowy odpowiednik | Wejście 0–10 V / PWM, wyjście Tacho 3 impulsy/obrót |
| Instalacja | Listwy zaciskowe, bezpieczniki, rozłącznik, obudowa DIN | Dobór na etapie schematu elektrycznego |

## Elementy zalecane

- terminatory 120 Ω na końcach magistrali RS-485,
- rezystory bias/failsafe, jeżeli nie zapewnia ich interfejs,
- ekranowana skrętka dla RS-485,
- osobne prowadzenie przewodów sygnałowych i zasilających wentylatory,
- zabezpieczenie przepięciowe wejść RS-485,
- bezpieczniki dla poszczególnych gałęzi zasilania,
- konwerter poziomów lub wejście zabezpieczające dla Tacho po ustaleniu jego charakterystyki elektrycznej.

## Elementy niewymagane na obecnym etapie

- detektor LEL,
- rozbudowane analizatory gazów,
- dodatkowe czujniki chemiczne,
- bezpośrednie prowadzenie I²C z SEN55 do Raspberry Pi.

## Informacje wymagające potwierdzenia przed zamówieniem końcowym

1. Dokładny model Raspberry Pi.
2. Moc i liczba wyjść zasilacza DIN.
3. Napięcie zasilania modułu czujnika.
4. Czy RS-485 ma być izolowany po obu stronach czy tylko po stronie rozdzielni.
5. Model drugiego wentylatora.
6. Charakterystyka elektryczna wyjść Tacho obu wentylatorów.
7. Sposób montażu DAC oraz zabezpieczenie jego wyjść 0–10 V.
