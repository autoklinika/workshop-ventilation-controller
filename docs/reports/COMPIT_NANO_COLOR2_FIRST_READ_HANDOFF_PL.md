# COMPIT NANO COLOR 2 — handoff pierwszego odczytu

Gałąź robocza: `agent/rekuperator-rs485-discovery`.

Aktualne założenia są zgodne z `docs/COMPIT_AERO4A2_INTEGRATION_PL.md` i `docs/DECISIONS_PL.md`:

- nie skanujemy ogólnie prędkości, formatów i adresów,
- nie analizujemy C14, jeżeli panel udostępnia Modbus/BMS,
- używamy znanych parametrów 44 / 9600 / 8N1,
- pierwszy test jest wyłącznie odczytowy FC03,
- najpierw potwierdzamy wersję firmware, tryb Modbus/BMS i właściwą parę zacisków,
- pierwszy odczyt obejmuje 2016, 2021, 2036, 2039 i 2040,
- zapis 1081 jest osobnym późniejszym etapem.

Narzędzie Windows: `tools/compit_nano_color2_read.py`.
