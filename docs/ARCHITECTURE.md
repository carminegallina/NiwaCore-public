# Architecture

## Panoramica

NiwaCore e' un progetto local-first con Raspberry Pi come host operativo. I servizi sono divisi in pannelli e componenti host/firmware.

## Aree principali

- `configs`: configurazione homepage/dashboard.
- `data`: dati versionati o esempi; dati runtime reali sono ignorati.
- `docker`: pannelli Flask containerizzati.
- `firmware`: sketch e tool ESP32-CAM.
- `host`: script e servizi host-side.
- `PROJECT_HISTORY.md`: storia funzionale.
- `ROADMAP.md`: priorita.
- `SYSTEM_SNAPSHOT.md`: stato operativo, porte, volumi, endpoint e note.

## Pannelli Docker

- `docker/drone-panel`
- `docker/shooting-tools`
- `docker/review-panel`
- `docker/storage-panel`
- `docker/lights-panel`
- `docker/system-panel`
- `docker/companion-panel`
- `docker/filebrowser`

## Firmware

Il firmware ESP32-CAM Companion gestisce avatar OLED, heartbeat, camera opzionale, microSD e interazione con il Raspberry. Le configurazioni locali non devono essere committate.

## Sicurezza

- `firmware/esp32cam-companion/niwa_companion_local_config.h` ignorato.
- database e config FileBrowser runtime ignorati.
- `data/*.json` runtime ignorati tranne librerie/esempi esplicitamente versionati.

