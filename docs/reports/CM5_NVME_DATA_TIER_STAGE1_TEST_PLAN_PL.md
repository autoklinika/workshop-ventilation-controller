# CM5 NVMe Data Tier Stage 1 — validation plan

Validation before any merge to `main`:

1. Repository unit tests / compile checks on branch.
2. CM5 disk preparation verification: ext4 `WVC_DATA`, UUID mount at `/srv/wvc-data`, `noatime`, `fstrim.timer` active.
3. Migration dry run.
4. Controlled migration from eMMC with core forced to `STOP / 0 V`.
5. Post-migration validation:
   - all intended writers use `/srv/wvc-data`,
   - legacy eMMC files remain unchanged rollback snapshots,
   - telemetry and alert databases are readable,
   - Zigbee2MQTT and service agent are active,
   - Web UI remains a read-only client,
   - core remains healthy and hardware state is known.
6. Reboot validation with NVMe present.
7. Mount-loss fail-safe validation: writers must not fall back to eMMC; core alert journal may use RAM fallback only.
8. No merge to `main` without explicit owner approval.
