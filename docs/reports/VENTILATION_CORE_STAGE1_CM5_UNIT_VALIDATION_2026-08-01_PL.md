# Walidacja jednostkowa ventilation-core Stage 1 na CM5

Data: 2026-08-01

Gałąź: `agent/cm5-hardware-bringup-stage1`

## Platforma

- Raspberry Pi Compute Module 5 Wireless,
- Raspberry Pi OS Lite 64-bit / Debian 13,
- repozytorium uruchomione bezpośrednio na docelowej platformie CM5.

## Polecenie

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

## Wynik

```text
Ran 9 tests in 0.001s

OK
```

## Wniosek

Pełny zestaw testów jednostkowych Stage 1 przeszedł na docelowej platformie CM5. Potwierdzono poprawność warstwy domenowej, aplikacyjnej i adaptera DFR0971 w testach wykorzystujących atrapy sprzętu. Test nie obejmował jeszcze uruchomienia procesu sprzętowego na rzeczywistej magistrali I²C.

## Następny krok

Uruchomić `ventilation-core` ręcznie z lokalnym gniazdem Unix w `/tmp`, potwierdzić przejęcie rzeczywistego DFR0971 i sprawdzić komendy `status`, `set`, `stop` oraz `shutdown` przed instalacją usługi `systemd`.
