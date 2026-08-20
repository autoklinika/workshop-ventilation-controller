# CM5 NVMe Data Tier Stage 1 — safety note

## Mount-loss behavior

The production alert journal is located at `/srv/wvc-data/workshop-ventilation/alerts.sqlite3`.

`ventilation-core` must remain available even when the NVMe data tier is unavailable. At the same time it must never mistake the underlying `/srv/wvc-data` directory on eMMC for a mounted NVMe filesystem.

Production therefore sets both:

- `WVC_ALERT_STORE_ALLOW_VOLATILE_FALLBACK=1`
- `WVC_ALERT_STORE_REQUIRED_MOUNT=/srv/wvc-data`

Before opening the persistent alert database, `SqliteAlertStore` verifies that the configured required mount is an actual mount point. If it is not mounted, the persistent open is rejected and the explicitly enabled in-memory fallback is used.

This keeps control logic available while preventing accidental alert-history writes to eMMC after an NVMe mount failure.

Telemetry, weather, AI advisory, service-agent state and Zigbee2MQTT use systemd mount dependencies / mountpoint prechecks and therefore fail closed when the NVMe data tier is unavailable.
