#!/usr/bin/env python3
"""Deprecated map-based reader for COMPIT NANO.

The connected controller reports firmware 6.30. The previously used public
NANO COLOR 2 register map does not match the observed device state and must not
be used for interpretation or writes.

Use the read-only raw discovery tool instead:
    py tools\compit_nano_v630_discovery.py --help
"""

raise SystemExit(
    "WYCOFANE: mapa rejestrów nie odpowiada firmware 6.30. "
    "Użyj tools\\compit_nano_v630_discovery.py. "
    "Nie wykonuj zapisów Modbus do czasu potwierdzenia mapy."
)
